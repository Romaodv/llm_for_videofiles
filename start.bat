@echo off
cd /d %~dp0

powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force" >nul 2>nul

py -3 --version >nul 2>nul
if errorlevel 1 (
  winget --version >nul 2>nul
  if not errorlevel 1 (
    echo Instalando Python 3.12 via winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
  )

  echo Configurando Python padrao no Windows...
  py install default
)

py -3 --version >nul 2>nul
if errorlevel 1 (
  python --version >nul 2>nul
  if errorlevel 1 (
    echo Nao foi possivel configurar o Python padrao. Instale o Python 3 e tente novamente.
    pause
    exit /b 1
  )
  python scripts\launcher.py
) else (
  py scripts\launcher.py
)
