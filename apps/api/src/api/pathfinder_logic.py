# apps/api/src/api/pathfinder_logic.py
from __future__ import annotations
import os
import time
import requests
from collections import deque, OrderedDict
from typing import Any, Dict, List, Tuple, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Tenta importar a URL base da sua infraestrutura
try:
    from ..infra.familysearch.fs_routes import FS_BASE as API_BASE_URL
except (ModuleNotFoundError, ImportError):
    API_BASE_URL = "https://apibeta.familysearch.org"

# --- Configuração de HTTP e Cache (adaptado do pathfinder.py) ---

session_http = requests.Session()
retries = Retry(total=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504))
adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=retries)
session_http.mount("https://", adapter)
DEFAULT_TIMEOUT = 10

class TTLCache:
    def __init__(self, ttl=900, max_items=2000):
        self.ttl = ttl
        self.max = max_items
        self.data = OrderedDict()

    def get(self, key):
        if key in self.data:
            ts, val = self.data[key]
            if time.time() - ts < self.ttl:
                self.data.move_to_end(key)
                return val
            else:
                del self.data[key]
        return None

    def set(self, key, value):
        self.data[key] = (time.time(), value)
        self.data.move_to_end(key)
        if len(self.data) > self.max:
            self.data.popitem(last=False)

_person_cache = TTLCache()

def _get_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "WeRfamily-Pathfinder/1.0",
    }

def _get_person_with_parents(token: str, person_id: str) -> Tuple[List[str], bool]:
    """
    Versão simplificada que busca apenas os pais de uma pessoa.
    Retorna (lista_de_pais, sucesso).
    """
    cached = _person_cache.get(person_id)
    if cached is not None:
        return cached

    url = f"{API_BASE_URL}/platform/tree/persons/{person_id}"
    try:
        r = session_http.get(url, headers=_get_headers(token), timeout=DEFAULT_TIMEOUT)
        if r.status_code != 200:
            _person_cache.set(person_id, ([], False))
            return [], False
        
        data = r.json()
        parents = set()
        for rel in data.get("childAndParentsRelationships", []):
            child_ref = (rel.get("child") or {}).get("resourceId")
            if child_ref == person_id:
                if p1 := (rel.get("parent1") or {}).get("resourceId"): parents.add(p1)
                if p2 := (rel.get("parent2") or {}).get("resourceId"): parents.add(p2)
        
        result = (list(parents), True)
        _person_cache.set(person_id, result)
        return result
    except requests.RequestException:
        _person_cache.set(person_id, ([], False))
        return [], False

def _find_paths_bfs(start_pid: str, end_pid: str, token: str, max_depth: int = 20) -> List[List[str]]:
    """
    Lógica de busca bidirecional (BFS) adaptada do pathfinder.py.
    Retorna uma lista de caminhos encontrados.
    """
    q1, q2 = deque([(start_pid, [start_pid])]), deque([(end_pid, [end_pid])])
    visited1, visited2 = {start_pid: [start_pid]}, {end_pid: [end_pid]}
    
    paths_found = []
    depth = 0

    while q1 and q2 and depth < max_depth and not paths_found:
        depth += 1
        
        # Expande a partir do início (start_pid)
        q_size = len(q1)
        for _ in range(q_size):
            curr_id, path = q1.popleft()
            parent_ids, ok = _get_person_with_parents(token, curr_id)
            if not ok: continue

            for parent_id in parent_ids:
                if parent_id in visited1: continue
                new_path = path + [parent_id]
                visited1[parent_id] = new_path
                
                if parent_id in visited2: # Encontro!
                    path2 = visited2[parent_id]
                    paths_found.append(new_path + path2[::-1][1:])
                
                q1.append((parent_id, new_path))
        
        if paths_found: break

        # Expande a partir do fim (end_pid)
        q_size = len(q2)
        for _ in range(q_size):
            curr_id, path = q2.popleft()
            parent_ids, ok = _get_person_with_parents(token, curr_id)
            if not ok: continue

            for parent_id in parent_ids:
                if parent_id in visited2: continue
                new_path = path + [parent_id]
                visited2[parent_id] = new_path

                if parent_id in visited1: # Encontro!
                    path1 = visited1[parent_id]
                    paths_found.append(path1 + new_path[::-1][1:])
                
                q2.append((parent_id, new_path))
        
        if paths_found: break
        
    return paths_found

# --- FUNÇÃO PRINCIPAL EXPOSTA PELO MÓDULO ---

def find_kinship_path(start_pid: str, end_pid: str, token: str) -> Optional[List[str]]:
    """
    Encontra o caminho de parentesco mais curto entre duas pessoas.
    
    Args:
        start_pid: O PID do usuário (ponto de partida).
        end_pid: O PID do ancestral (ponto de chegada).
        token: O token de acesso do FamilySearch.
    
    Returns:
        Uma lista de PIDs representando o caminho (incluindo início e fim),
        ou None se nenhum caminho for encontrado.
    """
    if start_pid == end_pid:
        return [start_pid]
        
    paths = _find_paths_bfs(start_pid, end_pid, token)

    if not paths:
        return None

    # Ordena os caminhos encontrados pelo mais curto e retorna o primeiro
    paths.sort(key=len)
    return paths[0]