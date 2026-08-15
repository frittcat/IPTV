$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path 'backups' | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
docker compose exec -T db pg_dump -U ${env:POSTGRES_USER} ${env:POSTGRES_DB} | Out-File -Encoding utf8 "backups/db-$stamp.sql"
Compress-Archive -Path config,data,.env -DestinationPath "backups/familystream-$stamp.zip" -Force
Write-Host "Backup criado em backups/"
