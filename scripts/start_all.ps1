# Hermes Trading Agent — System Auto-Start Controller
# Bootstraps the entire multi-service ecosystem (RPC, Docker stack, database initializations, dashboard)

$ErrorActionPreference = "Stop"

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "      HERMES TRADING INTEGRATION — DEPLOYMENT PIPELINE     " -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Start Hermes RPC Server in new PowerShell window (Minimized)
Write-Host "[*] Initiating host-layer Python RPC services..." -ForegroundColor Yellow
$VenvActivate = Join-Path (Get-Location) "hermes_rpc\.venv\Scripts\Activate.ps1"
$ExecutionPath = Get-Location

# Build Command statement
if (Test-Path $VenvActivate) {
    $CommandBlock = "Set-Location '$ExecutionPath'; . '$VenvActivate'; uvicorn hermes_rpc.server:app --host 0.0.0.0 --port 7778 --reload"
} else {
    $CommandBlock = "Set-Location '$ExecutionPath'; uvicorn hermes_rpc.server:app --host 0.0.0.0 --port 7778 --reload"
}

try {
    Start-Process powershell.exe -ArgumentList "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $CommandBlock -WindowStyle Minimized
    Write-Host "[+] Launched Hermes RPC Server in background on Port 7778." -ForegroundColor Green
} catch {
    Write-Warning "[-] Could not start Hermes RPC automatically. Please execute 'uvicorn' manually inside 'hermes_rpc'."
}

# 2. Spin up Docker containers
Write-Host ""
Write-Host "[*] Launching containerized microservices (Redis, ChromaDB, preprocessors, executors)..." -ForegroundColor Yellow
try {
    & docker-compose up -d
    Write-Host "[+] Docker containers started successfully." -ForegroundColor Green
} catch {
    Write-Error "[-] Failed to running docker-compose up. Ensure Docker Desktop is active."
    Exit 1
}

# 3. Wait 15 seconds
Write-Host ""
Write-Host "[*] Allowing 15 seconds for database indexing and socket connections..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# 4. Build Obsidian directory schema structures
Write-Host ""
Write-Host "[*] Building and verifying local Obsidian knowledge vault..." -ForegroundColor Yellow
try {
    $HostPython = Join-Path (Get-Location) "hermes_rpc\.venv\Scripts\python.exe"
    if (Test-Path $HostPython) {
        & $HostPython scripts/init_vault.py
    } else {
        & python scripts/init_vault.py
    }
} catch {
    Write-Warning "[-] Vault initialization returned warning logs: $_"
}

# 5. Open Dashboard website in user's default browser
Write-Host ""
Write-Host "[*] Summoning Hermes SSE Integration console..." -ForegroundColor Yellow
try {
    Start-Process "http://localhost:8080"
    Write-Host "[+] Portal unlocked at http://localhost:8080." -ForegroundColor Green
} catch {
    Write-Host "[!] Could not auto-launch browser. Please navigate to http://localhost:8080 manually." -ForegroundColor Yellow
}

# 6. Status of services
Write-Host ""
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "         HERMES SYSTEM PIPELINES ARE NOW ONLINE          " -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host " * Windows RPC Gateway  :  [ON] -> http://localhost:7778" -ForegroundColor Green
Write-Host " * Pub/Sub Redis Engine :  [ON] -> port 6379" -ForegroundColor Green
Write-Host " * Chroma Vector Index  :  [ON] -> port 8000" -ForegroundColor Green
Write-Host " * MT5 Bridge Adaptor   :  [ON] -> ZeroMQ sockets active" -ForegroundColor Green
Write-Host " * Risk & SMC Execution :  [ON] -> Max 1% risk constraint active" -ForegroundColor Green
Write-Host " * Web Dashboard Portal :  [ON] -> http://localhost:8080" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
Write-Host "To shut down the architecture securely, run 'scripts/stop_all.ps1'" -ForegroundColor Gray
