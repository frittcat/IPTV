param(
  [int]$LiveHealth = 100,
  [int]$VodLimit = 20
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop não foi encontrado.' }
if (-not (Test-Path '.env')) { throw '.env não encontrado. Execute scripts\install.ps1 primeiro.' }

Write-Host '1/4 Sincronizando catálogo Live público/autorizado (modo rápido em lote)...'
docker compose exec -T backend python -c "from backend.live_sync import fast_sync; print(fast_sync())" | Out-Host

Write-Host ''
Write-Host "2/4 Importando até $VodLimit filmes públicos/licenciados do Archive.org..."
docker compose exec -T backend python -c "from backend.app import vod_sync; print(vod_sync('archive_org', $VodLimit))" | Out-Host

Write-Host ''
Write-Host "3/4 Testando até $LiveHealth streams Live e os streams VOD importados..."
docker compose exec -T backend python -c "from backend.health_worker import run_health_batch; print(run_health_batch(live_limit=$LiveHealth, vod_limit=$VodLimit))" | Out-Host

Write-Host ''
Write-Host '4/4 Estatísticas atuais...'
docker compose exec -T backend python -c "from backend.app import stats; print(stats())" | Out-Host

Write-Host ''
Write-Host 'Sincronização inicial concluída.'
Write-Host 'Na TV, feche e abra novamente o FamilyStream para recarregar a Home.'
