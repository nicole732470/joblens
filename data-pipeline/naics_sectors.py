"""NAICS 2-digit sector labels for employer index enrichment."""

NAICS_SECTORS: dict[str, str] = {
    "11": "Agriculture, forestry & fishing",
    "21": "Mining & extraction",
    "22": "Utilities",
    "23": "Construction",
    "31": "Manufacturing",
    "32": "Manufacturing",
    "33": "Manufacturing",
    "42": "Wholesale trade",
    "44": "Retail trade",
    "45": "Retail trade",
    "48": "Transportation & warehousing",
    "49": "Transportation & warehousing",
    "51": "Information / software / media",
    "52": "Finance & insurance",
    "53": "Real estate",
    "54": "Professional & technical services",
    "55": "Management of companies",
    "56": "Administrative & support services",
    "61": "Education",
    "62": "Healthcare & social assistance",
    "71": "Arts, entertainment & recreation",
    "72": "Hospitality & food services",
    "81": "Other services",
    "92": "Public administration",
}


def naics_sector_label(code: str | None) -> str:
    code = str(code or "").strip()
    if len(code) < 2 or not code[:2].isdigit():
        return ""
    return NAICS_SECTORS.get(code[:2], "Other industry")
