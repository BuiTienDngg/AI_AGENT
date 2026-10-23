param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Chua co .venv. Chay: py -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
}
& $projectPython (Join-Path $PSScriptRoot 'local_admin.py') --port $Port --open-browser
exit $LASTEXITCODE
