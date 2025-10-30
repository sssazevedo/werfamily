# fs_client.py
from __future__ import annotations
import os, base64, hashlib, secrets
import requests
from urllib.parse import urlencode

DEBUG_FS = os.getenv("FLASK_DEBUG", "0") == "1"

# ========= Config a partir das SUAS variáveis =========

CLIENT_ID     = os.getenv("FAMILYSEARCH_APP_KEY") or ""
REDIRECT_URI  = os.getenv("FAMILYSEARCH_REDIRECT_URI", "https://127.0.0.1:5000/callback")
SCOPE         = "openid profile email"

ENV = os.getenv("FAMILYSEARCH_ENV", "beta").lower()  # 'prod' ou 'beta'

if ENV == "prod":
    AUTH_URL     = "https://ident.familysearch.org/cis-web/oauth2/v3/authorization"
    TOKEN_URL    = "https://ident.familysearch.org/cis-web/oauth2/v3/token"
    API_BASE_URL = "https://api.familysearch.org"
else:
    AUTH_URL     = "https://identbeta.familysearch.org/cis-web/oauth2/v3/authorization"
    TOKEN_URL    = "https://identbeta.familysearch.org/cis-web/oauth2/v3/token"
    API_BASE_URL = "https://apibeta.familysearch.org"


# ========= PKCE =========
def _pkce_pair() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return code_verifier, code_challenge

def auth_headers_from_session():
    from flask import session
    tok = session.get("fs_access_token")
    h = {"Accept": "application/json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h

def build_auth_url(store_code_verifier: callable, state: str | None = None) -> str:
    """
    Gera a URL de autorização e chama store_code_verifier(verifier) para você salvar na session.
    """
    code_verifier, code_challenge = _pkce_pair()
    # salve no lugar que você quiser (tipicamente session['fs_code_verifier'])
    store_code_verifier(code_verifier)

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if state:
        params["state"] = state
    return f"{AUTH_URL}?{urlencode(params)}"

def exchange_code_for_token(code: str, code_verifier: str | None) -> dict | None:
    import requests
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier or "",
    }
    headers = {"Accept": "application/json"}
    r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)
    if r.status_code != 200:
        # LOG para diagnóstico
        try:
            print("[TOKEN ERROR]", r.status_code, r.text[:600], flush=True)
        except Exception:
            pass
        return None
    try:
        return r.json()
    except Exception:
        print("[TOKEN PARSE ERROR]", r.text[:600], flush=True)
        return None


def get_headers(access_token: str | None) -> dict | None:
    if not access_token:
        return None
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
