param(
  [string]$ServerIp = ''
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path '.env')) { throw '.env não encontrado. Execute scripts\install.ps1 primeiro.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop não foi encontrado.' }

if ([string]::IsNullOrWhiteSpace($ServerIp)) {
  $candidate = Get-NetIPConfiguration |
    Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
    Select-Object -First 1
  if ($candidate -and $candidate.IPv4Address) {
    $ServerIp = $candidate.IPv4Address.IPAddress
  }
}

if ([string]::IsNullOrWhiteSpace($ServerIp)) {
  throw 'Não foi possível detectar o IPv4 LAN. Execute novamente com -ServerIp 192.168.x.x.'
}

$publicUrl = "http://${ServerIp}:8080"
$lines = Get-Content '.env'
$foundNew = $false
$foundLegacy = $false
$updated = foreach ($line in $lines) {
  if ($line -match '^GALODOIDOTV_PUBLIC_URL=') {
    $foundNew = $true
    "GALODOIDOTV_PUBLIC_URL=$publicUrl"
  } elseif ($line -match '^FAMILYSTREAM_PUBLIC_URL=') {
    $foundLegacy = $true
    "FAMILYSTREAM_PUBLIC_URL=$publicUrl"
  } else {
    $line
  }
}
if (-not $foundNew) { $updated += "GALODOIDOTV_PUBLIC_URL=$publicUrl" }
if (-not $foundLegacy) { $updated += "FAMILYSTREAM_PUBLIC_URL=$publicUrl" }
$updated | Set-Content -Encoding utf8 '.env'

docker compose up -d --force-recreate backend scheduler | Out-Host
Write-Host ''
Write-Host "GaloDoidoTV LAN configurado em: $publicUrl"
Write-Host "Teste em outro dispositivo: $publicUrl/health"
