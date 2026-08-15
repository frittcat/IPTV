$ErrorActionPreference = 'Stop'
docker compose exec backend python -m pytest -q
Invoke-RestMethod http://localhost:8080/health
