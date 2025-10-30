# apps/api/src/api/routes_auth.py - CÓDIGO INTEGRAL ATUALIZADO

import time, requests, json, secrets, traceback
from datetime import datetime
from flask import Blueprint, jsonify, redirect, request, session, url_for, render_template
from sqlalchemy.exc import IntegrityError
from typing import Any, Dict, List, Tuple, Optional
from functools import wraps

# Suas funções auxiliares (devem permanecer no arquivo)
try: from ..infra.familysearch.fs_routes import FS_BASE as API_BASE_URL
except Exception: API_BASE_URL = "https://apibeta.familysearch.org"
def _headers_json(token: str) -> Dict[str, str]: return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
def _fetch_person_with_relatives(token: str, pid: str) -> Tuple[Dict | None, List[str], List[str], List[str]]:
    url = f"{API_BASE_URL}/platform/tree/persons/{pid}?personDetails=true&children=true"
    try: r = requests.get(url, headers=_headers_json(token), timeout=20); r.raise_for_status(); data = r.json()
    except requests.RequestException: return None, [], [], []
    details = (data.get("persons") or [None])[0]; parents, spouses, children = set(), set(), set()
    if not details: return None, [], [], []
    for rel in data.get("childAndParentsRelationships", []):
        p1 = (rel.get("parent1") or {}).get("resourceId"); p2 = (rel.get("parent2") or {}).get("resourceId"); child = (rel.get("child") or {}).get("resourceId")
        if child == pid:
            if p1: parents.add(p1)
            if p2: parents.add(p2)
        if (p1 == pid or p2 == pid) and child:
            children.add(child)
            if p1 == pid and p2: spouses.add(p2)
            elif p2 == pid and p1: spouses.add(p1)
    return details, list(parents), list(spouses), list(children)
def _format_node(details: Dict) -> Dict:
    display = details.get("display") or {}; gender_type = (details.get("gender") or {}).get("type", "")
    gender = "Male" if "Male" in gender_type else "Female" if "Female" in gender_type else "Unknown"
    return { "id": details.get("id"), "name": display.get("name"), "gender": gender, "birth": {"date": display.get("birthDate"), "place": display.get("birthPlace")}, "death": {"date": display.get("deathDate"), "place": display.get("deathPlace")}, "living": details.get("living", False) }
def _upsert_person(db, p_data: Dict):
    from ..infra.db.models import Person
    p = db.get(Person, p_data["id"]);
    if not p: p = Person(id=p_data["id"]); db.add(p);
    p.name, p.gender = p_data.get("name"), p_data.get("gender")
    birth, death = p_data.get("birth") or {}, p_data.get("death") or {}
    p.birth, p.birth_place = birth.get("date"), birth.get("place")
    p.death, p.death_place = death.get("date"), death.get("place")
def _ensure_edge(db, e_data: Dict):
    from ..infra.db.models import Relation
    typ = e_data.get("type"); src = e_data.get("from") or e_data.get("a"); dst = e_data.get("to") or e_data.get("b")
    if not all([typ, src, dst]): return False
    if typ == 'couple': src, dst = tuple(sorted((src, dst)))
    try:
        q = db.query(Relation).filter_by(rel_type=typ, src_id=src, dst_id=dst)
        if q.first() is None:
            db.add(Relation(rel_type=typ, src_id=src, dst_id=dst)); db.flush()
            return True
        return False
    except IntegrityError:
        db.rollback()
        return False

from .pathfinder_logic import find_kinship_path
from ..infra.familysearch.fs_routes import build_authorize_url, exchange_code_for_token, FS_BASE
from ..infra.db.models import SessionLocal, User, Invite, Membership, Snapshot, UserPath, Person, Relation

auth_bp = Blueprint("auth_bp", __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = session.get("fs_token")
        exp = session.get("fs_token_exp", 0)
        if not token or time.time() > exp:
            return redirect(url_for("auth_bp.index"))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route("/")
def index():
    if "fs_token" in session and time.time() < session.get("fs_token_exp", 0):
        return redirect(url_for("app_main"))
    return render_template("login.html")

@auth_bp.route("/auth/status")
def auth_status():
    token = session.get("fs_token"); exp = session.get("fs_token_exp", 0); user_fs_id = session.get("user_fs_id")
    ok = bool(token) and (time.time() < exp if exp else True) and bool(user_fs_id)
    user_info = {"fs_id": user_fs_id, "name": session.get("user_name")}
    
    if ok and not user_info["name"]:
        db = SessionLocal();
        try:
            user = db.get(User, user_fs_id)
            if user: user_info["name"] = user.name
        finally:
            db.close()
    return jsonify({"ok": ok, "user": user_info})

@auth_bp.route("/login")
def login():
    invite_token = request.args.get("token"); csrf_token = secrets.token_urlsafe(24)
    session["oauth_state"] = csrf_token
    combined_state = f"{invite_token}|{csrf_token}" if invite_token else csrf_token
    auth_url = build_authorize_url(state=combined_state)
    return redirect(auth_url, code=302)

@auth_bp.route("/callback")
def callback():
    full_state = request.args.get("state"); invite_token = None; received_csrf = full_state
    if full_state and "|" in full_state:
        parts = full_state.split("|", 1)
        if len(parts) == 2: invite_token, received_csrf = parts
    if not received_csrf or received_csrf != session.pop("oauth_state", None):
        return "Erro de validação (state mismatch).", 400

    code = request.args.get("code", "");
    if not code: return redirect(url_for("auth_bp.index"))
    tok = exchange_code_for_token(code)
    if not tok or "access_token" not in tok: return redirect(url_for("auth_bp.index"))

    access_token = tok["access_token"]
    session["fs_token"] = access_token
    expires_in = int(tok.get("expires_in", 3600)); session["fs_token_exp"] = int(time.time()) + expires_in

    db = SessionLocal()
    try:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        r = requests.get(f"{FS_BASE}/platform/users/current", headers=headers, timeout=15); r.raise_for_status()
        fs_user_data = r.json()
        user_info = (fs_user_data.get("users") or [{}])[0]
        fs_id = user_info.get("id"); person_id = user_info.get("personId"); contact_name = user_info.get("contactName")

        if fs_id and contact_name:
            user = db.get(User, fs_id)
            if not user: user = User(fs_id=fs_id, name=contact_name); db.add(user)
            else: user.name = contact_name
            db.commit()
            session["user_fs_id"] = fs_id
            session["user_name"] = contact_name
            # <<< MUDANÇA: Salva o Person ID do usuário na sessão >>>
            session["user_person_id"] = person_id

            if invite_token:
                # ... (sua lógica de convite) ...
                pass

    except requests.RequestException as e: 
        print(f"AVISO: Falha ao buscar dados do utilizador: {e}")
        session.clear()
    finally: 
        db.close()
    
    return redirect(url_for("app_main"))

@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("auth_bp.index"))