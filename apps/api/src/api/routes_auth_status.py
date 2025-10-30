from flask import Blueprint, jsonify, session, current_app
import os, requests

auth_status_bp = Blueprint("auth_status", __name__)

API_BASE_URL = os.getenv("FS_API_BASE_URL", "https://apibeta.familysearch.org")

@auth_status_bp.get("/auth/status")
def auth_status():
    token = session.get("fs_access_token")
    if not token:
        return jsonify({"connected": False}), 200
    try:
        r = requests.get(
            f"{API_BASE_URL}/platform/users/current",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )
        if r.status_code != 200:
            return jsonify({"connected": False}), 200
        data = r.json() or {}
        # tenta extrair um nome amigável
        user = {}
        for p in (data.get("persons") or []):
            disp = p.get("display") or {}
            if disp.get("name"):
                user["name"] = disp["name"]
                break
        return jsonify({"connected": True, "user": user}), 200
    except Exception as e:
        current_app.logger.warning(f"/auth/status error: {e}")
        return jsonify({"connected": False}), 200
