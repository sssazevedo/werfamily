# apps/api/src/infra/familysearch/fs_search.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List
import json, re, requests

# Tenta usar sua infra; senão, fallback simples
try:
    from .fs_routes import FS_BASE as API_BASE_URL  # type: ignore
except (ModuleNotFoundError, ImportError):
    API_BASE_URL = "https://apibeta.familysearch.org"

def _strip_accents(s: str) -> str:
    if not s: return ""
    import unicodedata as u
    s = u.normalize("NFD", s)
    return "".join(ch for ch in s if u.category(ch) != "Mn")

def _norm_name(s: str) -> str:
    s = _strip_accents(s or "")
    s = re.sub(r"\b(de|da|do|das|dos)\b", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()

def _extract_persons_from_search(data: dict) -> List[dict]:
    persons: List[dict] = []
    entries = data.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            content = (entry or {}).get("content") or {}
            gx = content.get("gedcomx") or content.get("gedcomX") or {}
            ps = gx.get("persons")
            if isinstance(ps, list):
                persons.extend(ps)
    root = data.get("persons")
    if isinstance(root, list):
        persons.extend(root)
    results = data.get("results")
    if isinstance(results, list):
        persons.extend(results)
    elif isinstance(results, dict):
        ps = results.get("persons")
        if isinstance(ps, list):
            persons.extend(ps)
    return persons

def _attempt_get(url: str, headers: Dict[str,str], params: Dict[str, Any], timeout: int = 30) -> Tuple[dict, dict]:
    dbg = {"url": url, "params": dict(params)}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        dbg.update({
            "status_code": r.status_code,
            "ok": r.ok,
            "content_type": r.headers.get("content-type",""),
            "bytes": len(r.content or b""),
            "text_sample": (r.text or "")[:8000],
        })
        try:
            payload = r.json()
        except Exception:
            payload = {"__raw_text__": r.text}
        dbg["extracted_persons_count"] = len(_extract_persons_from_search(payload)) if isinstance(payload, dict) else 0
        return (payload if isinstance(payload, dict) else {"entries":[]}), dbg
    except requests.RequestException as ex:
        dbg["error"] = f"{type(ex).__name__}: {ex}"
        return {"entries": []}, dbg

def _attempt_post(url: str, headers: Dict[str,str], params: Dict[str, Any], payload: dict, timeout: int = 30) -> Tuple[dict, dict]:
    dbg = {"url": url, "params": dict(params)}
    try:
        r = requests.post(url, headers=headers, params=params, data=json.dumps(payload), timeout=timeout)
        dbg.update({
            "status_code": r.status_code,
            "ok": r.ok,
            "content_type": r.headers.get("content-type",""),
            "bytes": len(r.content or b""),
            "text_sample": (r.text or "")[:8000],
        })
        try:
            data = r.json()
        except Exception:
            data = {"__raw_text__": r.text}
        dbg["extracted_persons_count"] = len(_extract_persons_from_search(data)) if isinstance(data, dict) else 0
        return (data if isinstance(data, dict) else {"entries":[]}), dbg
    except requests.RequestException as ex:
        dbg["error"] = f"{type(ex).__name__}: {ex}"
        return {"entries": []}, dbg

# -------- GET /platform/tree/search com q.*
def search_persons_q_with_debug(
    *,
    access_token: Optional[str],
    given: Optional[str],
    surname: Optional[str],
    birth_year_exact: Optional[int],
    birth_place: Optional[str],
    count: int = 20,
) -> Tuple[dict, List[dict]]:
    base = API_BASE_URL.rstrip("/")
    url = f"{base}/platform/tree/search"
    headers = {
        "Accept": "application/x-gedcomx-atom+json",
        "User-Agent": "WeRfamily-MVP/1.0",
        "Accept-Language": "pt-BR, en;q=0.7",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    def _base_params() -> Dict[str, Any]:
        return {"count": str(min(max(int(count or 20),1),100))}

    attempts: List[dict] = []
    g = _norm_name(given) if given else None
    s = _norm_name(surname) if surname else None
    bp = _strip_accents(birth_place).strip() if birth_place else None

    # Estratégias: (1) g+s+(data)+(lugar), (2) g+s+(data), (3) s+(data), (4) g+s, (5) s, (6) g
    def add_params(p: Dict[str,Any], g_:Optional[str], s_:Optional[str], y:Optional[int], bp_:Optional[str]):
        if g_: p["q.givenName"] = g_
        if s_: p["q.surname"]   = s_
        if y is not None: p["q.birthLikeDate"] = f"+{int(y)}"
        if bp_:
            if 1 <= len(bp_) <= 60: p["q.birthLikePlace"] = bp_

    for (g_, s_, y_, bp_, label) in [
        (g, s, birth_year_exact, bp, "q: given+surname+date+place"),
        (g, s, birth_year_exact, None, "q: given+surname+date"),
        (None, s, birth_year_exact, None, "q: surname+date"),
        (g, s, None, None, "q: given+surname"),
        (None, s, None, None, "q: surname"),
        (g, None, None, None, "q: given"),
    ]:
        params = _base_params()
        add_params(params, g_, s_, y_, bp_)
        payload, dbg = _attempt_get(url, headers, params)
        dbg["label"] = label
        attempts.append(dbg)
        if _extract_persons_from_search(payload):
            return payload, attempts

    return payload, attempts  # última tentativa

# -------- POST /platform/tree/persons/matches com GedcomX mínimo
def matches_with_debug(
    *,
    access_token: Optional[str],
    full_name: str,
    gender: Optional[str],
    birth_year: Optional[int],
    birth_place: Optional[str],
    count: int = 20,
) -> Tuple[dict, dict]:
    base = API_BASE_URL.rstrip("/")
    url = f"{base}/platform/tree/persons/matches"
    params = {"count": str(min(max(count,1),100))}

    gx_gender = None
    if gender:
        g = gender.strip().lower()
        gx_gender = "http://gedcomx.org/Male" if g.startswith("m") else "http://gedcomx.org/Female" if g.startswith("f") else None

    facts = []
    if birth_year or birth_place:
        fact = {"type": "http://gedcomx.org/Birth"}
        if birth_year:  fact["date"]  = {"original": str(int(birth_year))}
        if birth_place: fact["place"] = {"original": birth_place}
        facts.append(fact)

    person = {"names": [{"nameForms": [{"fullText": (full_name or '').strip()}]}]}
    if gx_gender: person["gender"] = {"type": gx_gender}
    if facts:     person["facts"]  = facts
    body = {"persons": [person]}

    # tenta content-types diferentes (alguns pods exigem gedcomx)
    trials = [
        ("json/json",     {"Accept":"application/json",                    "Content-Type":"application/json"}),
        ("gx/gx",         {"Accept":"application/x-gedcomx-v1+json",       "Content-Type":"application/x-gedcomx-v1+json"}),
        ("json/gx",       {"Accept":"application/json",                    "Content-Type":"application/x-gedcomx-v1+json"}),
        ("gx/json",       {"Accept":"application/x-gedcomx-v1+json",       "Content-Type":"application/json"}),
    ]
    last = {}
    for label, extra in trials:
        headers = {
            "User-Agent": "WeRfamily-MVP/1.0",
            "Accept-Language": "pt-BR, en;q=0.7",
            **extra
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        payload, dbg = _attempt_post(url, headers, params, body)
        dbg["label"] = f"matches {label}"
        last = dbg
        if dbg.get("status_code") not in (400,406,415) or _extract_persons_from_search(payload):
            return payload, dbg
    return {"entries":[]}, last
