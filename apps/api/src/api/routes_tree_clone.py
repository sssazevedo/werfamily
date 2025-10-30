from flask import Blueprint, request, jsonify, session, abort
from ..infra.familysearch.tree_clone_service import clone_couple_snapshot

tree_clone_bp = Blueprint("tree_clone", __name__)

def _require_token() -> str:
    token = session.get("fs_access_token")
    if not token:
        abort(401, description="not_authenticated")
    return token

@tree_clone_bp.post("/tree/clone")
def tree_clone():
    """
    Ex.: POST /tree/clone?husband=KW7T-Z2P&wife=XXXX-YYY&desc=3&asc=1&family=azevedo
    """
    token = _require_token()
    husband = request.args.get("husband") or request.json.get("husband") if request.is_json else None
    wife    = request.args.get("wife")    or request.json.get("wife")    if request.is_json else None
    depth_desc = int(request.args.get("desc", request.json.get("desc", 3) if request.is_json else 3))
    depth_asc  = int(request.args.get("asc",  request.json.get("asc", 1) if request.is_json else 1))
    family     = (request.args.get("family") or (request.json.get("family") if request.is_json else None)) or "default"

    if not (husband or wife):
        return jsonify({"ok": False, "error": "missing_params", "detail": "informe pelo menos husband ou wife"}), 400

    result = clone_couple_snapshot(
        token=token,
        husband=husband,
        wife=wife,
        depth_desc=depth_desc,
        depth_asc=depth_asc,
        family_slug=family
    )
    return jsonify(result), 200
