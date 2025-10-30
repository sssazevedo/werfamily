from flask import Blueprint, request, jsonify, session
from ..services.load_tree import load_tree
from ..infra.familysearch.fs_client_helpers import auth_headers_from_session

tree_bp = Blueprint("tree", __name__)

@tree_bp.post("/tree/load")
def tree_load():
    fsid = request.args.get("fsid")
    depth = int(request.args.get("depth", "4") or 4)
    if not fsid:
        return jsonify({"ok": False, "error": "fsid required"}), 400

    # 1) tenta token no header Authorization
    authz = request.headers.get("Authorization", "")
    if authz.startswith("Bearer "):
        session["fs_access_token"] = authz.split(" ", 1)[1].strip()

    # 2) chama o serviço (ele usa auth_headers_from_session internamente)
    stats = load_tree(fsid, depth=depth)
    return jsonify(stats), (200 if stats.get("ok") else 401 if stats.get("error") == "not_authenticated" else 400)
