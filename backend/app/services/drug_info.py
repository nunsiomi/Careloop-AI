"""Medicine information from trusted public sources only (decided by Nunsi, 5 Nov 2026): never the open web.

- RxNav (US National Library of Medicine) turns a name, brand or a slightly wrong spelling into an RxNorm id.
- MedlinePlus Connect (same library) gives the plain-language "what it is used for" summary, for patients.
- openFDA drug labels give warnings, interactions and contraindications, for the care team only.

All free, no key. Answers are cached for a day. Any failure returns None, and the caller says it could not check.
"""

import html
import logging
import re
import time

import httpx

log = logging.getLogger("careloop.drug_info")

RXNAV = "https://rxnav.nlm.nih.gov/REST"
MEDLINEPLUS = "https://connect.medlineplus.gov/service"
OPENFDA = "https://api.fda.gov/drug/label.json"
TIMEOUT = 8
CACHE_SECONDS = 86400
PATIENT_SOURCE = "MedlinePlus, US National Library of Medicine"
LABEL_SOURCE = "US FDA drug label"

_cache: dict[str, tuple[float, dict | None]] = {}

STRENGTH = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ml|g|iu|units?|%)\b.*$", re.I)
DOSE = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ml|g|iu|units?|times?|tablets?|capsules?|doses?|hours?|days?|weeks?)\b", re.I)
FORMS = re.compile(r"\b(tablets?|tabs?|capsules?|caps?|syrup|suspension|injection|cream|ointment|drops|inhaler|sachet|oral|solution|"
                   r"modified release|extended release|er|sr|xl)\b", re.I)


def clean_name(text: str) -> str:
    """'Amlodipine 5 mg tablet' -> 'amlodipine'."""
    name = STRENGTH.sub("", str(text or ""))
    name = FORMS.sub("", name)
    return re.sub(r"[^a-z\- ]", "", name.lower()).strip(" -")


def _plain(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str, count: int, without_numbers: bool = False) -> str:
    parts = [part for part in re.split(r"(?<=[.!?])\s+", text) if part]
    if without_numbers:  # a patient never hears a dose from a leaflet; their plan holds their own dose
        parts = [part for part in parts if not DOSE.search(part)]
    return " ".join(parts[:count])


def _label_section(label: dict, *keys: str, limit: int = 700) -> str:
    for key in keys:
        if label.get(key):
            text = re.sub(r"^\s*[\d.]*\s*[A-Z &]{4,}\s+", "", _plain(" ".join(label[key])))  # drop "5 WARNINGS AND PRECAUTIONS"
            return text[:limit].rsplit(" ", 1)[0] + ("…" if len(text) > limit else "")
    return ""


async def _rxcui(http: httpx.AsyncClient, name: str) -> str | None:
    response = await http.get(f"{RXNAV}/rxcui.json", params={"name": name, "search": 2})
    ids = (response.json().get("idGroup") or {}).get("rxnormId") or []
    if ids:
        return ids[0]
    response = await http.get(f"{RXNAV}/approximateTerm.json", params={"term": name, "maxEntries": 1})
    candidates = (response.json().get("approximateGroup") or {}).get("candidate") or []
    return candidates[0].get("rxcui") if candidates else None


async def _medlineplus(http: httpx.AsyncClient, rxcui: str) -> dict | None:
    response = await http.get(MEDLINEPLUS, params={
        "mainSearchCriteria.v.cs": "2.16.840.1.113883.6.88", "mainSearchCriteria.v.c": rxcui,
        "knowledgeResponseType": "application/json", "informationRecipient.languageCode.c": "en"})
    entries = (response.json().get("feed") or {}).get("entry") or []
    if not entries:
        return None
    entry = entries[0]
    return {"title": _plain(entry["title"]["_value"]), "summary": _plain((entry.get("summary") or {}).get("_value", "")),
            "url": (entry.get("link") or [{}])[0].get("href", "").split("?")[0]}


async def _label(http: httpx.AsyncClient, name: str) -> dict | None:
    for field in ("openfda.generic_name", "openfda.brand_name"):
        response = await http.get(OPENFDA, params={"search": f'{field}:"{name}"', "limit": 1})
        if response.status_code == 200 and response.json().get("results"):
            return response.json()["results"][0]
    return None


async def look_up(medicine: str) -> dict | None:
    """{name, used_for, warnings, interactions, contraindications, sources[], url} or None when nothing trusted was found."""
    name = clean_name(medicine)
    if len(name) < 3:
        return None
    cached = _cache.get(name)
    if cached and cached[0] > time.time():
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            rxcui = await _rxcui(http, name)
            leaflet = await _medlineplus(http, rxcui) if rxcui else None
            label = await _label(http, name)
            if not label and leaflet:  # "paracetamol" is labelled as acetaminophen in the US
                label = await _label(http, clean_name(leaflet["title"]))
    except (httpx.HTTPError, ValueError, KeyError) as error:
        log.warning("Medicine look-up for %r failed: %r", name, error)
        return None  # not cached: try again next time
    if not leaflet and not label:
        result = None
    else:
        result = {
            "name": leaflet["title"] if leaflet else name.title(),
            "used_for": _sentences(leaflet["summary"], 2) if leaflet else _label_section(label, "indications_and_usage", "purpose", limit=400),
            "used_for_patient": _sentences(leaflet["summary"], 2, without_numbers=True) if leaflet else "",
            "warnings": _label_section(label, "boxed_warning", "warnings_and_cautions", "warnings") if label else "",
            "interactions": _label_section(label, "drug_interactions") if label else "",
            "contraindications": _label_section(label, "contraindications", "do_not_use", limit=400) if label else "",
            "sources": [source for source, found in ((PATIENT_SOURCE, leaflet), (LABEL_SOURCE, label)) if found],
            "url": leaflet["url"] if leaflet else "",
        }
    _cache[name] = (time.time() + CACHE_SECONDS, result)
    return result


def for_patient(info: dict | None) -> dict:
    """Only what a patient may hear: what it is generally used for, and where that came from. No doses."""
    if not info or not info.get("used_for_patient"):
        return {"found": False, "note": "No trusted information found. Offer to pass the question to the care team."}
    return {"found": True, "name": info["name"], "generally_used_for": info["used_for_patient"], "source": PATIENT_SOURCE,
            "note": "General information only. Their care team decides why it is right for them."}


def for_care_team(info: dict | None) -> dict:
    if not info:
        return {"found": False, "note": "No trusted information found for that name. Check the spelling, or look it up in the facility's formulary."}
    return {"found": True, **{key: info[key] for key in ("name", "used_for", "warnings", "interactions", "contraindications", "sources", "url")}}
