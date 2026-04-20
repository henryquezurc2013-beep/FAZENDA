@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Sistema de Rebanho Bovino
echo ============================================
echo.
echo Pasta: %CD%
echo.

echo Verificando Python...
"C:\Users\heryc\AppData\Local\Programs\Python\Python312\python.exe" --version
if errorlevel 1 (
    echo ERRO: Python nao encontrado!
    pause
    exit /b 1
)

echo.
echo Iniciando servidor na porta 8000...
echo Acesse: http://localhost:8000
echo Pressione CTRL+C para encerrar.
echo.

"C:\Users\heryc\AppData\Local\Programs\Python\Python312\python.exe" main.py

echo.
echo Servidor encerrado.
pause
