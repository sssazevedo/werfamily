# fs_matcher.py
from __future__ import annotations
import unicodedata, re
from typing import Tuple, Dict, Any

try:
    from rapidfuzz import fuzz
except ImportError:
    # fallback simples se RapidFuzz não estiver instalado
    def _ratio(a: str, b: str) -> float:
        a = a or ""; b = b or ""
        if not a and not b:
            return 100.0
        inter = len(set(a.split()) & set(b.split()))
        uni   = len(set(a.split()) | set(b.split())) or 1
        return 100.0 * inter / uni
    class fuzz:
        token_set_ratio = staticmethod(_ratio)
        token_sort_ratio = staticmethod(_ratio)

LIGACAO = {"d","da","das","de","do","dos"}

def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    tokens = [t for t in re.sub(r"[^a-z\s]"," ", s).split() if t not in LIGACAO]
    return " ".join(tokens)

def _year(date_str: str) -> int | None:
    if not date_str:
        return None
    m = re.search(r"\b(1[6-9]\d{2}|20\d{2})\b", date_str)
    return int(m.group(1)) if m else None

def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(_norm(a), _norm(b)) / 100.0

def _sim_surname(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_sort_ratio(_norm(a), _norm(b)) / 100.0

def score_person(local: Dict[str, Any], fs_person: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    local: given_name, surname, birth_date, birth_place, father_name, mother_name, spouse_name, gender
    fs_person: flatten do FS (given_name, surname, birth_year, birth_place, father_name, mother_name, spouse_name, gender)
    """
    exp: Dict[str, Any] = {}

    if local.get("gender") and fs_person.get("gender"):
        if _norm(local["gender"]) and _norm(fs_person["gender"]) and _norm(local["gender"]) != _norm(fs_person["gender"]):
            return 0.0, {"reason": "gender_mismatch"}

    sg = _sim(local.get("given_name",""), fs_person.get("given_name",""))
    ss = _sim_surname(local.get("surname",""), fs_person.get("surname",""))
    exp["name_given"] = sg
    exp["name_surname"] = ss

    y_loc = _year(local.get("birth_date",""))
    y_fs  = fs_person.get("birth_year")
    if y_loc and y_fs is not None:
        diff = abs(y_loc - y_fs)
        sy = max(0.0, 1.0 - (diff / 3.0))
    else:
        sy = 0.0
    exp["birth_year"] = sy

    sp = _sim(local.get("birth_place",""), fs_person.get("birth_place",""))
    exp["birth_place"] = sp

    rel_scores = []
    for lk, fk in [("father_name","father_name"),("mother_name","mother_name"),("spouse_name","spouse_name")]:
        rel_scores.append(_sim(local.get(lk,""), fs_person.get(fk,"")))
    positives = [x for x in rel_scores if x > 0]
    sr = sum(positives)/len(positives) if positives else 0.0
    exp["relatives"] = sr

    score = 0.35*sg + 0.25*ss + 0.15*sy + 0.10*sp + 0.15*sr
    if ss == 1.0:
        score = min(1.0, score + 0.05)
    return score, exp
