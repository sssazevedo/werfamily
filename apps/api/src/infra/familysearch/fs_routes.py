# apps/api/src/infra/familysearch/fs_routes.py - CÓDIGO INTEGRAL ATUALIZADO

import os
import secrets
import logging
import requests
from urllib.parse import urlencode
from flask import Blueprint, request, session, redirect, jsonify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3 # <<< MUDANÇA: Importa urllib3 para ajustes de segurança

# <<< INÍCIO DA CORREÇÃO DE SSL/TLS PARA WINDOWS >>>
# Este bloco força o uso de um conjunto de cifras mais moderno e compatível,
# o que resolve o erro ConnectionResetError (10054) em muitos ambientes Windows.
try:
    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = 'ALL:@SECLEVEL=1'
except AttributeError:
    # A estrutura interna do urllib3 pode mudar. Se o patch acima falhar,
    # ele tentará um método alternativo.
    try:
        import ssl
        from urllib3.contrib.pyopenssl import PyOpenSSLContext
        
        class CustomHttpAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                context = PyOpenSSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.set_ciphers('DEFAULT')
                kwargs['ssl_context'] = context
                return super().init_poolmanager(*args, **kwargs)
        
        # Substitui o adaptador padrão
        session_http = requests.Session()
        session_http.mount('https://', CustomHttpAdapter())
        print("INFO: Usando adaptador HTTP customizado para compatibilidade SSL.")
    except Exception as e:
        print(f"AVISO: Não foi possível aplicar o patch de SSL. Erros de conexão podem ocorrer. Detalhe: {e}")

# Desativa os avisos de segurança sobre certificados não verificados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# <<< FIM DA CORREÇÃO >>>


log = logging.getLogger(__name__)
fs_bp = Blueprint("fs_bp", __name__)

FAMILYSEARCH_ENV = os.getenv("FAMILYSEARCH_ENV", "beta").lower()
FS_BASE = "https://apibeta.familysearch.org" if FAMILYSEARCH_ENV == "beta" else "https://api.familysearch.org"
CIS_BASE = "https://identbeta.familysearch.org/cis-web/oauth2/v3" if FAMILYSEARCH_ENV == "beta" else "https://ident.familysearch.org/cis-web/oauth2/v3"

APP_KEY = os.getenv("FAMILYSEARCH_APP_KEY", "")
REDIRECT_URI = os.getenv("FAMILYSEARCH_REDIRECT_URI", "https://127.0.0.1:5000/callback")

# A configuração de session_http e retries permanece a mesma
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
    
    # A diretiva verify=False continua importante para o dev local
    r = session_http.post(f"{CIS_BASE}/token", data=payload, headers=headers, timeout=20, verify=False)
    
    if not r.ok:
        log.error("Token exchange failed: %s %s", r.status_code, r.text)
        return None
    return r.json()