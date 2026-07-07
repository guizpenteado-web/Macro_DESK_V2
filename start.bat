@echo off
title IBOV Market Breadth
cd /d "%~dp0"

echo.
echo  =========================================
echo   IBOV Market Breadth - Servidor Local
echo  =========================================
echo.
echo  Acesso: http://localhost:8001
echo  Pressione Ctrl+C para encerrar o servidor
echo.

:: Abre o navegador apos 2 segundos (enquanto o servidor sobe)
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8001"

:: Inicia o servidor
.venv\Scripts\python.exe server.py

echo.
echo  Servidor encerrado.
pause
