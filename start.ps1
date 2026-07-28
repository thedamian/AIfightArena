#!/usr/bin/env pwsh
# Bring up both processes: the arena and the lobby.
param()

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is required but not found on PATH. Install it from https://docs.astral.sh/uv/"
    exit 1
}

if (-not (Test-Path .venv)) {
    Write-Host "Setting up .venv ..."
    uv venv .venv
}

# Reconcile dependencies even when .venv already exists. This is quick when
# requirements are already installed and prevents an incomplete environment
# from making both servers exit immediately.
uv pip install --python .venv\Scripts\python.exe -q -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "uv could not install the project's dependencies."
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env — add your OPENAI_API_KEY to it."
}

$gamePort = 8000
$lobbyPort = 8100
$lobbyPublicHost = ""
if (Test-Path .env) {
    foreach ($line in Get-Content .env) {
        if ($line -match '^GAME_PORT=(\d+)') { $gamePort = [int]$matches[1] }
        if ($line -match '^LOBBY_PORT=(\d+)') { $lobbyPort = [int]$matches[1] }
        if ($line -match '^LOBBY_PUBLIC_HOST=(.+)$') { $lobbyPublicHost = $matches[1].Trim() }
    }
}

New-Item -ItemType Directory -Force -Path runtime | Out-Null

# Launch both servers as background processes so they keep running even if
# this script's runspace is idle. Output is redirected to runtime/*.log and
# tailed below so prefixes match the original shell script.
$gameOutLog = Join-Path runtime game.out.log
$gameErrLog = Join-Path runtime game.err.log
$lobbyOutLog = Join-Path runtime lobby.out.log
$lobbyErrLog = Join-Path runtime lobby.err.log

Remove-Item $gameOutLog, $gameErrLog, $lobbyOutLog, $lobbyErrLog -Force -ErrorAction SilentlyContinue

$gameProc = Start-Process -FilePath uv -ArgumentList "run", "python", "-m", "game_app.server" `
    -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $gameOutLog -RedirectStandardError $gameErrLog -PassThru

$lobbyProc = Start-Process -FilePath uv -ArgumentList "run", "python", "-m", "web_app.server" `
    -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $lobbyOutLog -RedirectStandardError $lobbyErrLog -PassThru

Start-Sleep -Seconds 2

if (-not $lobbyPublicHost) {
    $lobbyPublicHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'
    } | Select-Object -First 1).IPAddress
}
if (-not $lobbyPublicHost) { $lobbyPublicHost = "localhost" }

Write-Host @"

  AI FIGHT ARENA

  Main screen (put this on the TV)    http://localhost:${gamePort}
    Lobby (players join on their phone) http://${lobbyPublicHost}:${lobbyPort}

  Fighter scripts live in ./player — add, edit or delete them while a match
  is running and the arena keeps up.

  Ctrl-C to stop both.

"@

# Tail the log files with prefixes until the user hits Ctrl-C or a server dies.
function New-LogReader($path) {
    if (-not (Test-Path $path)) { New-Item -ItemType File -Path $path | Out-Null }

    $fileStream = [System.IO.FileStream]::new(
        $path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    [System.IO.StreamReader]::new($fileStream)
}

$streams = @{
    gameOut = New-LogReader $gameOutLog
    gameErr = New-LogReader $gameErrLog
    lobbyOut = New-LogReader $lobbyOutLog
    lobbyErr = New-LogReader $lobbyErrLog
}

try {
    while (-not $gameProc.HasExited -and -not $lobbyProc.HasExited) {
        $line = $streams.gameOut.ReadLine()
        if ($null -ne $line) { Write-Host "[game ] $line" }

        $line = $streams.gameErr.ReadLine()
        if ($null -ne $line) { Write-Host "[game!] $line" }

        $line = $streams.lobbyOut.ReadLine()
        if ($null -ne $line) { Write-Host "[lobby] $line" }

        $line = $streams.lobbyErr.ReadLine()
        if ($null -ne $line) { Write-Host "[lobby!] $line" }

        Start-Sleep -Milliseconds 100
    }

    # A server exited. Print its complete logs so the failure is visible rather
    # than silently returning after the banner.
    if ($gameProc.HasExited) {
        Write-Host "Game server exited with code $($gameProc.ExitCode)."
        Get-Content $gameOutLog, $gameErrLog -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "[game ] $_" }
    }
    if ($lobbyProc.HasExited) {
        Write-Host "Lobby server exited with code $($lobbyProc.ExitCode)."
        Get-Content $lobbyOutLog, $lobbyErrLog -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "[lobby] $_" }
    }

    exit 1
} finally {
    Stop-Process -Id $gameProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $lobbyProc.Id -Force -ErrorAction SilentlyContinue
    $streams.gameOut.Dispose()
    $streams.gameErr.Dispose()
    $streams.lobbyOut.Dispose()
    $streams.lobbyErr.Dispose()
}
