import json
from ..infra.db.sqlite import init_db, db
from ..infra.familysearch.fs_api import get_person, get_children
from ..infra.familysearch.fs_client_helpers import auth_headers_from_session

def _upsert_person(con, fsid: str, person: dict):
    given = surname = birth_date = birth_place = death_date = death_place = sex = None
    # GEDCOM X normalization (simplified)
    persons = person.get('persons')
    if persons:
        target = persons[0]
    else:
        target = person.get('person') or {}

    if target:
        names = target.get('names') or []
        if names:
            # try to get given/surname
            nf = names[0].get('nameForms') or []
            if nf:
                given = nf[0].get('given')
                surname = nf[0].get('surname')
        facts = target.get('facts') or []
        for f in facts:
            typ = f.get('type','')
            if typ.endswith('/birth'):
                birth_date  = (f.get('date') or {}).get('original')
                birth_place = (f.get('place') or {}).get('original')
            if typ.endswith('/death'):
                death_date  = (f.get('date') or {}).get('original')
                death_place = (f.get('place') or {}).get('original')
        g = target.get('gender') or {}
        sex = g.get('type')
        if sex:
            sex = sex.rsplit('/', 1)[-1]

    con.execute("""        INSERT INTO individuals (fsid, given, surname, birth_date, birth_place, death_date, death_place, sex)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fsid) DO UPDATE SET
            given=excluded.given,
            surname=excluded.surname,
            birth_date=excluded.birth_date,
            birth_place=excluded.birth_place,
            death_date=excluded.death_date,
            death_place=excluded.death_place,
            sex=excluded.sex
    """, (fsid, given, surname, birth_date, birth_place, death_date, death_place, sex))

def _link(con, a: str, b: str, rel_type: str):
    con.execute("""
        INSERT OR IGNORE INTO relations (src_fsid, dst_fsid, rel_type) VALUES (?, ?, ?)
    """, (a, b, rel_type))

def load_tree(root_fsid: str, depth: int = 3):
    init_db()
    headers = auth_headers_from_session()
    if "Authorization" not in headers:
        return {"ok": False, "error": "not_authenticated", "msg": "Faça login em /login"}

    visited = set()
    frontier = [(root_fsid, 0)]
    added = {"persons": 0, "relations": 0}

    with db() as con:
        con.execute("INSERT INTO sync_log (root_fsid, action, notes) VALUES (?, 'start', ?)", (root_fsid, f"depth={depth}"))
        while frontier:
            fsid, d = frontier.pop(0)
            if fsid in visited or d > depth:
                continue
            visited.add(fsid)

            # pessoa
            try:
                pdata = get_person(fsid, headers)
                _upsert_person(con, fsid, pdata)
                added["persons"] += 1
            except Exception:
                pass

            if d == depth:
                continue

            # filhos (descendência)
            try:
                cdata = get_children(fsid, headers)
                persons = cdata.get("persons") or []
                children = set()
                for p in persons:
                    pid = p.get("id")
                    if pid and pid != fsid:
                        children.add(pid)
                rels = cdata.get("childAndParentsRelationships") or []
                for rel in rels:
                    child = (rel.get("child") or {}).get("resourceId")
                    if child:
                        children.add(child)

                for child_id in children:
                    _link(con, fsid, child_id, "parent")
                    _link(con, child_id, fsid, "child")
                    frontier.append((child_id, d+1))
                    added["relations"] += 2
            except Exception:
                pass

        con.execute("INSERT INTO sync_log (root_fsid, action, notes) VALUES (?, 'finish', ?)", (root_fsid, json.dumps(added)))
        con.commit()

    return {"ok": True, "root": root_fsid, "depth": depth, "stats": added}
