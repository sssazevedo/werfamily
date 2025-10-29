# WeRfamily

Plataforma para conectar familiares a partir de um casal ancestral no FamilySearch, criando uma árvore privada e um portal de interação com Pathfinder.

## Como rodar (dev rápido)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_APP=apps/api/src/main.py  # Windows PowerShell: $env:FLASK_APP='apps/api/src/main.py'
flask run --host 0.0.0.0 --port 5000
```

Endpoints iniciais:
- GET /healthz
- GET /auth/fs/login
- GET /auth/fs/callback
- GET /path?from=<PID>&to=<PID>
- POST /tree/load?fsid=<ROOT_FSID>&depth=<N>
