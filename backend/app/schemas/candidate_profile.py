"""Candidate profile — durable job-search intent (separate from resume text)."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class Track(BaseModel):
    id: str
    label: str
    priority: int = Field(ge=1, le=3, description="User-configured target tier: P1-P3")
    example_titles: list[str] = []


class AvoidTrack(BaseModel):
    id: str
    label: str
    example_titles: list[str] = []


class Locations(BaseModel):
    summary: str = ""
    tier_1: list[str] = []
    tier_2: list[str] = []
    tier_3: list[str] = []
    remote_ok: bool = True
    relocation_ok: bool = True


class Constraints(BaseModel):
    needs_sponsorship: bool = True


class CompanyPreferences(BaseModel):
    industries: list[str] = []
    stages: list[str] = []
    sizes: list[str] = []
    funding_signals: list[str] = []
    network_signals: list[str] = []
    avoid: list[str] = []


class CandidateProfile(BaseModel):
    tracks: list[Track] = []
    avoid_tracks: list[AvoidTrack] = []
    locations: Locations = Field(default_factory=Locations)
    dealbreakers: list[str] = []
    preferences: list[str] = []
    company_preferences: CompanyPreferences = Field(default_factory=CompanyPreferences)
    # JD domains you cannot do — bump Role P-tier when responsibilities mention these.
    technical_penalties: list[str] = []
    # Schools to match against LinkedIn «X alumni work here» (page text from extension).
    alumni_schools: list[str] = []
    constraints: Constraints = Field(default_factory=Constraints)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_low_priority_tracks(cls, value: Any) -> Any:
        """Move legacy configurable P4/P5 tracks into the extremely-low bucket.

        Users now configure only P1-P3. Keeping an old P4 as P3 would silently
        raise its priority, so preserve its meaning as an avoid/out-of-range
        track instead. Saving the profile later persists the new shape.
        """
        if not isinstance(value, dict):
            return value
        data = dict(value)
        tracks = list(data.get("tracks") or [])
        avoids = list(data.get("avoid_tracks") or [])
        avoid_ids = {
            str(row.get("id") or "")
            for row in avoids
            if isinstance(row, dict)
        }
        kept: list[Any] = []
        changed = False
        for track in tracks:
            if not isinstance(track, dict):
                kept.append(track)
                continue
            try:
                priority = int(track.get("priority"))
            except (TypeError, ValueError):
                kept.append(track)
                continue
            if 1 <= priority <= 3:
                kept.append(track)
                continue
            changed = True
            track_id = str(track.get("id") or "")
            if track_id not in avoid_ids:
                avoids.append(
                    {
                        "id": track_id,
                        "label": track.get("label") or track_id,
                        "example_titles": list(track.get("example_titles") or []),
                    }
                )
                avoid_ids.add(track_id)
        if changed:
            data["tracks"] = kept
            data["avoid_tracks"] = avoids
        return data
