from __future__ import annotations
import os, json, time, pathlib, logging, requests
from typing import Dict, Any, List, Set, Tuple

API_BASE_URL = os.getenv("FS_API_BASE_URL", "https://apibeta.familysearch.org")

def _h(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

def fs_get_json(token: str, path: str, params: dict | None = None, timeout: int = 20) -> dict:
    url = f"{API_BASE_URL}{path}"
    r = requests.get(url, headers=_h(token), params=params or {}, timeout=timeout)
    if r.status_code != 200:
        raise requests.HTTPError(f"{r.status_code} for {url}")
    return r.json() if r.content else {}

def fetch_person(token: str, pid: str) -> dict:
    # pessoa completa (ok no beta)
    return fs_get_json(token, f"/platform/tree/persons/{pid}")

def fetch_parents(token: str, pid: str) -> List[str]:
    # retorna IDs dos pais (funciona no beta)
    data = fs_get_json(token, f"/platform/tree/persons/{pid}/parents")
    ids: List[str] = []
    for rel in (data.get("childAndParentsRelationships") or []):
        f = rel.get("father") or {}
        m = rel.get("mother") or {}
        if f.get("resourceId"): ids.append(f["resourceId"])
        if m.get("resourceId"): ids.append(m["resourceId"])
    return list(dict.fromkeys(ids))

def fetch_children(token: str, pid: str) -> List[str]:
    # retorna IDs dos filhos (funciona no beta)
    data = fs_get_json(token, f"/platform/tree/persons/{pid}/children")
    ids: List[str] = []
    for rel in (data.get("childAndParentsRelationships") or []):
        c = rel.get("child") or {}
        if c.get("resourceId"): ids.append(c["resourceId"])
    return list(dict.fromkeys(ids))

def fetch_spouses(token: str, pid: str) -> List[str]:
    # spouses via relationships
    data = fs_get_json(token, f"/platform/tree/persons/{pid}/spouses")
    ids: List[str] = []
    for r in (data.get("relationships") or []):
        persons = r.get("persons") or []
        for p in persons:
            rid = p.get("resourceId")
            if rid and rid != pid:
                ids.append(rid)
    return list(dict.fromkeys(ids))

def safe_person_min(person_envelope: dict) -> dict:
    """Extrai um mínimo para snapshot: id, display, facts básicos, names."""
    person = {}
    # envelope pode vir com 'persons' (lista). Pegue a primeira.
    persons = person_envelope.get("persons") or []
    if persons:
        p = persons[0]
    else:
        # em alguns endpoints, já vem no root
        p = person_envelope.get("person") or person_envelope
    person["id"] = p.get("id")
    person["display"] = p.get("display") or {}
    person["names"] = p.get("names") or []
    person["gender"] = p.get("gender") or {}
    person["facts"] = p.get("facts") or []
    person["links"] = p.get("links") or {}
    return person

def clone_couple_snapshot(
    *,
    token: str,
    husband: str | None,
    wife: str | None,
    depth_desc: int = 3,
    depth_asc: int = 1,
    family_slug: str = "default",
) -> Dict[str, Any]:
    """
    Regras MVP:
      - Descendentes do casal: coleta completa até depth_desc.
      - Ancestrais de cada cônjuge: apenas metadados mínimos (até depth_asc).
      - Salva em data/snapshots/<family_slug>/{persons.json, relations.json, meta.json}
    """

    root = pathlib.Path("apps/api/src/data/snapshots") / family_slug
    root.mkdir(parents=True, exist_ok=True)
    persons: Dict[str, dict] = {}
    relations: List[Tuple[str, str, str]] = []  # (type, a, b) types: parent, spouse, child

    seen: Set[str] = set()

    def add_person(pid: str):
        if pid in persons: return
        try:
            env = fetch_person(token, pid)
            persons[pid] = safe_person_min(env)
        except Exception as e:
            logging.warning(f"fetch_person fail {pid}: {e}")

    def add_relation(t: str, a: str, b: str):
        relations.append((t, a, b))

    # 1) Registra casal
    if husband:
        add_person(husband)
    if wife:
        add_person(wife)
    if husband and wife:
        add_relation("spouse", husband, wife)

    # 2) Descendentes em largura a partir do(s) cônjuge(s)
    queue: List[Tuple[str, int]] = []
    for x in filter(None, [husband, wife]):
        queue.append((x, 0))
    while queue:
        pid, d = queue.pop(0)
        if (pid, d) in seen: 
            continue
        seen.add((pid, d))
        add_person(pid)
        # filhos
        if d < depth_desc:
            try:
                kids = fetch_children(token, pid)
                for c in kids:
                    add_person(c)
                    add_relation("parent", pid, c)  # pid -> c
                    queue.append((c, d + 1))
            except Exception as e:
                logging.warning(f"children fail {pid}: {e}")

        # spouse links (não expande spouse em profundidade para evitar explosão)
        try:
            sps = fetch_spouses(token, pid)
            for s in sps:
                add_person(s)
                add_relation("spouse", pid, s)
        except Exception as e:
            logging.warning(f"spouses fail {pid}: {e}")

    # 3) Ancestrais: até depth_asc (bem leve)
    def climb(pid: str, limit: int):
        frontier = [(pid, 0)]
        visited = set([pid])
        while frontier:
            cur, d = frontier.pop(0)
            if d >= limit: 
                continue
            try:
                parents = fetch_parents(token, cur)
                for p in parents:
                    if p not in visited:
                        add_person(p)  # min
                        add_relation("parent", p, cur)  # p -> cur
                        visited.add(p)
                        frontier.append((p, d + 1))
            except Exception as e:
                logging.warning(f"parents fail {cur}: {e}")

    for x in filter(None, [husband, wife]):
        climb(x, depth_asc)

    # 4) Persiste snapshot
    persons_path = root / "persons.json"
    relations_path = root / "relations.json"
    meta_path = root / "meta.json"

    with persons_path.open("w", encoding="utf-8") as f:
        json.dump(persons, f, ensure_ascii=False, indent=2)
    with relations_path.open("w", encoding="utf-8") as f:
        json.dump([{"type": t, "a": a, "b": b} for (t, a, b) in relations], f, ensure_ascii=False, indent=2)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump({
            "family": family_slug,
            "created_at": int(time.time()),
            "husband": husband, "wife": wife,
            "depth_desc": depth_desc, "depth_asc": depth_asc,
            "counts": {"persons": len(persons), "relations": len(relations)}
        }, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "family": family_slug,
        "stats": {"persons": len(persons), "relations": len(relations)},
        "files": {"persons": str(persons_path), "relations": str(relations_path), "meta": str(meta_path)},
    }
