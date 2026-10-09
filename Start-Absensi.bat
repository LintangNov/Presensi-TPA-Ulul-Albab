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

if exist "AbsensiTPA.exe" (
  start "Absensi TPA" /min "%~dp0AbsensiTPA.exe"
) else if exist "dist\AbsensiTPA\AbsensiTPA.exe" (
  start "Absensi TPA" /min "%~dp0dist\AbsensiTPA\AbsensiTPA.exe"
) else if exist ".venv\Scripts\python.exe" (
  start "Absensi TPA" /min ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port !PORT!
) else (
  echo Aplikasi belum dikemas dan virtual environment tidak ditemukan.
  echo Salin folder dist\AbsensiTPA dari komputer pembuat aplikasi.
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
