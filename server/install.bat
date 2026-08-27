@echo off
chcp 65001 >nul
title Instalador - Servico de Impressoras
echo.
echo ========================================
echo   Instalador - Servico de Impressoras
echo ========================================
echo.

:: Verificar se esta a correr como administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Execute como Administrador!
    echo.
    pause
    exit /b 1
)

:: Verificar se Python esta instalado
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Python nao encontrado!
    echo Instale Python 3.10+ de https://www.python.org
    pause
    exit /b 1
)

echo [1/4] A instalar dependencias...
pip install pysnmp pywin32 pystray pillow --quiet 2>nul
if %errorLevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo [2/4] A criar diretorias...
set AGENT_DIR=%APPDATA%\FotocopiadoraAgent
if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"
if not exist "%AGENT_DIR%\logs" mkdir "%AGENT_DIR%\logs"

echo [3/4] A copiar ficheiros...
copy /Y "%~dp0agent_service.py" "%AGENT_DIR%\agent_service.py" >nul
if not exist "%AGENT_DIR%\agent_service.py" (
    echo [ERRO] Ficheiro agent_service.py nao encontrado.
    pause
    exit /b 1
)

echo [4/4] A instalar servico...
sc create FotocopiadoraAgent binPath= "python \"%AGENT_DIR%\agent_service.py\"" start= auto DisplayName= "Servico de Impressoras" >nul 2>&1
sc description FotocopiadoraAgent "Agente de monitoramento de fotocopiadoras" >nul 2>&1
sc start FotocopiadoraAgent >nul 2>&1

echo.
echo ========================================
echo   Instalacao concluida com sucesso!
echo ========================================
echo.
echo O servico "Servico de Impressoras" foi instalado e iniciado.
echo.
echo Para gerir:
echo   - Gestor de Servicos do Windows
echo   - Parar: sc stop FotocopiadoraAgent
echo   - Iniciar: sc start FotocopiadoraAgent
echo   - Remover: sc delete FotocopiadoraAgent
echo.
pause
