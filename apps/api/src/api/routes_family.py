# apps/api/src/api/routes_family.py
from __future__ import annotations
from flask import Blueprint, jsonify, session
from sqlalchemy.orm import joinedload

# Importa os modelos do banco de dados
from ..infra.db.models import SessionLocal, Family, Membership, Invite, User

family_bp = Blueprint("family_bp", __name__)

@family_bp.route("/family/<string:slug>/manage", methods=["GET"])
def get_management_data(slug: str):
    """
    Retorna os dados de gestão para uma família: lista de membros e convites pendentes.
    Apenas administradores da família podem aceder.
    """
    user_fs_id = session.get("user_fs_id")
    if not user_fs_id:
        return jsonify({"ok": False, "error": "not_authenticated"}), 401

    db = SessionLocal()
    try:
        # 1. Verifica se o utilizador é administrador da família
        membership = db.query(Membership).join(Family).filter(
            Family.slug == slug,
            Membership.user_fs_id == user_fs_id,
            Membership.role == "admin"
        ).first()

        if not membership:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        
        # 2. Busca todos os membros da família
        all_members = db.query(Membership).filter(
            Membership.family_id == membership.family_id
        ).options(
            joinedload(Membership.user)
        ).all()

        members_data = []
        for m in all_members:
            if m.user: # Garante que o utilizador associado existe
                members_data.append({
                    "id": m.user_fs_id,
                    "name": m.user.name,
                    "role": m.role
                })

        # 3. Busca todos os convites pendentes
        pending_invites = db.query(Invite).filter(
            Invite.family_id == membership.family_id
        ).order_by(Invite.created_at.desc()).all()

        invites_data = []
        for i in pending_invites:
            invites_data.append({
                "token": i.token,
                "email": i.email,
                "created_at": i.created_at.isoformat()
            })

        # 4. Retorna os dados compilados
        return jsonify({
            "ok": True,
            "data": {
                "members": members_data,
                "pending_invites": invites_data
            }
        })

    finally:
        db.close()