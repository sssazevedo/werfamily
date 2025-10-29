# apps/api/src/infra/familysearch/fs_routes.py - CÓDIGO INTEGRAL ATUALIZADO

import os
import secrets
import logging
import requests
from urllib.parse import urlencode
from flask import Blueprint, request, session, redirect, jsonify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)
fs_bp = Blueprint("fs_bp", __name__)

FAMILYSEARCH_ENV = os.getenv("FAMILYSEARCH_ENV", "beta").lower()
FS_BASE = "https://apibeta.familysearch.org" if FAMILYSEARCH_ENV == "beta" else "https://api.familysearch.org"
CIS_BASE = "https://identbeta.familysearch.org/cis-web/oauth2/v3" if FAMILYSEARCH_ENV == "beta" else "https://ident.familysearch.org/cis-web/oauth2/v3"

APP_KEY = os.getenv("FAMILYSEARCH_APP_KEY", "")
REDIRECT_URI = os.getenv("FAMILYSEARCH_REDIRECT_URI", "https://127.0.0.1:5000/callback")

session_http = requests.Session()
retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(429, 500, 502, 503, 504))
adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
session_http.mount("https://", adapter)

def _auth_headers():
    token = session.get("fs_token")
    if not token: return {}
    return { "Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "weRfamily/1.0" }

def fs_get(path: str, **kwargs) -> requests.Response:
    url = f"{FS_BASE}{path}"; headers = _auth_headers(); headers.update(kwargs.pop("headers", {})); timeout = kwargs.pop("timeout", 15)
    return session_http.get(url, headers=headers, timeout=timeout, **kwargs)

def fs_post(path: str, json=None, data=None, **kwargs) -> requests.Response:
    url = f"{FS_BASE}{path}"; headers = _auth_headers(); headers.update(kwargs.pop("headers", {})); timeout = kwargs.pop("timeout", 15)
    return session_http.post(url, headers=headers, json=json, data=data, timeout=timeout, **kwargs)

def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": APP_KEY,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    return f"{CIS_BASE}/authorization?{urlencode(params)}"

def exchange_code_for_token(code: str) -> dict | None:
    payload = { "grant_type": "authorization_code", "client_id": APP_KEY, "code": code, "redirect_uri": REDIRECT_URI }
    headers = {"Accept": "application/json"}
    
    # <<< GARANTA QUE ESTA LINHA CONTENHA 'verify=False' >>>
    r = session_http.post(f"{CIS_BASE}/token", data=payload, headers=headers, timeout=20, verify=False)
    
    if not r.ok:
        log.error("Token exchange failed: %s %s", r.status_code, r.text)
        return None
    return r.json()