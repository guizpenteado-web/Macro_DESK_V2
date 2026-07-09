@echo off
setlocal

echo ============================================================
echo  RRGCOMPLETO - Rotacao Relativa (universo expandido)
echo ============================================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale em https://python.org
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] Criando ambiente virtual...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [2/3] Instalando dependencias...
pip install -q -r requirements.txt

echo [3/3] Iniciando servidor...
echo.
echo  Dashboard: http://localhost:8021
echo  Docs API:  http://localhost:8021/docs
echo.
echo  Pressione Ctrl+C para parar.
echo.

python -m app.main

pause
