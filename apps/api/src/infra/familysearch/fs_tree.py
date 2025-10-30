# apps/api/src/infra/familysearch/fs_tree.py
from __future__ import annotations
import requests
from .fs_client import API_BASE_URL

def load_ancestry(access_token: str, person_id: str, generations: int = 4, details: bool = True):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/x-gedcomx-v1+json",
    }
    params = {"person": person_id, "generations": str(generations)}
    if details:
        params["personDetails"] = "true"
        params["marriageDetails"] = "true"
    url = f"{API_BASE_URL}/platform/tree/ancestry"
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def load_descendancy(access_token: str, person_id: str, generations: int = 2):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/x-gedcomx-v1+json",
    }
    params = {"person": person_id, "generations": str(generations)}
    url = f"{API_BASE_URL}/platform/tree/descendancy"
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()
