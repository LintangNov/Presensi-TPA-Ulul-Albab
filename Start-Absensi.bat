@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PORT="
for /l %%P in (8000,1,8010) do (
  curl.exe --silent --show-error --max-time 1 "http://127.0.0.1:%%P/api/ping" >nul 2>&1
  if not errorlevel 1 if not defined PORT set "PORT=%%P"
)
if defined PORT (
  echo Absensi TPA sudah berjalan di port !PORT!.
  start "" "http://127.0.0.1:!PORT!/admin"
  start "" msedge.exe --app="http://127.0.0.1:!PORT!/scan"
  exit /b 0
)

for /l %%P in (8000,1,8010) do (
  netstat -ano | findstr /r /c:":%%P .*LISTENING" >nul
  if errorlevel 1 if not defined PORT set "PORT=%%P"
)
if not defined PORT (
  echo Tidak menemukan port kosong antara 8000 dan 8010.
  pause
  exit /b 1
)
set "ABSENSI_PORT=!PORT!"
set "APP_EXE="

if exist "%~dp0AbsensiTPA.exe" (
  set "APP_EXE=%~dp0AbsensiTPA.exe"
) else if exist "%~dp0AbsensiTPA\AbsensiTPA.exe" (
  set "APP_EXE=%~dp0AbsensiTPA\AbsensiTPA.exe"
) else if exist "%~dp0dist\AbsensiTPA\AbsensiTPA.exe" (
  set "APP_EXE=%~dp0dist\AbsensiTPA\AbsensiTPA.exe"
)

if defined APP_EXE (
  start "Absensi TPA" /min "!APP_EXE!"
) else if exist ".venv\Scripts\python.exe" (
  start "Absensi TPA" /min ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port !PORT!
) else (
  echo Aplikasi belum dikemas dan virtual environment tidak ditemukan.
  echo Pastikan folder AbsensiTPA berisi AbsensiTPA.exe berada sejajar
  echo dengan file Start-Absensi.bat ini.
  pause
  exit /b 1
)

for /l %%I in (1,1,15) do (
  curl.exe --silent --show-error --max-time 1 "http://127.0.0.1:!PORT!/api/ping" >nul 2>&1
  if not errorlevel 1 goto ready
  timeout /t 1 /nobreak >nul
)
echo Server tidak merespons. Periksa logs\app.log.
pause
exit /b 1

:ready
echo Absensi TPA berjalan di http://127.0.0.1:!PORT!
start "" "http://127.0.0.1:!PORT!/admin"
start "" msedge.exe --app="http://127.0.0.1:!PORT!/scan"
