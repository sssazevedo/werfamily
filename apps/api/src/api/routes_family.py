# apps/api/src/api/routes_family.py
from __future__ import annotations
from flask import Blueprint, jsonify, session
from sqlalchemy.orm import joinedload

import re
from .routes_auth import login_required

# Importa os modelos do banco de dados
from ..infra.db.models import SessionLocal, Family, Membership, Invite, User, Snapshot, SnapshotNode, Person

family_bp = Blueprint("family_bp", __name__)


_meses_dict = {
    # Português
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    # Inglês
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}
# Regex para "DD de MÊS de AAAA" (PT) ou "DD MÊS AAAA" (EN)
_date_regex = re.compile(r"(\d{1,2})\s+(?:de\s+)?([a-zA-Zç]+)(?:\s+(?:de\s+)?(\d{4}))?", re.IGNORECASE)

def _extract_event_date(date_string: str):
    """ Tenta extrair (dia, mês, ano) de um texto de data do FamilySearch. """
    if not date_string:
        return None, None, None
    
    match = _date_regex.search(date_string)
    if not match:
        return None, None, None
        
    try:
        day = int(match.group(1))
        month_str = match.group(2).lower()
        month = _meses_dict.get(month_str)
        year = int(match.group(3)) if match.group(3) else None
        
        if not month:
            return None, None, None
            
        return day, month, year
    except Exception:
        return None, None, None

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
                "id": i.id,  # <<< ADICIONE ESTA LINHA
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

@family_bp.route("/family/<string:slug>/events", methods=["GET"])
@login_required
def get_family_events(slug: str):
    """
    Retorna os eventos (aniversários, etc.) de todas as pessoas
    nos snapshots de uma família.
    """
    user_fs_id = session.get("user_fs_id")
    if not user_fs_id:
        return jsonify({"ok": False, "error": "not_authenticated"}), 401

    db = SessionLocal()
    try:
        family = db.query(Family).filter(Family.slug == slug).first()
        if not family:
            return jsonify({"ok": False, "error": "family_not_found"}), 404
        
        people_query = db.query(Person).join(
            SnapshotNode, SnapshotNode.person_id == Person.id
        ).join(
            Snapshot, Snapshot.id == SnapshotNode.snapshot_id
        ).filter(
            Snapshot.family_id == family.id
        ).distinct(Person.id)
        
        events = []
        for person in people_query.all():
            if person.birth:
                day, month, year = _extract_event_date(person.birth)
                if day and month:
                    events.append({
                        "id": person.id,
                        "type": "birth",
                        "name": person.name,
                        "day": day,
                        "month": month,
                        "year": year
                    })
            
            if person.death:
                day, month, year = _extract_event_date(person.death)
                if day and month:
                    events.append({
                        "id": person.id,
                        "type": "death",
                        "name": person.name,
                        "day": day,
                        "month": month,
                        "year": year
                    })
        
        return jsonify({"ok": True, "events": events})

    finally:
        db.close()