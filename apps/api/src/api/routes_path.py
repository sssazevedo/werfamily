from flask import Blueprint, request, jsonify
from ..services.pathfinder import rf_path_unauth, build_path_details_from_ids
from ..infra.familysearch.fs_client_helpers import auth_headers_from_session
from ..infra.familysearch.fs_api import get_person_with_relatives

from collections import deque

path_bp = Blueprint("path", __name__)

def _neighbors(person_id: str, headers: dict) -> set[str]:
    """
    Lê /platform/tree/persons/{id}/relationships e devolve um conjunto de vizinhos (pais, filhos, cônjuges).
    """
    try:
        rel = get_person_with_relatives(person_id, headers)
    except Exception:
        return set()

    nbrs = set()

    # persons[] pode já conter pais/cônjuges/filhos.
    persons = rel.get("persons") or []
    for p in persons:
        pid = p.get("id")
        if pid and pid != person_id:
            nbrs.add(pid)

    # childAndParentsRelationships[] traz filhos e pais
    caps = rel.get("childAndParentsRelationships") or []
    for r in caps:
        c = (r.get("child") or {}).get("resourceId")
        f = (r.get("father") or {}).get("resourceId")
        m = (r.get("mother") or {}).get("resourceId")
        for pid in (c, f, m):
            if pid and pid != person_id:
                nbrs.add(pid)

    # coupleRelationships[] traz cônjuges
    couples = rel.get("coupleRelationships") or []
    for cr in couples:
        p1 = (cr.get("person1") or {}).get("resourceId")
        p2 = (cr.get("person2") or {}).get("resourceId")
        for pid in (p1, p2):
            if pid and pid != person_id:
                nbrs.add(pid)

    return nbrs

def _bfs_path(src: str, dst: str, headers: dict, max_depth: int = 6) -> list[str] | None:
    """
    BFS simples sobre o grafo de relacionamentos do FS (pais/filhos/cônjuges).
    Limite de profundidade para evitar explosão de chamadas.
    """
    if src == dst:
        return [src]

    visited = {src}
    parent = {}
    q = deque()
    q.append((src, 0))

    while q:
        u, d = q.popleft()
        if d >= max_depth:
            continue
        for v in _neighbors(u, headers):
            if v in visited:
                continue
            visited.add(v)
            parent[v] = u
            if v == dst:
                # reconstrói caminho
                path = [v]
                while path[-1] != src:
                    path.append(parent[path[-1]])
                path.reverse()
                return path
            q.append((v, d + 1))
    return None

@path_bp.get("/path")
def path():
    p1 = (request.args.get("from") or "").strip().upper()
    p2 = (request.args.get("to")   or "").strip().upper()
    if not p1 or not p2:
        return jsonify({"ok": False, "error":"from/to required"}), 400

    # 1) tenta Relationship Finder público (rápido)
    rf = rf_path_unauth(p1, p2)
    if rf.get("ok"):
        headers = auth_headers_from_session()
        details = build_path_details_from_ids(rf["ids"], rf["common"], headers)
        return jsonify({"ok": True, "method": "rf_public", "path": details}), 200

    # 2) fallback BFS autenticado
    headers = auth_headers_from_session()
    if "Authorization" not in headers:
        # sem token, devolve o motivo do RF e pede login
        return jsonify({"ok": False, "method": "rf_public", "reason": rf.get("reason", "no_path"), "hint": "Faça login em /login para tentar o fallback BFS"}), 404

    ids = _bfs_path(p1, p2, headers, max_depth=6)
    if ids:
        details = build_path_details_from_ids(ids, common_id=None, headers=headers)
        return jsonify({"ok": True, "method": "bfs_auth", "path": details}), 200

    return jsonify({"ok": False, "method": "bfs_auth", "reason": "no_path_within_depth", "max_depth": 6}), 404
