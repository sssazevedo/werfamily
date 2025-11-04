# apps/api/src/api/routes_invites.py
from __future__ import annotations
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, redirect, request, session, url_for

# Importa os modelos do banco de dados
from ..infra.db.models import SessionLocal, User, Family, Membership, Invite

from .routes_auth import login_required

invites_bp = Blueprint("invites_bp", __name__)

@invites_bp.route("/join")
def join_via_token():
    """
    Este é o endpoint que o usuário acessa ao clicar no link de convite.
    Ex: /join?token=abcdef123456
    Ele valida o token e redireciona para o fluxo de login.
    """
    token = request.args.get("token")
    if not token:
        # Se não houver token, apenas redireciona para a página inicial.
        return redirect(url_for("index"))

    db = SessionLocal()
    try:
        # Verifica se o convite existe e não está expirado
        invite = db.query(Invite).filter_by(token=token).first()
        if not invite or invite.expires_at < datetime.utcnow():
            # Em uma aplicação real, você poderia mostrar uma mensagem de "Convite inválido ou expirado".
            return redirect(url_for("index"))
        
        # O token é válido. Redireciona para o endpoint de login,
        # passando o token para que a rota /callback possa processá-lo.
        return redirect(url_for("auth_bp.login", token=token))
    finally:
        db.close()


@invites_bp.route("/family/<string:slug>/invite", methods=["POST"])
def create_invite(slug: str):
    """
    Cria um novo convite para uma família.
    Apenas administradores da família podem chamar este endpoint.
    """
    user_fs_id = session.get("user_fs_id")
    if not user_fs_id:
        return jsonify({"ok": False, "error": "not_authenticated"}), 401

    body = request.get_json(silent=True) or {}
    email = body.get("email") # O e-mail é opcional, para fins de rastreamento

    db = SessionLocal()
    try:
        # 1. Verifica se o usuário é administrador da família especificada
        membership = db.query(Membership).join(Family).filter(
            Family.slug == slug,
            Membership.user_fs_id == user_fs_id,
            Membership.role == "admin"
        ).first()

        if not membership:
            return jsonify({"ok": False, "error": "forbidden"}), 403

        # 2. Gera um token seguro e define a data de expiração (ex: 7 dias)
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        # 3. Cria e salva o novo convite no banco de dados
        new_invite = Invite(
            family_id=membership.family_id,
            email=email,
            token=token,
            expires_at=expires_at
        )
        db.add(new_invite)
        db.commit()

        # 4. Retorna a URL completa do convite, que o admin pode compartilhar
        invite_url = url_for("invites_bp.join_via_token", token=token, _external=True)

        return jsonify({"ok": True, "invite_url": invite_url})
    finally:
        db.close()

@invites_bp.route("/invite/<int:invite_id>", methods=["DELETE"])
@login_required
def delete_invite(invite_id: int):
    """
    Exclui um convite pendente.
    Apenas administradores da família podem chamar este endpoint.
    """
    user_fs_id = session.get("user_fs_id")
    if not user_fs_id:
        return jsonify({"ok": False, "error": "not_authenticated"}), 401

    db = SessionLocal()
    try:
        # 1. Encontra o convite
        invite = db.query(Invite).filter(Invite.id == invite_id).first()
        if not invite:
            return jsonify({"ok": False, "error": "Convite não encontrado."}), 404

        # 2. Verifica se o usuário é administrador da família do convite
        membership = db.query(Membership).filter(
            Membership.family_id == invite.family_id,
            Membership.user_fs_id == user_fs_id,
            Membership.role == "admin"
        ).first()

        if not membership:
            return jsonify({"ok": False, "error": "Você não tem permissão para excluir este convite."}), 403

        # 3. Exclui o convite
        db.delete(invite)
        db.commit()

        return jsonify({"ok": True, "message": "Convite excluído com sucesso."})
    except Exception as e:
        db.rollback()
        print(f"Erro ao excluir convite: {e}")
        return jsonify({"ok": False, "error": "Erro interno do servidor."}), 500
    finally:
        db.close()