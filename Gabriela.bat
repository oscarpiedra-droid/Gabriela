@echo off
title Gabriela Rojas Pro - Madrid Pinto Logistics

set "ROOT_DIR=%~dp0"
set "APP_DIR=%ROOT_DIR%app"
set "CONDA_DIR=%ROOT_DIR%miniconda"
set "INSTALLER=%ROOT_DIR%Miniconda3-latest-Windows-x86_64.exe"

echo.
echo [INFO] Limpiando procesos antiguos...
taskkill /F /IM python.exe /T 2>nul

echo.
echo ============================================
echo   GABRIELA ROJAS PRO - ARRANQUE SEGURO
echo ============================================
echo.

set "CONDA_ACTIVATE=%CONDA_DIR%\Scripts\activate.bat"

:: 1. Check Miniconda
if not exist "%CONDA_ACTIVATE%" (
    echo [ERROR] No se encuentra el entorno de Miniconda.
    pause
    exit /b
)

:: 2. Activate Conda
echo [INFO] Activando entorno...
call "%CONDA_ACTIVATE%" base

:: 3. Create or Activate env
call conda activate gabriela

:: 4. Verify Deps
echo [INFO] Verificando dependencias...
cd /d "%APP_DIR%"
python -m pip install -r "requirements.txt" --upgrade-strategy only-if-needed

:: 5. Launch App (Visible console for debugging)
echo [INFO] Iniciando Gabriela Rojas Pro...
python main.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Error al iniciar la aplicacion.
    pause
)

exit
