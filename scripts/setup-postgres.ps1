# One-time local PostgreSQL setup for ai-equity-trader.
# Run in PowerShell as Administrator (required: it restarts the postgresql-x64-16
# service and briefly relaxes local auth to set passwords, then locks it back down).
#
# Creates: postgres superuser password, `trader` role, `ai_equity_trader` database.
# Matches the credentials already in .env.example / docker-compose.yml.

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Not running as Administrator. Close this window, right-click PowerShell (or Windows Terminal) and choose 'Run as administrator', then re-run this script."
    exit 1
}

$pgData = "C:\Program Files\PostgreSQL\16\data"
$pgBin  = "C:\Program Files\PostgreSQL\16\bin"
$hba    = Join-Path $pgData "pg_hba.conf"
$hbaBak = Join-Path $pgData "pg_hba.conf.bak"

if (Test-Path $hbaBak) {
    Write-Output "1. Backup already exists (from an earlier interrupted run) - reusing it instead of overwriting."
} else {
    Write-Output "1. Backing up pg_hba.conf..."
    Copy-Item $hba $hbaBak -Force
}

Write-Output "2. Temporarily allowing trust auth for local connections..."
(Get-Content $hba) | ForEach-Object {
    $_ -replace '^(local\s+all\s+all\s+)scram-sha-256$', '$1trust' `
       -replace '^(host\s+all\s+all\s+127\.0\.0\.1/32\s+)scram-sha-256$', '$1trust' `
       -replace '^(host\s+all\s+all\s+::1/128\s+)scram-sha-256$', '$1trust'
} | Set-Content $hba

Write-Output "3. Restarting PostgreSQL service..."
Restart-Service postgresql-x64-16 -Force
Start-Sleep -Seconds 3

Write-Output "4. Setting postgres password and creating trader role + database..."
Write-Output "   (If you're re-running this, 'role/database already exists' errors below are harmless.)"
& "$pgBin\psql.exe" -U postgres -h localhost -c "ALTER USER postgres WITH PASSWORD 'postgres';"
& "$pgBin\psql.exe" -U postgres -h localhost -c "CREATE ROLE trader LOGIN PASSWORD 'trader';"
& "$pgBin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE ai_equity_trader OWNER trader;"

Write-Output "5. Restoring secure auth (scram-sha-256)..."
Copy-Item $hbaBak $hba -Force
Remove-Item $hbaBak -Force

Write-Output "6. Restarting PostgreSQL service to re-lock..."
Restart-Service postgresql-x64-16 -Force
Start-Sleep -Seconds 3

Write-Output "7. Verifying trader can connect..."
$env:PGPASSWORD = "trader"
& "$pgBin\psql.exe" -U trader -h localhost -d ai_equity_trader -c "SELECT current_database(), current_user;"
Remove-Item Env:\PGPASSWORD

Write-Output ""
Write-Output "Done. PostgreSQL is ready at localhost:5432 (db=ai_equity_trader, user=trader, password=trader)."
