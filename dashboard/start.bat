@echo off
setlocal

echo ============================================================
echo  Intermarket Dashboard
echo  IBOVESPA / 6L COT / NTN-B 2035 / Fluxo Estrangeiro
echo ============================================================
echo.

cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale em https://python.org
    pause
    exit /b 1
)

REM Create venv if not exists
if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] Criando ambiente virtual...
    python -m venv .venv
)

REM Activate venv
call .venv\Scripts\activate.bat

REM Install deps
echo [2/3] Instalando dependencias...
pip install -q -r requirements.txt

REM Start server
echo [3/3] Iniciando servidor...
echo.
echo  Dashboard: http://localhost:8000
echo  Docs API:  http://localhost:8000/docs
echo.
echo  Pressione Ctrl+C para parar.
echo.

python main.py

pause
