from flask import Blueprint, jsonify
import json, pathlib

family_view_bp = Blueprint("family_view", __name__)

BASE = pathlib.Path("apps/api/src/data/snapshots")

@family_view_bp.get("/family/<slug>/tree")
def family_tree(slug: str):
    root = BASE / slug
    persons = root / "persons.json"
    relations = root / "relations.json"
    meta = root / "meta.json"
    if not persons.exists():
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({
        "ok": True,
        "family": slug,
        "persons": json.loads(persons.read_text(encoding="utf-8")),
        "relations": json.loads(relations.read_text(encoding="utf-8")) if relations.exists() else [],
        "meta": json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {},
    }), 200

@family_view_bp.get("/family/<slug>/person/<pid>")
def family_person(slug: str, pid: str):
    root = BASE / slug / "persons.json"
    if not root.exists():
        return jsonify({"ok": False, "error": "not_found"}), 404
    persons = json.loads(root.read_text(encoding="utf-8"))
    return jsonify({"ok": True, "person": persons.get(pid)}), 200
