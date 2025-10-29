# apps/api/src/api/routes_snapshot.py
from __future__ import annotations
import os, time, traceback, json
from typing import Any, Dict, List, Tuple
from collections import deque
import requests
from flask import Blueprint, jsonify, request, session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from ..infra.db.models import (
    init_db, SessionLocal, Person, Relation,
    Snapshot, SnapshotNode, SnapshotEdge, User, Family, Membership, UserPath
)
try: from ..infra.familysearch.fs_routes import FS_BASE as API_BASE_URL
except Exception: API_BASE_URL = "https://apibeta.familysearch.org"

snapshot_bp = Blueprint("snapshot", __name__)

def _auth_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "): return auth.split(" ", 1)[1].strip()
    return session.get("fs_token")

def _headers_json(token: str) -> Dict[str, str]: return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
def _me(token: str) -> Dict[str, Any]: r = requests.get(f"{API_BASE_URL}/platform/users/current", headers=_headers_json(token), timeout=20); r.raise_for_status(); return r.json()
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
def _build_tree_iteratively(token: str, roots: List[str], desc_depth: int) -> Tuple[List[Dict], List[Dict]]:
    nodes, edges = {}, {}; processed_ids = set(); queue = deque([(pid, 0) for pid in roots])
    while queue:
        pid, depth = queue.popleft()
        if pid in processed_ids: continue
        details, _, spouse_ids, child_ids = _fetch_person_with_relatives(token, pid); processed_ids.add(pid)
        if not details: continue
        nodes[pid] = _format_node(details)
        for spouse_id in spouse_ids:
            edges[tuple(sorted((pid, spouse_id)))] = {"type": "couple", "a": pid, "b": spouse_id}
            if spouse_id not in nodes:
                s_details, _, _, _ = _fetch_person_with_relatives(token, spouse_id)
                if s_details: nodes[spouse_id] = _format_node(s_details)
        if depth < desc_depth:
            for child_id in child_ids:
                if child_id not in processed_ids: queue.append((child_id, depth + 1))
                edges[tuple(sorted((pid, child_id)))] = {"type": "parentChild", "from": pid, "to": child_id}
    return list(nodes.values()), list(edges.values())
def _upsert_person(db, p_data: Dict):
    p = db.get(Person, p_data["id"]);
    if not p: p = Person(id=p_data["id"]); db.add(p)
    p.name, p.gender = p_data.get("name"), p_data.get("gender")
    birth, death = p_data.get("birth") or {}, p_data.get("death") or {}
    p.birth, p.birth_place = birth.get("date"), birth.get("place")
    p.death, p.death_place = death.get("date"), death.get("place")
def _ensure_edge(db, e_data: Dict):
    typ = e_data.get("type"); src = e_data.get("from") or e_data.get("a"); dst = e_data.get("to") or e_data.get("b")
    if not all([typ, src, dst]): return
    if typ == 'couple': src, dst = tuple(sorted((src, dst)))
    try:
        q = db.query(Relation).filter_by(rel_type=typ, src_id=src, dst_id=dst)
        if q.first() is None: db.add(Relation(rel_type=typ, src_id=src, dst_id=dst)); db.flush()
    except IntegrityError: db.rollback()

@snapshot_bp.post("/snapshot/clone")
def snapshot_clone():
    token = _auth_token(); user_fs_id = session.get("user_fs_id")
    if not token or not user_fs_id: return jsonify({"ok": False, "error": "not_authenticated"}), 401
    body = request.get_json(silent=True) or {}
    husband, wife = (body.get("husband") or "").strip(), (body.get("wife") or "").strip()
    desc_d = int(body.get("desc_depth") or 0)
    slug = (body.get("slug") or "default").strip()
    roots = [pid for pid in [husband, wife] if pid]
    if not roots: return jsonify({"ok": False, "error": "missing_roots"}), 400
    nodes, edges = _build_tree_iteratively(token, roots, desc_d)
    init_db(); db = SessionLocal()
    try:
        family = db.query(Family).filter_by(slug=slug).first()
        if not family:
            family = Family(slug=slug, name=slug); db.add(family); db.flush()
            membership = Membership(user_fs_id=user_fs_id, family_id=family.id, role="admin"); db.add(membership)
        existing = db.query(Snapshot).filter_by(slug=slug).first()
        if existing: db.query(SnapshotNode).filter_by(snapshot_id=existing.id).delete(); db.query(SnapshotEdge).filter_by(snapshot_id=existing.id).delete(); db.delete(existing);
        snap = Snapshot(family_id=family.id, slug=slug, root_husband_id=husband, root_wife_id=wife, desc_depth=desc_d, asc_depth=0)
        db.add(snap); db.flush()
        for p_data in nodes: _upsert_person(db, p_data); db.add(SnapshotNode(snapshot_id=snap.id, person_id=p_data["id"]))
        for e_data in edges: _ensure_edge(db, e_data); src = e_data.get("from") or e_data.get("a"); dst = e_data.get("to") or e_data.get("b"); db.add(SnapshotEdge(snapshot_id=snap.id, type=e_data["type"], src_id=src, dst_id=dst))
        db.commit()
    except Exception as e: db.rollback(); traceback.print_exc(); return jsonify({"ok": False, "error": "database_error", "detail": str(e)}), 500
    finally: db.close()
    
    # Adiciona a flag isAdmin=True porque quem clona é sempre admin
    snapshot_json = { "ok": True, "slug": slug, "roots": roots, "elements": {"nodes": [{"data": n} for n in nodes], "edges": [{"data": e} for e in edges]}, "isAdmin": True }
    return jsonify(snapshot_json), 200

@snapshot_bp.get("/snapshot/<slug>")
def snapshot_get(slug: str):
    user_fs_id = session.get("user_fs_id");
    if not user_fs_id: return jsonify({"ok": False, "error": "not_authenticated"}), 401
    db = SessionLocal()
    try:
        # --- ALTERAÇÃO AQUI: Verifica o papel do utilizador na mesma query ---
        membership = db.query(Membership).join(Family).join(Snapshot).filter(
            Snapshot.slug == slug,
            Membership.user_fs_id == user_fs_id
        ).first()

        if not membership: return jsonify({"ok": False, "error": "not_found_or_forbidden"}), 404
        
        # O snapshot existe e pertence à família da qual o utilizador é membro
        snap = db.query(Snapshot).filter_by(slug=slug).first()
        is_admin = membership.role == "admin"
        
        kinship_path = []
        path_record = db.query(UserPath).filter_by(user_fs_id=user_fs_id, family_id=snap.family_id).first()
        if path_record and path_record.path_json: kinship_path = json.loads(path_record.path_json)
        
        snapshot_person_ids = {n.person_id for n in db.query(SnapshotNode.person_id).filter_by(snapshot_id=snap.id)}
        
        global_relations = db.query(Relation).filter(
            or_(Relation.src_id.in_(snapshot_person_ids), Relation.dst_id.in_(snapshot_person_ids))
        ).all()
        
        path_person_ids = set(kinship_path)
        extra_relation_ids = {r.src_id for r in global_relations}.union({r.dst_id for r in global_relations})
        all_person_ids = snapshot_person_ids.union(path_person_ids).union(extra_relation_ids)

        all_persons = db.query(Person).filter(Person.id.in_(all_person_ids)).all()
        nodes = [{"id": p.id, "name": p.name, "gender": p.gender, "birth": {"date": p.birth, "place": p.birth_place}, "death": {"date": p.death, "place": p.death_place}} for p in all_persons]
        
        snapshot_edges_db = db.query(SnapshotEdge).filter_by(snapshot_id=snap.id).all()
        edges_map = {}
        for e in snapshot_edges_db:
            key = (e.type, e.src_id, e.dst_id)
            edges_map[key] = {"type": e.type, "from": e.src_id, "to": e.dst_id, "a": e.src_id, "b": e.dst_id}
        for r in global_relations:
             key = (r.rel_type, r.src_id, r.dst_id)
             if key not in edges_map:
                edges_map[key] = {"type": r.rel_type, "from": r.src_id, "to": r.dst_id, "a": r.src_id, "b": r.dst_id}
        edges = list(edges_map.values())

        # --- ALTERAÇÃO FINAL: Adiciona `isAdmin` à resposta ---
        snapshot_json = { 
            "ok": True, 
            "slug": snap.slug, 
            "roots": [pid for pid in [snap.root_husband_id, snap.root_wife_id] if pid], 
            "elements": {"nodes": [{"data": n} for n in nodes], "edges": [{"data": e} for e in edges]}, 
            "kinship_path": kinship_path,
            "isAdmin": is_admin
        }
        return jsonify(snapshot_json)
    finally:
        db.close()

@snapshot_bp.get("/snapshot")
def snapshot_list():
    user_fs_id = session.get("user_fs_id");
    if not user_fs_id: return jsonify({"ok": True, "items": []})
    db = SessionLocal()
    try:
        snapshots = db.query(Snapshot).join(Family).join(Membership).filter(Membership.user_fs_id == user_fs_id).order_by(Snapshot.created_at.desc()).all()
        items = [{"slug": s.slug} for s in snapshots]
        return jsonify({"ok": True, "items": items})
    finally:
        db.close()