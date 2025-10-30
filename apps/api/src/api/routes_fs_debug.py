from flask import Blueprint, request, jsonify, session
import requests
from ..infra.familysearch.fs_client import API_BASE_URL

fs_dbg_bp = Blueprint("fs_dbg", __name__)

@fs_dbg_bp.get("/fs/raw")
def fs_raw():
    token = session.get("fs_access_token")
    if not token:
        return jsonify({"ok": False, "error": "not_authenticated"}), 401

    path = request.args.get("path") or "/platform/tree/search"
    # você pode passar ?q.anyName=Maria&count=5 na própria URL
    params = {k: v for k, v in request.args.items() if k not in {"path"}}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/x-gedcomx-atom+json",
    }
    url = f"{API_BASE_URL}{path}"
    r = requests.get(url, headers=headers, params=params, timeout=25)

    try:
        data = r.json()
    except Exception:
        data = {"_text": r.text[:1000]}

    preview = None
    entries = data.get("entries") if isinstance(data, dict) else None
    persons = data.get("persons") if isinstance(data, dict) else None

    def _first_two(x):
        if isinstance(x, list):
            return x[:2]
        if isinstance(x, dict):
            # mostra as primeiras chaves e 1o item caso haja listas conhecidas
            out = {"_first_keys": list(x.keys())[:10]}
            if "entries" in x and isinstance(x["entries"], list):
                out["entries_preview"] = x["entries"][:1]
            if "persons" in x and isinstance(x["persons"], list):
                out["persons_preview"] = x["persons"][:1]
            return out
        return x  # string, etc.

    if entries is not None:
        preview = _first_two(entries)
    elif persons is not None:
        preview = _first_two(persons)
    else:
        preview = _first_two(data)

    return jsonify({
        "ok": r.ok,
        "status": r.status_code,
        "url": r.url,
        "headers": dict(r.headers),
        "keys": list(data.keys()) if isinstance(data, dict) else str(type(data)),
        "preview": preview,
    })
