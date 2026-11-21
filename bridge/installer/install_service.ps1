# TallyGuard MCP - Windows Background Service Installer
# Registers TallyGuard Bridge Agent as an automatic Windows Service

param (
    [string]$ServiceName = "TallyGuardBridge",
    [string]$DisplayName = "TallyGuard MCP Bridge Service",
    [string]$Description = "Governed Model Context Protocol bridge agent for local Tally Prime access."
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     TallyGuard MCP Windows Service Registration" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Check for Administrator elevation
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warning "Administrator permissions required. Re-launching PowerShell with elevated rights..."
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$pythonPath = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) {
    Write-Error "Python 3.11+ is not found in system PATH. Please install Python before continuing."
    exit 1
}

$scriptDir = Split-Path -Parent $PSCommandPath
$repoDir = Split-Path -Parent (Split-Path -Parent $scriptDir)
$serviceScript = Join-Path $repoDir "bridge\service.py"

Write-Host "[1/3] Verifying Python service entrypoint..."
Write-Host "      Entrypoint: $serviceScript"

# Stop existing service if already installed
if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "[2/3] Existing service '$ServiceName' detected. Stopping and removing..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    & sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
} else {
    Write-Host "[2/3] Registering new service '$ServiceName'..."
}

$binPath = "`"$pythonPath`" `"$serviceScript`""

# Register service via sc.exe (Standard Windows Service Controller)
& sc.exe create $ServiceName binPath= $binPath start= auto DisplayName= "`"$DisplayName`"" | Out-Null
& sc.exe description $ServiceName "$Description" | Out-Null
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/60000 | Out-Null

Write-Host "[3/3] Starting $DisplayName..."
& sc.exe start $ServiceName | Out-Null

Write-Host ""
Write-Host "✔ Service installed and started successfully!" -ForegroundColor Green
Write-Host "  Service Name: $ServiceName"
Write-Host "  Startup Type: Automatic (restarts on reboot and auto-recovers on failure)"
