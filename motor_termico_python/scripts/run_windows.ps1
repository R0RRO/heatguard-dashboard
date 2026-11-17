$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -e ".[full,test]"
.\.venv\Scripts\python.exe -m pytest -q

if (-not $env:HG_ADMIN_API_KEY -or -not $env:HG_VIEWER_API_KEY) {
    throw 'Configure HG_ADMIN_API_KEY y HG_VIEWER_API_KEY antes de iniciar.'
}

.\.venv\Scripts\python.exe -m uvicorn heatguard.api:app --host 127.0.0.1 --port 8000
