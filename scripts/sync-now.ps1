param(
  [int]$LiveHealth = 300,
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

Write-Host '1/5 Sincronizando catálogo Live BR/PT/FR público/autorizado (modo rápido em lote)...'
Invoke-GaloDoidoPython -Stage 'Etapa 1/5: catálogo Live' -Code "from backend.live_sync import fast_sync; print(fast_sync())"

Write-Host ''
Write-Host "2/5 Importando até $VodLimit filmes públicos/licenciados do Archive.org..."
Invoke-GaloDoidoPython -Stage 'Etapa 2/5: VOD' -Code "from backend.app import vod_sync; print(vod_sync('archive_org', $VodLimit))"

Write-Host ''
Write-Host "3/5 Testando até $LiveHealth streams Live e os streams VOD importados..."
Invoke-GaloDoidoPython -Stage 'Etapa 3/5: health check' -Code "from backend.health_worker import run_health_batch; print(run_health_batch(live_limit=$LiveHealth, vod_limit=$VodLimit))"

Write-Host ''
Write-Host '4/5 Estatísticas atuais...'
Invoke-GaloDoidoPython -Stage 'Etapa 4/5: estatísticas' -Code "from backend.app import stats; print(stats())"

Write-Host ''
Write-Host '5/5 Cobertura da Grade Master Brasil...'
Invoke-GaloDoidoPython -Stage 'Etapa 5/5: cobertura BR' -Code "import json; from backend.live_master_catalog import coverage_report; from backend.app import db_execute; r=coverage_report(db_execute); print(json.dumps({'target':r['target'],'known':r['known'],'playable':r['playable'],'missing_or_unplayable':r['missing_or_unplayable'],'coverage_percent':r['coverage_percent'],'p0_missing':[x['name'] for x in r['items'] if x['priority']=='P0' and not x['playable']]}, ensure_ascii=False, indent=2))"

Write-Host ''
Write-Host 'Sincronização concluída.'
Write-Host 'A Grade Master Brasil permanece como alvo mesmo para canais ainda sem fonte saudável.'
Write-Host 'Na TV, feche e abra novamente o GaloDoidoTV para recarregar o catálogo.'
