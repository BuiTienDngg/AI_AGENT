param(
    [Parameter(Mandatory = $true)]
    [string]$Video,
    [string]$Out = "",
    [ValidateSet('auto', 'always', 'never')]
    [string]$ObjectReview = "auto",
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
# Pick up tools installed after VS Code started while preserving the current PATH.
$pathEntries = @($env:Path -split ';' | Where-Object { $_ })
foreach ($scope in @('User', 'Machine')) {
    foreach ($entry in ([Environment]::GetEnvironmentVariable('Path', $scope) -split ';')) {
        if ($entry -and $pathEntries -notcontains $entry) { $pathEntries += $entry }
    }
}
$env:Path = $pathEntries -join ';'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Missing .venv. Run: py -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}
$cmdArgs = @('run.py', 'run', '--video', $Video)
$cmdArgs += @('--object-review', $ObjectReview)
if ($Out -ne '') { $cmdArgs += @('--out', $Out) }
if ($Resume) {
    if ($Out -eq '') { throw 'Resume requires -Out pointing to the existing run directory.' }
    $cmdArgs += '--resume'
}
& $python @cmdArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Pipeline stopped with exit code $LASTEXITCODE. See the run directory for qa_report.json or logs."
    exit $LASTEXITCODE
}
