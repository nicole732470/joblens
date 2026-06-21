"""Evidence-first entity resolution backed by Postgres.

Every signal, ranking rule, confidence rule, warning, note, and alternative
from the extension is preserved. The only differences are environmental:

  * Data is loaded from Postgres (companies / company_aliases /
    company_search_keys), imported from `data/h1b/employers.json.gz`.
  * Async fetch/decompress is replaced by a synchronous DB load.

lookup() returns normalized resolution metadata:
  { employer, confidence, rank_score, method, matched_on, warnings, notes,
    alternatives } | None
"""

from __future__ import annotations

import math
import threading
from functools import cmp_to_key

from app.db import fetch_all
from app.tools.text_normalize import (
    core_normalize,
    meaningful_tokens,
    short_label,
    slugify_raw,
)

INF = float("inf")


def _intersect(a: set, b: set) -> set:
    return {x for x in a if x in b}


class EntityResolver:
    def __init__(self) -> None:
        self._fein_map: dict[str, dict] = {}
        self._key_index: dict[str, str] = {}
        self._profiles: dict[str, dict] = {}
        self._token_index: dict[str, set[str]] = {}
        self._cache: dict[str, dict | None] = {}

    # ------------------------------------------------------------------ load
    def load(self) -> None:
        employers = fetch_all(
            "SELECT fein, name, naics_code, naics_sector, city, state, "
            "lca_count, h1b_count, certified_count, top_jobs FROM companies"
        )
        aliases = fetch_all("SELECT fein, alias_name FROM company_aliases")
        keys = fetch_all("SELECT search_key, fein FROM company_search_keys")

        aliases_by_fein: dict[str, list[str]] = {}
        for row in aliases:
            aliases_by_fein.setdefault(row["fein"], []).append(row["alias_name"])

        keys_by_fein: dict[str, list[str]] = {}
        self._key_index = {}
        for row in keys:
            keys_by_fein.setdefault(row["fein"], []).append(row["search_key"])
            self._key_index[row["search_key"]] = row["fein"]

        self._fein_map = {}
        for e in employers:
            fein = e["fein"]
            e["names"] = aliases_by_fein.get(fein, [])
            e["search_keys"] = keys_by_fein.get(fein, [])
            self._fein_map[fein] = e

        self._build_indexes()

    def _build_employer_profile(self, employer: dict) -> dict:
        token_set: set[str] = set()
        cores: set[str] = set()
        sources = [
            employer["name"],
            *(employer.get("names") or []),
            *(employer.get("search_keys") or []),
        ]
        for raw in sources:
            for t in meaningful_tokens(raw):
                token_set.add(t)
            core = core_normalize(raw)
            if core:
                cores.add(core)
        return {
            "employer": employer,
            "tokens": token_set,
            "cores": cores,
            "primaryCore": core_normalize(employer["name"]),
        }

    def _build_indexes(self) -> None:
        self._profiles = {}
        self._token_index = {}
        for employer in self._fein_map.values():
            profile = self._build_employer_profile(employer)
            self._profiles[employer["fein"]] = profile
            for token in profile["tokens"]:
                self._token_index.setdefault(token, set()).add(employer["fein"])

    # --------------------------------------------------------- linkedin side
    def _linkedin_token_set(self, slug: str, page_name: str) -> set[str]:
        page_tokens = meaningful_tokens(page_name) if page_name else []
        slug_tokens = meaningful_tokens(slug.replace("-", " ")) if slug else []

        if page_tokens:
            tokens = set(page_tokens)
            for slug_token in slug_tokens:
                if slug_token in tokens:
                    continue
                dominated = any(
                    (page_token in slug_token)
                    or (slug_token in page_token)
                    or slug_token.startswith(page_token)
                    or page_token.startswith(slug_token)
                    for page_token in tokens
                )
                if not dominated:
                    tokens.add(slug_token)
            return tokens
        return set(slug_tokens)

    def _linkedin_core(self, slug: str, page_name: str) -> str:
        page_core = core_normalize(page_name) if page_name else ""
        slug_core = core_normalize(slug.replace("-", " ")) if slug else ""
        if page_core and (not slug_core or len(page_core) >= len(slug_core)):
            return page_core
        return slug_core

    def _slug_token_set(self, slug: str) -> set[str]:
        return set(meaningful_tokens(slug.replace("-", " "))) if slug else set()

    def _page_token_set(self, page_name: str) -> set[str]:
        return set(meaningful_tokens(page_name)) if page_name else set()

    def _slug_display_disagree(self, slug: str, page_name: str) -> bool:
        slug_tokens = self._slug_token_set(slug)
        page_tokens = self._page_token_set(page_name)
        if not slug_tokens or not page_tokens:
            return False
        if len(slug_tokens) != len(page_tokens):
            return True
        return any(t not in page_tokens for t in slug_tokens)

    def _is_display_name_subset(self, page_name: str, legal_name: str) -> bool:
        page_tokens = meaningful_tokens(page_name)
        legal_token_set = set(meaningful_tokens(legal_name))
        if not page_tokens:
            return False
        if len(page_tokens) >= len(meaningful_tokens(legal_name)):
            return False
        return all(t in legal_token_set for t in page_tokens)

    # ------------------------------------------------------------- evidence
    def _ambiguity_count(self, linkedin_tokens: set[str]) -> float:
        if not linkedin_tokens:
            return INF
        feins: set[str] | None = None
        for token in linkedin_tokens:
            hits = self._token_index.get(token)
            if not hits:
                return INF
            feins = set(hits) if feins is None else _intersect(feins, hits)
        return len(feins) if feins is not None else INF

    def _compute_signals(
        self, linkedin_tokens: set[str], linkedin_core_name: str, profile: dict
    ) -> dict:
        shared = _intersect(linkedin_tokens, profile["tokens"])
        linkedin_count = len(linkedin_tokens)
        dol_count = len(profile["tokens"])

        exact_core_match = bool(linkedin_core_name) and (
            linkedin_core_name == profile["primaryCore"]
            or linkedin_core_name in profile["cores"]
        )
        subset_match = linkedin_count > 0 and all(
            t in profile["tokens"] for t in linkedin_tokens
        )
        extra_dol_tokens = [t for t in profile["tokens"] if t not in linkedin_tokens]

        return {
            "shared_count": len(shared),
            "linkedIn_count": linkedin_count,
            "dol_count": dol_count,
            "token_overlap_ratio": (len(shared) / linkedin_count) if linkedin_count else 0,
            "reverse_overlap_ratio": (len(shared) / dol_count) if dol_count else 0,
            "exact_core_match": exact_core_match,
            "subset_match": subset_match,
            "single_token_match": linkedin_count == 1,
            "extra_dol_tokens": extra_dol_tokens,
        }

    def _compute_rank_score(self, signals: dict, ambiguity: float) -> float:
        return (
            (1_000_000 if signals["exact_core_match"] else 0)
            + signals["shared_count"] * 10_000
            + math.floor(signals["token_overlap_ratio"] * 1_000 + 0.5)
            - ambiguity * 100
        )

    @staticmethod
    def _compare_candidates(a: dict, b: dict) -> int:
        sa, sb = a["signals"], b["signals"]
        if sa["exact_core_match"] != sb["exact_core_match"]:
            return int(sb["exact_core_match"]) - int(sa["exact_core_match"])
        if sa["shared_count"] != sb["shared_count"]:
            return sb["shared_count"] - sa["shared_count"]
        if sa["token_overlap_ratio"] != sb["token_overlap_ratio"]:
            d = sb["token_overlap_ratio"] - sa["token_overlap_ratio"]
            return -1 if d < 0 else 1
        if a["ambiguity_count"] != b["ambiguity_count"]:
            d = a["ambiguity_count"] - b["ambiguity_count"]
            return -1 if d < 0 else 1
        return b["profile"]["employer"]["lca_count"] - a["profile"]["employer"]["lca_count"]

    def _is_close_alternative(self, top: dict, other: dict) -> bool:
        if other["profile"]["employer"]["fein"] == top["profile"]["employer"]["fein"]:
            return False
        ts, os = top["signals"], other["signals"]
        if os["shared_count"] == 0:
            return False
        if ts["exact_core_match"] and os["exact_core_match"]:
            return True
        if abs(ts["token_overlap_ratio"] - os["token_overlap_ratio"]) <= 0.15:
            return True
        if ts["shared_count"] > 0 and os["shared_count"] >= ts["shared_count"] - 1:
            return True
        return False

    def _display_overlap(self, page_name: str, legal_name: str) -> float:
        if not page_name or not legal_name:
            return 1
        page_tokens = set(meaningful_tokens(page_name))
        legal_tokens = set(meaningful_tokens(legal_name))
        if not page_tokens or not legal_tokens:
            return 0
        shared = _intersect(page_tokens, legal_tokens)
        return len(shared) / max(len(page_tokens), len(legal_tokens))

    def _passes_minimum_evidence(self, signals: dict, ambiguity: float) -> bool:
        if signals["shared_count"] == 0:
            return False
        if signals["exact_core_match"]:
            if signals["single_token_match"] and ambiguity > 1:
                return False
            if (
                signals["single_token_match"]
                and signals["dol_count"] > 1
                and signals["reverse_overlap_ratio"] < 0.5
            ):
                return False
            return True
        if signals["subset_match"]:
            if signals["single_token_match"] and ambiguity > 1:
                return False
            if (
                signals["single_token_match"]
                and signals["dol_count"] > 1
                and signals["reverse_overlap_ratio"] < 0.5
            ):
                return False
            return True
        if signals["token_overlap_ratio"] >= 0.5 and signals["shared_count"] >= 2:
            return True
        if signals["single_token_match"] and signals["shared_count"] == 1:
            if ambiguity > 1:
                return False
            if signals["dol_count"] > 1 and signals["reverse_overlap_ratio"] < 0.5:
                return False
            return True
        return False

    def _is_fuzzy_evidence(self, signals: dict) -> bool:
        return not signals["exact_core_match"] and not (
            signals["subset_match"] and signals["token_overlap_ratio"] >= 1
        )

    def _assign_confidence(
        self, signals: dict, ambiguity: float, close_alternatives: list, context: dict
    ) -> str | None:
        if not self._passes_minimum_evidence(signals, ambiguity):
            return None

        exact_core_match = signals["exact_core_match"]
        subset_match = signals["subset_match"]
        single_token_match = signals["single_token_match"]
        token_overlap_ratio = signals["token_overlap_ratio"]
        shared_count = signals["shared_count"]
        linkedin_count = signals["linkedIn_count"]
        extra_dol_tokens = signals["extra_dol_tokens"]

        slug_page_disagree = context["slugDisplayDisagree"]
        fuzzy_only = context["fuzzyOnly"]
        competing = ambiguity > 1 or len(close_alternatives) > 0
        weak_overlap = token_overlap_ratio < 0.5
        partial_multi_token = linkedin_count >= 2 and shared_count < linkedin_count
        extra_dol_meaningful = len(extra_dol_tokens) > 0

        if exact_core_match and not competing:
            return "high"
        if subset_match and linkedin_count >= 2 and token_overlap_ratio >= 1 and not competing:
            return "high"

        if fuzzy_only:
            return "low"
        if single_token_match and competing:
            return "low"
        if single_token_match and not exact_core_match:
            return "low"
        if weak_overlap:
            return "low"
        if partial_multi_token:
            return "low"

        if subset_match and linkedin_count >= 2 and extra_dol_meaningful:
            return "medium"
        if competing:
            return "medium"
        if slug_page_disagree:
            return "medium"
        if len(close_alternatives) > 0:
            return "medium"
        if exact_core_match:
            return "medium"

        if single_token_match:
            return "low"

        return "medium"

    # ----------------------------------------------------------- candidates
    def _collect_key_candidates(self, clean_slug: str, page_name: str) -> set[str]:
        keys: set[str] = set()

        def add_key(key: str) -> None:
            if key:
                keys.add(key)

        add_key(clean_slug)
        add_key(clean_slug.replace("-", " "))
        add_key(core_normalize(clean_slug.replace("-", " ")))
        add_key(core_normalize(clean_slug.replace("-", " ")).replace(" ", "-"))
        if page_name:
            add_key(core_normalize(page_name))
            add_key(core_normalize(page_name).replace(" ", "-"))

        feins: set[str] = set()
        for key in keys:
            fein = self._key_index.get(key)
            if fein:
                feins.add(fein)
        return feins

    def _collect_token_candidates(self, linkedin_tokens: set[str]) -> set[str]:
        feins: set[str] = set()
        for token in linkedin_tokens:
            hits = self._token_index.get(token)
            if hits:
                feins.update(hits)
        return feins

    def _resolve_method(self, signals: dict, from_key_index: bool) -> str:
        if signals["exact_core_match"]:
            return "core_exact"
        if signals["subset_match"] and signals["token_overlap_ratio"] >= 1:
            return "core_subset"
        if from_key_index:
            return "key_overlap"
        return "token_overlap"

    def _build_warnings(
        self, signals, confidence, page_name, employer, ambiguity,
        close_alternatives, method, slug_page_disagree,
    ) -> list[str]:
        warnings: list[str] = []
        if signals["single_token_match"]:
            warnings.append("Matched on a single distinctive word — verify the legal entity.")
        if ambiguity > 1:
            warnings.append(f"Multiple employers ({ambiguity}) share these name tokens.")
        if len(close_alternatives) > 0 and confidence != "high":
            warnings.append("Other similar employers exist — see alternatives below.")
        if slug_page_disagree:
            warnings.append("LinkedIn slug and display name disagree — match uses both inputs.")
        if page_name:
            overlap = self._display_overlap(page_name, employer["name"])
            if overlap < 0.34:
                warnings.append(
                    f'LinkedIn shows "{short_label(page_name)}" but LCA lists "{employer["name"]}".'
                )
        if len(signals["extra_dol_tokens"]) > 0 and signals["reverse_overlap_ratio"] < 0.8:
            warnings.append("DOL legal name includes extra words not seen on LinkedIn.")
        if method in ("token_overlap", "key_overlap"):
            warnings.append("Partial token overlap only — confirm legal name and industry.")
        if employer["lca_count"] <= 2:
            warnings.append("Very few LCA filings — weak sponsorship signal.")
        return warnings

    def _build_notes(self, page_name: str, employer: dict) -> list[str]:
        notes: list[str] = []
        if page_name and self._is_display_name_subset(page_name, employer["name"]):
            notes.append(
                f'LinkedIn display name "{short_label(page_name)}" is a subset of '
                f'DOL legal name "{employer["name"]}".'
            )
        return notes

    def _build_result(self, top, page_name, clean_slug, all_ranked, matched_on):
        profile = top["profile"]
        signals = top["signals"]
        ambiguity = top["ambiguity_count"]
        close_alternatives = [c for c in all_ranked[1:] if self._is_close_alternative(top, c)]
        slug_page_disagree = self._slug_display_disagree(clean_slug, page_name)
        method = self._resolve_method(signals, matched_on.startswith("key:"))
        fuzzy_only = self._is_fuzzy_evidence(signals)

        confidence = self._assign_confidence(
            signals, ambiguity, close_alternatives,
            {"slugDisplayDisagree": slug_page_disagree, "fuzzyOnly": fuzzy_only},
        )
        if not confidence:
            return None

        rank_score = self._compute_rank_score(signals, ambiguity)
        warnings = self._build_warnings(
            signals, confidence, page_name, profile["employer"], ambiguity,
            close_alternatives, method, slug_page_disagree,
        )
        notes = self._build_notes(page_name, profile["employer"])

        alternatives = []
        for c in all_ranked[1:4]:
            if c["signals"]["shared_count"] <= 0:
                continue
            alt_conf = self._assign_confidence(
                c["signals"], c["ambiguity_count"], [],
                {
                    "slugDisplayDisagree": slug_page_disagree,
                    "fuzzyOnly": self._is_fuzzy_evidence(c["signals"]),
                },
            )
            if alt_conf:
                alternatives.append({"employer": c["profile"]["employer"], "confidence": alt_conf})

        return {
            "employer": profile["employer"],
            "confidence": confidence,
            "rank_score": rank_score,
            "method": method,
            "matched_on": matched_on[4:] if matched_on.startswith("key:") else matched_on,
            "warnings": warnings,
            "notes": notes,
            "alternatives": alternatives,
            "signals": signals,
            "ambiguity_count": ambiguity,
        }

    # -------------------------------------------------------------- resolve
    def _resolve_match(self, clean_slug: str, page_name: str):
        linkedin_tokens = self._linkedin_token_set(clean_slug, page_name)
        linkedin_core_name = self._linkedin_core(clean_slug, page_name)
        if not linkedin_tokens:
            return None

        candidate_feins = self._collect_token_candidates(linkedin_tokens)
        candidate_feins |= self._collect_key_candidates(clean_slug, page_name)

        global_ambiguity = self._ambiguity_count(linkedin_tokens)
        ranked = []
        for fein in candidate_feins:
            profile = self._profiles.get(fein)
            if not profile:
                continue
            signals = self._compute_signals(linkedin_tokens, linkedin_core_name, profile)
            if not self._passes_minimum_evidence(signals, global_ambiguity):
                continue
            ranked.append(
                {
                    "profile": profile,
                    "signals": signals,
                    "ambiguity_count": global_ambiguity,
                    "rank_score": self._compute_rank_score(signals, global_ambiguity),
                }
            )

        if not ranked:
            return None

        ranked.sort(key=cmp_to_key(self._compare_candidates))
        top = ranked[0]

        matched_on = " + ".join(sorted(linkedin_tokens))
        key_hits = self._collect_key_candidates(clean_slug, page_name)
        if top["profile"]["employer"]["fein"] in key_hits:
            matched_on = f"key:{matched_on}"

        return self._build_result(top, page_name, clean_slug, ranked, matched_on)

    def lookup(self, slug: str, page_name: str | None):
        clean_slug = (slug or "").lower()
        clean_slug = clean_slug.strip("/")
        if not clean_slug:
            return None

        cache_key = f"{clean_slug}|{core_normalize(page_name or '')}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._resolve_match(clean_slug, page_name)
        self._cache[cache_key] = result
        return result

    def resolve_company(self, name: str):
        """Backend entry point: resolve a plain company name (no LinkedIn slug)."""
        name = (name or "").strip()
        if not name:
            return None
        return self.lookup(slugify_raw(name), name)

    def lookup_by_fein(self, fein: str):
        return self._fein_map.get(fein)


_resolver: EntityResolver | None = None
_lock = threading.Lock()


def get_resolver() -> EntityResolver:
    global _resolver
    if _resolver is None:
        with _lock:
            if _resolver is None:
                r = EntityResolver()
                r.load()
                _resolver = r
    return _resolver
