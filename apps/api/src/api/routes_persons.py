from flask import Blueprint, request, jsonify, session
from ..infra.familysearch.fs_search import search_persons

persons_bp = Blueprint("persons", __name__)

@persons_bp.get("/persons/search")
def persons_search():
    # parâmetros de query (ex.: ?given=Maria&surname=Silva&year=1900&place=Alagoas&count=25)
    given   = request.args.get("given") or None
    surname = request.args.get("surname") or None
    place   = request.args.get("place") or request.args.get("birth_place") or None
    year_str = request.args.get("year") or request.args.get("birth_year") or None
    count_str = request.args.get("count") or None

    # normaliza tipos
    birth_year = int(year_str) if year_str and year_str.isdigit() else None
    try:
        count = int(count_str) if count_str else 50
    except ValueError:
        count = 50

    # precisa estar logado (token na sessão)
    access_token = session.get("fs_access_token")
    if not access_token:
        return jsonify({"ok": False, "error": "not_authenticated", "msg": "Faça login em /login"}), 401

    # chama seu wrapper com a assinatura correta
    data = search_persons(
        access_token,
        given=given,
        surname=surname,
        birth_year=birth_year,
        birth_place=place,
        count=count,
    )
    return jsonify({"ok": True, "data": data}), 200
