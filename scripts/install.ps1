$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop não foi encontrado.' }
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
docker compose pull
docker compose build
docker compose up -d
docker compose ps
Write-Host 'FamilyStream iniciado. Backend: http://localhost:8080/docs; Dispatcharr: http://localhost:9191'
