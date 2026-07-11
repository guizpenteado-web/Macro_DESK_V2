@echo off
setlocal
cd /d "%~dp0"

echo Liberando porta 3100...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3100 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1

echo Iniciando frontend SmartMoneyBR...
echo Acesse: http://localhost:3100
call npm run dev
