# Optional Windows fallback when Docker is unavailable. Uses EDB binaries, no service registration.
param([string]$BinPath = "$PSScriptRoot/../.local/pgsql/bin")
$ErrorActionPreference = 'Stop'
$rootPath = [IO.Path]::GetFullPath("$PSScriptRoot/..")
$localPath = Join-Path $rootPath '.local'
$dataPath = Join-Path $localPath 'pgdata'
$envPath = Join-Path $rootPath '.env'
if (-not (Test-Path -LiteralPath "$BinPath/initdb.exe")) { throw 'Extract the documented EDB PostgreSQL archive into .local first.' }
if (-not (Test-Path -LiteralPath $envPath)) { throw 'Run python scripts/init_env.py --without-redis first.' }
$passwordLine = Get-Content -LiteralPath $envPath | Where-Object { $_.StartsWith('POSTGRES_PASSWORD=') }
$dbPassword = $passwordLine.Substring('POSTGRES_PASSWORD='.Length)
if (-not $dbPassword) { throw 'POSTGRES_PASSWORD must be set in .env.' }
New-Item -ItemType Directory -Path $localPath -Force | Out-Null
if (-not (Test-Path -LiteralPath "$dataPath/PG_VERSION")) {
    $passwordPath = Join-Path $localPath 'pg-init-password'
    [IO.File]::WriteAllText($passwordPath, $dbPassword, [Text.UTF8Encoding]::new($false))
    try {
        & "$BinPath/initdb.exe" -D $dataPath -U computer --auth=scram-sha-256 --encoding=UTF8 --locale=C --pwfile=$passwordPath
        if ($LASTEXITCODE -ne 0) { throw 'initdb failed.' }
    } finally { Remove-Item -LiteralPath $passwordPath -ErrorAction SilentlyContinue }
}
& "$BinPath/pg_ctl.exe" -D $dataPath status *> $null
if ($LASTEXITCODE -ne 0) {
    & "$BinPath/pg_ctl.exe" -D $dataPath -l "$localPath/postgres.log" -o '-h 127.0.0.1 -p 55432' -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL start failed; inspect .local/postgres.log.' }
}
$previousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $dbPassword
    foreach ($dbName in @('computer', 'test_computer')) {
        $exists = & "$BinPath/psql.exe" -h 127.0.0.1 -p 55432 -U computer -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$dbName'"
        if ($LASTEXITCODE -ne 0) { throw 'Database connection failed.' }
        if ($exists -ne '1') {
            & "$BinPath/createdb.exe" -h 127.0.0.1 -p 55432 -U computer $dbName
            if ($LASTEXITCODE -ne 0) { throw "Cannot create $dbName." }
        }
    }
} finally { $env:PGPASSWORD = $previousPassword }
Write-Output 'Local PostgreSQL ready at 127.0.0.1:55432; no system service registered.'
