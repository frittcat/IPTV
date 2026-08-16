param(
  [int]$LiveHealth = 100,
  [int]$VodLimit = 20
)

$ErrorActionPreference = 'Stop'

# Keep accented output readable on Windows PowerShell 5.1.
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop não foi encontrado.' }
if (-not (Test-Path '.env')) { throw '.env não encontrado. Execute scripts\install.ps1 primeiro.' }

function Invoke-GaloDoidoPython {
  param(
    [Parameter(Mandatory=$true)][string]$Code,
    [Parameter(Mandatory=$true)][string]$Stage
  )
  docker compose exec -T backend python -c $Code | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "$Stage falhou (exit code $LASTEXITCODE). A sincronização foi interrompida para não mascarar o erro."
  }
}

Write-Host '1/4 Sincronizando catálogo Live público/autorizado (modo rápido em lote)...'
Invoke-GaloDoidoPython -Stage 'Etapa 1/4: catálogo Live' -Code "from backend.live_sync import fast_sync; print(fast_sync())"

Write-Host ''
Write-Host "2/4 Importando até $VodLimit filmes públicos/licenciados do Archive.org..."
Invoke-GaloDoidoPython -Stage 'Etapa 2/4: VOD' -Code "from backend.app import vod_sync; print(vod_sync('archive_org', $VodLimit))"

Write-Host ''
Write-Host "3/4 Testando até $LiveHealth streams Live e os streams VOD importados..."
Invoke-GaloDoidoPython -Stage 'Etapa 3/4: health check' -Code "from backend.health_worker import run_health_batch; print(run_health_batch(live_limit=$LiveHealth, vod_limit=$VodLimit))"

Write-Host ''
Write-Host '4/4 Estatísticas atuais...'
Invoke-GaloDoidoPython -Stage 'Etapa 4/4: estatísticas' -Code "from backend.app import stats; print(stats())"

Write-Host ''
Write-Host 'Sincronização inicial concluída.'
Write-Host 'Na TV, feche e abra novamente o GaloDoidoTV para recarregar a Home.'
