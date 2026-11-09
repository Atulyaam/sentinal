# Kiro Quality Hook — Validate All (Backend Tests + Manifest + Frontend Build + Headless Browser Runtime)
$ErrorActionPreference = "Stop"

Write-Host "==> [Hook] Running Project Sentinel Validation..." -ForegroundColor Cyan

# 1. Backend tests
Write-Host "--> Running Backend Unit & Contract Tests..." -ForegroundColor Yellow
python -m unittest discover -s tests -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backend tests failed!"
    exit 1
}

# 2. Manifest validation
Write-Host "--> Validating Kiro Crew Manifest..." -ForegroundColor Yellow
python scripts/validate_manifest.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Kiro Crew manifest validation failed!"
    exit 1
}

# 3. Frontend typecheck and build
Write-Host "--> Running Frontend Build & Typecheck..." -ForegroundColor Yellow
Push-Location apps/crew-app
try {
    npm run typecheck
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend typecheck failed!"
        exit 1
    }
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend build failed!"
        exit 1
    }
}
finally {
    Pop-Location
}

# 4. Headless browser runtime verification
Write-Host "--> Running Headless Browser Runtime Verification..." -ForegroundColor Yellow
python scripts/runtime_verification.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Headless browser runtime verification failed!"
    exit 1
}

# 5. Real browser import & SQLite workflow verification
Write-Host "--> Running Real Browser & SQLite Workflow Verification..." -ForegroundColor Yellow
python scripts/verify_real_import_workflow.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Real browser and SQLite workflow verification failed!"
    exit 1
}

Write-Host "==> [Hook] All Quality Gates Passed Cleanly!" -ForegroundColor Green
