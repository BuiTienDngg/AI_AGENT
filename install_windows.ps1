# Re-runnable setup; never replaces an existing environment or user config.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'

function Refresh-OfficePath {
    foreach ($scope in @('Machine', 'User')) {
        $value = [Environment]::GetEnvironmentVariable('Path', $scope)
        if ($value) { $env:Path += ';' + [Environment]::ExpandEnvironmentVariables($value) }
    }
    $npmBin = Join-Path $env:APPDATA 'npm'
    if (Test-Path -LiteralPath $npmBin) { $env:Path += ';' + $npmBin }
}

function Install-OfficePackage([string]$Id) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Missing winget. Install Microsoft App Installer from Microsoft Store, then run CAI_DAT.bat again. Required package: $Id"
    }
    & winget.exe install --id $Id --exact --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Could not install $Id (code $LASTEXITCODE). Review the message above and retry." }
    Refresh-OfficePath
}

function Find-OfficePython {
    foreach ($candidate in @('python.exe', 'py.exe')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            $found = & $command.Source -c "import sys; print(sys.executable if (3,10) <= sys.version_info[:2] < (3,15) else '')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $found -and (Test-Path -LiteralPath "$found")) { return "$found" }
        }
    }
    # Python installed by winget may not yet be visible to the py launcher.
    $installed = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (Test-Path -LiteralPath $installed) { return $installed }
    return $null
}

try {
    Refresh-OfficePath
    Write-Host '[1/6] Python and virtual environment'
    $projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $projectPython)) {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv')) {
            throw 'Existing .venv is incomplete. Rename it for backup, then run CAI_DAT.bat again.'
        }
        $basePython = Find-OfficePython
        if (-not $basePython) {
            Install-OfficePackage 'Python.Python.3.13'
            $basePython = Find-OfficePython
        }
        if (-not $basePython) { throw 'Python is not available. Restart this installer after installing Python 3.13.' }
        & $basePython -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
    }
    & $projectPython -c "import sys; assert (3,10) <= sys.version_info[:2] < (3,15), 'Python 3.10-3.14 required'; print(sys.version)"
    if ($LASTEXITCODE -ne 0) { throw 'Existing virtual environment is incompatible. Keep a backup before recreating it.' }
    & $projectPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Could not upgrade pip. Check your internet connection.' }
    & $projectPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    & $projectPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed.' }

    Write-Host '[2/6] FFmpeg and FFprobe'
    if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or
        -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
        Install-OfficePackage 'Gyan.FFmpeg'
    }
    foreach ($binary in @('ffmpeg.exe', 'ffprobe.exe')) {
        if (-not (Get-Command $binary -ErrorAction SilentlyContinue)) { throw "$binary is missing. Restart Windows/VS Code and retry." }
        & $binary -version
        if ($LASTEXITCODE -ne 0) { throw "$binary failed to start." }
    }

    Write-Host '[3/6] Codex CLI (ChatGPT authentication; no API key)'
    if (-not (Get-Command codex.cmd -ErrorAction SilentlyContinue) -and
        -not (Get-Command codex.exe -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { Install-OfficePackage 'OpenJS.NodeJS.LTS' }
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'npm is unavailable. Restart installer after installing Node.js LTS.' }
        & npm.cmd install -g '@openai/codex'
        if ($LASTEXITCODE -ne 0) { throw 'Codex CLI installation failed.' }
        Refresh-OfficePath
    }
    $codexCommand = Get-Command codex.cmd -ErrorAction SilentlyContinue
    if (-not $codexCommand) { $codexCommand = Get-Command codex.exe -ErrorAction SilentlyContinue }
    if (-not $codexCommand) { throw 'Codex CLI not found after installation.' }
    & $codexCommand.Source --version
    if ($LASTEXITCODE -ne 0) { throw 'Codex CLI failed to start.' }
    & $codexCommand.Source login status
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Please complete Sign in with ChatGPT in your browser. No API key is needed.'
        & $codexCommand.Source login
        if ($LASTEXITCODE -ne 0) { throw 'ChatGPT login was not completed. Run CAI_DAT.bat again when ready.' }
    }

    Write-Host '[4/6] Local folders and VS Code'
    foreach ($folder in @('runs', 'local_admin_data', '.vscode')) {
        New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot $folder) -Force | Out-Null
    }
    # Preserve custom JSON/JSONC settings. A project-local relative interpreter is portable.
    $settingsFile = Join-Path $PSScriptRoot '.vscode\settings.json'
    if (-not (Test-Path -LiteralPath $settingsFile)) {
        '{"python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe"}' |
            Set-Content -LiteralPath $settingsFile -Encoding UTF8
    }
    Write-Host '[5/6] Imports'
    & $projectPython -c "import docx, PIL, requests, flask, waitress; print('Imports OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Required Python imports failed.' }
    Write-Host '[6/6] Project doctor'
    & $projectPython (Join-Path $PSScriptRoot 'run.py') doctor
    if ($LASTEXITCODE -ne 0) { throw 'Project doctor failed. See details above.' }
    Write-Host ''
    Write-Host 'SETUP COMPLETE. Double-click CHAY_ADMIN.bat to open the admin.'
} catch {
    Write-Host ''
    Write-Host ('SETUP FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
exit 0
