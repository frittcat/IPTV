$ErrorActionPreference = 'Stop'

if (-not (Test-Path '.env')) { throw '.env não encontrado. Execute scripts\install.ps1 primeiro.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop não foi encontrado.' }

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
$newLine = "ADMIN_PASSWORD_HASH='" + $encoded + "'"

$lines = Get-Content '.env'
$found = $false
$updated = foreach ($line in $lines) {
  if ($line -match '^ADMIN_PASSWORD_HASH=') {
    $found = $true
    $newLine
  } else {
    $line
  }
}
if (-not $found) { $updated += $newLine }
$updated | Set-Content -Encoding utf8 '.env'

docker compose up -d --force-recreate backend scheduler | Out-Host
Write-Host ''
Write-Host 'Credencial administrativa redefinida:'
Write-Host '  usuário: admin'
Write-Host "  senha:   $adminPassword"
Write-Host ''
Write-Host 'Guarde esta senha; ela não pode ser recuperada depois a partir do hash.'
