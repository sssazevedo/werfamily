import requests
from .fs_client_helpers import API_BASE_URL

def get_person(person_id: str, headers: dict) -> dict:
    r = requests.get(f"{API_BASE_URL}/platform/tree/persons/{person_id}", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def get_person_with_relatives(person_id: str, headers: dict) -> dict:
    r = requests.get(f"{API_BASE_URL}/platform/tree/persons/{person_id}/relationships", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def get_children(person_id: str, headers: dict) -> dict:
    r = requests.get(f"{API_BASE_URL}/platform/tree/persons/{person_id}/children", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()
