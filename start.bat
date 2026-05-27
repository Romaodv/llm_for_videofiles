@echo off
cd /d %~dp0

py -3 --version >nul 2>nul
if errorlevel 1 (
  echo Configurando Python padrao no Windows...
  py install default
  if errorlevel 1 (
    echo Nao foi possivel configurar o Python padrao. Instale o Python 3 e tente novamente.
    pause
    exit /b 1
  )
)

py scripts\launcher.py
