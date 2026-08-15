$ErrorActionPreference = 'Stop'
git pull --ff-only
docker compose pull
docker compose build --pull
docker compose up -d
