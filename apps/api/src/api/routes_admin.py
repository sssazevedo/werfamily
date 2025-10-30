from flask import Blueprint, request, jsonify, abort
import secrets, time
from ..infra.db.db import init_db, create_invite

admin_bp = Blueprint("admin", __name__)

def _is_admin_mock() -> bool:
    # MVP: coloque sua checagem real; por enquanto, aceita sempre.
    return True

@admin_bp.post("/admin/invites")
def admin_create_invite():
    if not _is_admin_mock():
        abort(403)
    init_db()
    body = request.get_json(force=True, silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    family = (body.get("family") or "default").strip().lower()
    if not email:
        return jsonify({"ok": False, "error": "email_required"}), 400
    token = secrets.token_urlsafe(16)
    create_invite(family, email, token, ttl_days=int(body.get("ttl_days", 7)))
    return jsonify({"ok": True, "invite": {"token": token, "email": email, "family": family}}), 200
