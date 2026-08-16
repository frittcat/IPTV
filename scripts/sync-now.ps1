param(
  [int]$LiveHealth = 300,
  [int]$VodLimit = 20
)

$ErrorActionPreference = 'Stop'

# Keep UTF-8 output readable on Windows PowerShell 5.1. The script's own
# messages intentionally stay ASCII because PS 5.1 can misread UTF-8 files
# without a BOM.
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop nao foi encontrado.' }
if (-not (Test-Path '.env')) { throw '.env nao encontrado. Execute scripts\install.ps1 primeiro.' }

function Invoke-GaloDoidoPython {
  param(
    [Parameter(Mandatory=$true)][string]$Code,
    [Parameter(Mandatory=$true)][string]$Stage
  )
  docker compose exec -T backend python -c $Code | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "$Stage falhou (exit code $LASTEXITCODE). A sincronizacao foi interrompida para nao mascarar o erro."
  }
}

Write-Host '1/5 Sincronizando catalogo Live BR/PT/FR publico/autorizado (modo rapido em lote)...'
Invoke-GaloDoidoPython -Stage 'Etapa 1/5: catalogo Live' -Code "from backend.live_sync import fast_sync; print(fast_sync())"

Write-Host ''
Write-Host '1b/5 Verificando fonte Live autorizada configurada localmente...'
Invoke-GaloDoidoPython -Stage 'Etapa 1b/5: fonte Live autorizada' -Code "from providers.xtream_live import sync_xtream_live; from backend.app import db_execute, now; print(sync_xtream_live(db_execute, now))"

Write-Host ''
Write-Host "2/5 Importando ate $VodLimit filmes publicos/licenciados do Archive.org..."
try {
  Invoke-GaloDoidoPython -Stage 'Etapa 2/5: VOD' -Code "from backend.app import vod_sync; print(vod_sync('archive_org', $VodLimit))"
}
catch {
  Write-Warning 'Etapa 2/5: Archive.org indisponivel. O VOD e opcional para este levantamento; continuando com Live e cobertura BR.'
}

Write-Host ''
Write-Host "3/5 Testando ate $LiveHealth streams Live e os streams VOD importados..."
Invoke-GaloDoidoPython -Stage 'Etapa 3/5: health check' -Code "from backend.health_worker import run_health_batch; print(run_health_batch(live_limit=$LiveHealth, vod_limit=$VodLimit))"

Write-Host ''
Write-Host '4/5 Estatisticas atuais...'
Invoke-GaloDoidoPython -Stage 'Etapa 4/5: estatisticas' -Code "from backend.app import stats; print(stats())"

Write-Host ''
Write-Host '5/5 Cobertura da Grade Master Brasil...'
Invoke-GaloDoidoPython -Stage 'Etapa 5/5: cobertura BR' -Code "import json; from backend.live_master_catalog import coverage_report; from backend.app import db_execute; r=coverage_report(db_execute); p0=[{'name':x['name'],'state':x['state'],'sources':x['source_count'],'healthy_sources':x['healthy_sources']} for x in r['items'] if x['priority']=='P0' and not x['playable']]; print(json.dumps({'target':r['target'],'known':r['known'],'with_source':r['with_source'],'healthy':r['healthy'],'playable':r['playable'],'missing_or_unplayable':r['missing_or_unplayable'],'coverage_percent':r['coverage_percent'],'states':r['states'],'p0_missing':p0}, ensure_ascii=False, indent=2))"

Write-Host ''
Write-Host 'Sincronizacao concluida.'
Write-Host 'A Grade Master Brasil permanece como alvo mesmo para canais ainda sem fonte saudavel.'
Write-Host 'Credenciais de fontes autorizadas ficam somente no .env local e nunca devem ser enviadas ao GitHub.'
Write-Host 'Na TV, feche e abra novamente o GaloDoidoTV para recarregar o catalogo.'
