@echo off
setlocal
title Macro Dashboard

echo.
echo  ============================================================
echo   Macro Dashboard
echo   Fed Rate / CPI / NFP / Sazonalidade / Bitcoin
echo  ============================================================
echo.

cd /d "%~dp0"

REM Libera porta 8002 se estiver ocupada
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8002 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1
timeout /t 1 /nobreak >nul

REM Verifica se venv existe, cria se não existir
if not exist ".venv\Scripts\python.exe" (
    echo  Criando ambiente virtual...
    python -m venv .venv
    echo  Instalando dependencias...
    .venv\Scripts\pip install -r requirements.txt --quiet
)

call .venv\Scripts\activate.bat

echo  Iniciando servidor...
echo  Acesse: http://localhost:8002
echo.
echo  Na primeira execucao, aguarde ~60s para coleta de dados.
echo  Pressione Ctrl+C para encerrar.
echo.

python server.py

pause
