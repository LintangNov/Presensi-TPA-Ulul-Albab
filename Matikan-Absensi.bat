@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "FOUND="
for /l %%P in (8000,1,8010) do (
  curl.exe --silent --show-error --max-time 1 -X POST "http://127.0.0.1:%%P/admin/matikan" >nul 2>&1
  if not errorlevel 1 set "FOUND=%%P"
)
if defined FOUND (
  echo Permintaan matikan dikirim ke port !FOUND!.
  timeout /t 3 /nobreak >nul
  exit /b 0
)
echo Server Absensi TPA tidak ditemukan.
exit /b 0