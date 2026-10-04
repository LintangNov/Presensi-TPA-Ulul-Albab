@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment tidak ditemukan.
  exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm AbsensiTPA.spec
if errorlevel 1 exit /b 1
echo Selesai. Distribusikan seluruh folder dist\AbsensiTPA beserta
echo Start-Absensi.bat dan Matikan-Absensi.bat.
