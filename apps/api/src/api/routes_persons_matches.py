# apps/api/src/api/routes_persons_matches.py
from __future__ import annotations
from flask import Blueprint, request, jsonify, session
from typing import Any, Dict, List, Tuple, Optional

try:
    from ..infra.familysearch.fs_routes import FS_BASE as API_BASE_URL  # noqa: F401
except (ModuleNotFoundError, ImportError):
    API_BASE_URL = "https://apibeta.familysearch.org"  # noqa: F401

try:
    from ..infra.familysearch.fs_search import search_persons_q_with_debug  # type: ignore
except (ModuleNotFoundError, ImportError):
    from fs_search import search_persons_q_with_debug  # type: ignore

persons_matches_bp = Blueprint("persons_matches", __name__)

def _get_bearer_token() -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return session.get("fs_token")

def _split_name(full_name: str) -> Tuple[Optional[str], Optional[str]]:
    parts = [p for p in (full_name or "").replace("  "," ").strip().split(" ") if p]
    if not parts: return None, None
    if len(parts) == 1: return parts[0], None
    return " ".join(parts[:-1]), parts[-1]

def _coalesce_display_value(*values: Optional[str]) -> str:
    for v in values:
        if isinstance(v, str) and v.strip(): return v.strip()
    return ""

def _extract_persons_from_search(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict): return []
    if isinstance(payload.get("persons"), list): return payload["persons"]
    persons: List[Dict[str, Any]] = []
    for e in (payload.get("entries") or []):
        gx = ((e or {}).get("content") or {}).get("gedcomx") or {}
        for p in (gx.get("persons") or []):
            if isinstance(p, dict): persons.append(p)
    return persons

def _score_person(p: Dict[str, Any], *, full_name: str, place: Optional[str]) -> float:
    disp = p.get("display") or {}
    name = _coalesce_display_value(disp.get("name"), p.get("id"))
    birth_place = _coalesce_display_value(disp.get("birthPlace"))
    s_name = 1.0 if name and full_name and full_name.lower() in name.lower() else 0.5 if name else 0.0
    s_place = 0.0
    if place and birth_place:
        pnorm = place.lower(); bpnorm = birth_place.lower()
        s_place = 1.0 if pnorm in bpnorm or bpnorm in pnorm else 0.0
    return float(max(0.0, min(1.0, (0.85 * s_name) + (0.15 * s_place))))

def _summary_from_person(p: Dict[str, Any]) -> Dict[str, Any]:
    disp = p.get("display") or {}
    return {
        "id": p.get("id") or p.get("resourceId"),
        "name": _coalesce_display_value(disp.get("name")),
        "gender": _coalesce_display_value(disp.get("gender")),
        "birthDate": _coalesce_display_value(disp.get("birthDate")),
        "birthPlace": _coalesce_display_value(disp.get("birthPlace")),
        "deathDate": _coalesce_display_value(disp.get("deathDate")),
        "deathPlace": _coalesce_display_value(disp.get("deathPlace")),
    }

@persons_matches_bp.post("/persons/matches")
def persons_matches():
    """
    Entrada: { name, birth_year_from, birth_year_to, birth_place, count, debug? }
    Implementação: usa GET /platform/tree/search com parâmetros q.* (como no seu projeto que funciona).
    """
    body = request.get_json(silent=True) or {}
    full_name: str = (body.get("name") or "").strip()
    birth_year_from = body.get("birth_year_from")
    birth_year_to   = body.get("birth_year_to")
    birth_place     = (body.get("birth_place") or "").strip()
    count           = max(1, min(int(body.get("count") or 20), 100))
    want_debug      = bool(body.get("debug"))

    given, surname = _split_name(full_name)
    token = _get_bearer_token()

    # Estratégia de ano: se vier intervalo, tentamos sem ano (1a) e com ano exato (meio do intervalo) (1b)
    birth_year_exact = None
    if isinstance(birth_year_from, int) and isinstance(birth_year_to, int):
        birth_year_exact = (birth_year_from + birth_year_to) // 2
    elif isinstance(birth_year_from, int):
        birth_year_exact = birth_year_from
    elif isinstance(birth_year_to, int):
        birth_year_exact = birth_year_to

    # 1) primeiro sem ano (mais amplo)
    payload, attempts = search_persons_q_with_debug(
        access_token=token,
        given=given,
        surname=surname,
        birth_year_exact=None,
        birth_place=birth_place or None,
        count=count,
    )
    persons = _extract_persons_from_search(payload)

    # 2) se nada veio e temos um ano “representativo”, tenta com +YYYY
    if not persons and birth_year_exact is not None:
        payload2, attempts2 = search_persons_q_with_debug(
            access_token=token,
            given=given,
            surname=surname,
            birth_year_exact=birth_year_exact,
            birth_place=birth_place or None,
            count=count,
        )
        attempts.extend(attempts2)
        persons = _extract_persons_from_search(payload2)
        if persons:
            payload = payload2

    bucket: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for p in persons:
        pid = p.get("id") or p.get("resourceId")
        if not pid or pid in seen: continue
        seen.add(pid)
        bucket.append({"score": _score_person(p, full_name=full_name, place=birth_place), "summary": _summary_from_person(p)})
    bucket.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    resp: Dict[str, Any] = {"ok": True, "data": bucket[:count]}
    if want_debug:
        resp["debug"] = {
            "attempts": attempts,
            "final_count": len(bucket),
            "input": {
                "name": full_name,
                "given": given,
                "surname": surname,
                "birth_year_from": birth_year_from,
                "birth_year_to": birth_year_to,
                "birth_year_used": birth_year_exact,
                "birth_place": birth_place,
                "count": count,
            },
        }
    return jsonify(resp), 200
