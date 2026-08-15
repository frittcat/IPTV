$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop não foi encontrado.' }
if (-not (Test-Path '.env')) {
  $postgres = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N').Substring(0,8)
  $adminPassword = [Guid]::NewGuid().ToString('N')
  $salt = New-Object byte[] 16
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($salt)
  $iterations = 310000
  $derive = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($adminPassword, $salt, $iterations, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
  $hash = $derive.GetBytes(32)
  $encoded = 'pbkdf2_sha256$' + $iterations + '$' + ([Convert]::ToHexString($salt).ToLower()) + '$' + ([Convert]::ToHexString($hash).ToLower())
  @(
    'POSTGRES_DB=familystream'
    'POSTGRES_USER=familystream'
    "POSTGRES_PASSWORD=$postgres"
    'BACKEND_PORT=8080'
    'DISPATCHARR_PORT=9191'
    'HOST_COUNTRY=FR'
    'PUBLISH_MIN_SCORE=60'
    'ADULT_CONTENT=false'
    'FAMILYSTREAM_PUBLIC_URL=http://localhost:8080'
    'ADMIN_USERNAME=admin'
    "ADMIN_PASSWORD_HASH=$encoded"
    'SCHEDULER_INTERVAL_SECONDS=3600'
  ) | Set-Content -Encoding utf8 '.env'
  Write-Host "Credencial administrativa criada: usuário admin / senha $adminPassword"
}
docker compose pull
docker compose build
docker compose up -d
docker compose ps
Write-Host 'FamilyStream iniciado. Painel: http://localhost:8080/admin/; API: http://localhost:8080/docs; Dispatcharr: http://localhost:9191'
