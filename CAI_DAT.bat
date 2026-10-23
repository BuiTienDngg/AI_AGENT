@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"
set "office_exit=%errorlevel%"
echo.
if not "%office_exit%"=="0" echo Cai dat chua hoan tat. Xem loi ben tren.
pause
exit /b %office_exit%
