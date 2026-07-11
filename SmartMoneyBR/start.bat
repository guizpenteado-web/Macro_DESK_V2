@echo off
setlocal
cd /d "%~dp0"

echo Liberando portas 8100 e 3100...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8100 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3100 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1

echo Iniciando backend (porta 8100)...
start "SmartMoneyBR Backend" cmd /k "cd backend && call .venv\Scripts\activate.bat && python -m app.main"

timeout /t 3 >nul

echo Iniciando frontend (porta 3100)...
start "SmartMoneyBR Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Backend:  http://localhost:8100/docs
echo Frontend: http://localhost:3100
