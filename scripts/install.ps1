$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop não foi encontrado.' }
if (-not (Test-Path '.env')) {
  $postgres = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N').Substring(0,8)
  $adminPassword = [Guid]::NewGuid().ToString('N')
  $salt = New-Object byte[] 16
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($salt)
  } finally {
    $rng.Dispose()
  }
  $iterations = 310000
  $derive = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($adminPassword, $salt, $iterations, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
  try {
    $hash = $derive.GetBytes(32)
  } finally {
    $derive.Dispose()
  }
  $saltHex = ([BitConverter]::ToString($salt)).Replace('-', '').ToLowerInvariant()
  $hashHex = ([BitConverter]::ToString($hash)).Replace('-', '').ToLowerInvariant()
  $encoded = 'pbkdf2_sha256$' + $iterations + '$' + $saltHex + '$' + $hashHex

  $lanIp = $null
  try {
    $candidate = Get-NetIPConfiguration |
      Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
      Select-Object -First 1
    if ($candidate -and $candidate.IPv4Address) {
      $lanIp = $candidate.IPv4Address.IPAddress
    }
  } catch {
    $lanIp = $null
  }
  $publicUrl = if ($lanIp) { "http://${lanIp}:8080" } else { 'http://localhost:8080' }

  @(
    'POSTGRES_DB=familystream'
    'POSTGRES_USER=familystream'
    "POSTGRES_PASSWORD=$postgres"
    'BACKEND_PORT=8080'
    'DISPATCHARR_PORT=9191'
    'HOST_COUNTRY=FR'
    'PUBLISH_MIN_SCORE=60'
    'ADULT_CONTENT=false'
    "GALODOIDOTV_PUBLIC_URL=$publicUrl"
    "FAMILYSTREAM_PUBLIC_URL=$publicUrl"
    'ADMIN_USERNAME=admin'
    ("ADMIN_PASSWORD_HASH='" + $encoded + "'")
    'SCHEDULER_INTERVAL_SECONDS=3600'
  ) | Set-Content -Encoding utf8 '.env'
  Write-Host "Credencial administrativa criada: usuário admin / senha $adminPassword"
  Write-Host "URL LAN detectada: $publicUrl"
}
docker compose pull
docker compose build
docker compose up -d
docker compose ps
Write-Host 'GaloDoidoTV iniciado. Painel: http://localhost:8080/admin/; API: http://localhost:8080/docs; Dispatcharr: http://localhost:9191'
