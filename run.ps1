# PowerShell script to set up and run TranscriptBooth on Windows

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "       TranscriptBooth Setup & Run       " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Check if Python is installed
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "Using $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python is not installed or not in your PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://python.org and try again." -ForegroundColor Yellow
    Exit 1
}

# 2. Set up virtual environment
$venvPath = Join-Path $PSScriptRoot "venv"
if (-not (Test-Path $venvPath)) {
    Write-Host ">> Creating virtual environment (venv)..." -ForegroundColor Yellow
    & python -m venv venv
    Write-Host ">> Virtual environment created." -ForegroundColor Green
}

# 3. Activate virtual environment
Write-Host ">> Activating virtual environment..." -ForegroundColor Yellow
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
} else {
    Write-Host "ERROR: Could not find activation script at $activateScript" -ForegroundColor Red
    Exit 1
}

# 4. Install requirements
Write-Host ">> Installing/updating dependencies from requirements.txt..." -ForegroundColor Yellow
& pip install -r (Join-Path $PSScriptRoot "requirements.txt")
Write-Host ">> Dependencies installed." -ForegroundColor Green

# 5. Check for .env file
$envPath = Join-Path $PSScriptRoot ".env"
$envExamplePath = Join-Path $PSScriptRoot ".env.example"
if (-not (Test-Path $envPath)) {
    if (Test-Path $envExamplePath) {
        Write-Host ">> Creating .env from .env.example..." -ForegroundColor Yellow
        Copy-Item -Path $envExamplePath -Destination $envPath
        Write-Host ""
        Write-Host "---------------------------------------------------------" -ForegroundColor Red
        Write-Host "ACTION REQUIRED: Created .env file." -ForegroundColor Yellow
        Write-Host "Please open the '.env' file in your workspace and add your" -ForegroundColor Yellow
        Write-Host "OPENAI_API_KEY. Then, run this script again." -ForegroundColor Yellow
        Write-Host "---------------------------------------------------------" -ForegroundColor Red
        Write-Host ""
        Read-Host "Press Enter to exit..."
        Exit 1
    } else {
        Write-Host "WARNING: .env.example not found. Creating empty .env..." -ForegroundColor Yellow
        New-Item -Path $envPath -ItemType File -Force | Out-Null
    }
}

# 6. Start Flask App
Write-Host ">> Starting TranscriptBooth server..." -ForegroundColor Green
Write-Host ">> Server will be available at http://127.0.0.1:5000" -ForegroundColor Cyan
Write-Host ">> Press Ctrl+C in this window to stop the server." -ForegroundColor Yellow
Write-Host ""

& python (Join-Path $PSScriptRoot "app.py")
