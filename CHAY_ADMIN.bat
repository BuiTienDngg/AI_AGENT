@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Hay nhap dup CAI_DAT.bat truoc khi chay lan dau.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_admin.ps1"
set "office_exit=%errorlevel%"
if not "%office_exit%"=="0" pause
exit /b %office_exit%
