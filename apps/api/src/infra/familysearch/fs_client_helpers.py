import os
from flask import session
from .fs_client import API_BASE_URL

def get_api_base_url() -> str:
    env = os.getenv("FAMILYSEARCH_ENV", "beta").lower()
    return "https://apibeta.familysearch.org" if env != "prod" else "https://api.familysearch.org"

API_BASE_URL = get_api_base_url()

def auth_headers_from_session():
    tok = session.get("fs_access_token")
    h = {"Accept": "application/json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h
