@echo off
setlocal
cd /d "%~dp0"

echo Liberando porta 8100...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8100 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1

call .venv\Scripts\activate.bat
echo Iniciando backend SmartMoneyBR...
echo Acesse: http://localhost:8100/docs
python -m app.main
