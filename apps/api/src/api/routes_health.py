from flask import Blueprint, jsonify, redirect, url_for  # adicione redirect, url_for

health_bp = Blueprint("health", __name__)

@health_bp.get("/")
def index():
    # você pode redirecionar para um dashboard no futuro
    return redirect(url_for("health.healthz"))

@health_bp.get("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200

