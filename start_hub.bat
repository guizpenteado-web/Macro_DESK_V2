@echo off
setlocal
title Macro Desk

echo.
echo  ============================================================
echo   Macro Desk
echo   Intermarket + Market Breadth Ultra
echo  ============================================================
echo.

cd /d "%~dp0"

REM Libera portas caso estejam ocupadas por instancias anteriores
echo  Liberando portas 8000, 8010, 8011, 8012 e 8013...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8010 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8011 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8012 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8013 " 2^>nul') do taskkill /PID %%p /F >nul 2>&1
timeout /t 2 /nobreak >nul

REM Inicia ngrok em background (janela minimizada)
echo  Iniciando ngrok...
taskkill /IM ngrok.exe /F >nul 2>&1
start /min "" "C:\Users\Guilherme\AppData\Local\Microsoft\WindowsApps\ngrok.exe" http --domain=jawed-sermon-extras.ngrok-free.dev 8000
timeout /t 3 /nobreak >nul
echo  ngrok: https://jawed-sermon-extras.ngrok-free.dev

REM Usa o venv do dashboard (tem fastapi + uvicorn)
call dashboard\.venv\Scripts\activate.bat

echo  Iniciando sub-servidores e hub...
echo  Acesse: http://localhost:8000
echo  Link publico: https://jawed-sermon-extras.ngrok-free.dev
echo.
echo  Pressione Ctrl+C para encerrar tudo.
echo.

python unified_server.py

pause
