@echo off
setlocal EnableDelayedExpansion
title Item Manager - Launcher & Installer
chcp 65001 >nul

:MENU
cls
echo ========================================
echo   🛠️  ITEM MANAGER - LAUNCHER
echo ========================================
echo.
echo [1] 📦 Instalar Dependências (Install)
echo [2] 🏃 Iniciar ItemManager (Run)
echo [3] 🧹 Limpar Cache (Clean)
echo [4] 🔍 Verificar Ambiente (Check)
echo [5] 🧨 Remover Dependências (Uninstall)
echo [0] ❌ Sair
echo.
set /p OPCAO="Escolha: "

if "%OPCAO%"=="1" goto INSTALL
if "%OPCAO%"=="2" goto RUN
if "%OPCAO%"=="3" goto CLEAN
if "%OPCAO%"=="4" goto CHECK
if "%OPCAO%"=="5" goto UNINSTALL
if "%OPCAO%"=="0" goto END

echo Opção inválida!
timeout /t 1 >nul
goto MENU

:INSTALL
cls
echo ========================================
echo   📦 INSTALANDO DEPENDÊNCIAS
echo ========================================
echo.

:: Check Python
py --version >nul 2>&1
if errorlevel 1 (
    echo Python não encontrado!
    echo Por favor instale Python 3.10 ou superior.
    pause
    goto MENU
)

echo Verificando pacotes...
set "MISSING_PACKAGES="
call :CheckPackage PyQt6
call :CheckPackage Pillow
call :CheckPackage torch
call :CheckPackage torchvision
call :CheckPackage opencv-python
call :CheckPackage numpy
call :CheckPackage check_basicsr
call :CheckPackage realesrgan
call :CheckPackage pyqtdarktheme
call :CheckPackage noise
call :CheckPackage PyOpenGL
call :CheckPackage pygame

if "!MISSING_PACKAGES!"=="" (
    echo Todas as dependências já estão instaladas!
    echo.
    echo Instalando requirements.txt para garantir...
    py -m pip install -r requirements.txt
    
    echo.
    echo Concluído!
    pause
    goto MENU
)

echo Faltando: !MISSING_PACKAGES!
echo.
echo Instalando...

:: Handle basicsr specifically if missing
echo !MISSING_PACKAGES! | findstr /C:"basicsr" >nul
if not errorlevel 1 (
    echo.
    echo [FIX] Instalando basicsr via patch local...
    call :InstallBasicSR
)

:: Install others
py -m pip install -r requirements.txt

echo.
echo Instalação concluída!
pause
goto MENU

:RUN
cls
echo ========================================
echo   🏃 INICIANDO ITEM MANAGER
echo ========================================
echo.
py ItemManager.py
if errorlevel 1 (
    echo.
    echo Ocorreu um erro ao executar a aplicação.
    pause
)
goto MENU

:CLEAN
cls
echo ========================================
echo   🧹 LIMPANDO CACHE
echo ========================================
echo.
echo Excluindo pastas __pycache__...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
echo.
echo Excluindo arquivos temporários...
if exist "download_basicsr.py" del "download_basicsr.py"
if exist "basicsr-1.4.2.tar.gz" del "basicsr-1.4.2.tar.gz"
echo.
echo Limpeza concluída!
pause
goto MENU

:CHECK
cls
echo ========================================
echo   🔍 VERIFICANDO AMBIENTE
echo ========================================
echo.
echo Python Version:
py --version
echo.
echo Pip Version:
py -m pip --version
echo.
pause
goto MENU

:UNINSTALL
cls
echo ========================================
echo   🧨 REMOVENDO DEPENDÊNCIAS
echo ========================================
echo.
echo Tem certeza que deseja desinstalar todas as bibliotecas do projeto?
echo (Isso pode quebrar o uso de outros programas se compartilhar o Python)
echo.
set /p CONFIRM="Digite S para confirmar: "
if /I "%CONFIRM%" NEQ "S" goto MENU

echo.
echo Desinstalando pacotes...
py -m pip uninstall -r requirements.txt -y
py -m pip uninstall basicsr -y
echo.
echo Remoção concluída!
pause
goto MENU

:END
exit

:CheckPackage
set "PKG_NAME=%~1"
if "%PKG_NAME%"=="check_basicsr" set "PKG_NAME=basicsr"
py -c "import importlib.util; exit(0) if importlib.util.find_spec('%PKG_NAME%') else exit(1)" >nul 2>&1
if errorlevel 1 set "MISSING_PACKAGES=!MISSING_PACKAGES! %PKG_NAME%"
exit /b

:InstallBasicSR
:: 1. Download source if not exists
if not exist "BasicSR-1.4.2" (
    echo Baixando código fonte...
    if not exist "download_basicsr.py" (
         echo import urllib.request; import tarfile; url = "https://github.com/XPixelGroup/BasicSR/archive/refs/tags/v1.4.2.tar.gz"; filename = "basicsr-1.4.2.tar.gz"; opener = urllib.request.build_opener^('User-agent', 'Mozilla/5.0'^); urllib.request.install_opener^(opener^); urllib.request.urlretrieve^(url, filename^); t = tarfile.open^(filename, "r:gz"^); t.extractall^(^); t.close^(^) > download_basicsr.py
    )
    py download_basicsr.py
    
    :: 2. Patch setup.py
    echo Aplicando patch no setup.py...
    py -c "import os; content = open('BasicSR-1.4.2/setup.py').read().replace('version=get_version(),', \"version='1.4.2',\").replace('version_file =', '#'); open('BasicSR-1.4.2/setup.py', 'w').write(content); open('BasicSR-1.4.2/basicsr/version.py', 'w').write(\"__version__ = '1.4.2'\")"
)

:: 3. Install from local directory
py -m pip install ./BasicSR-1.4.2

if errorlevel 1 (
    echo ERRO: Instalação manual falhou.
    echo Pressione qualquer tecla para voltar ao menu...
    pause >nul
)
exit /b
