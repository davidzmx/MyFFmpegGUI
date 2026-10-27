@echo off
setlocal
cd /d "%~dp0"

:: 1. Verificar si Python está instalado en el sistema
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo =====================================================================
    echo [ERROR] No se encontro Python en el PATH del sistema.
    echo Por favor asegurese de tener instalado Python 3.8 o superior y
    echo haber marcado la casilla "Add Python to PATH" durante la instalacion.
    echo =====================================================================
    echo.
    pause
    exit /b 1
)

:: 2. Si se invoca con --console o -c, ejecutar con consola visible para depuracion
if "%~1"=="--console" goto run_console
if "%~1"=="-c" goto run_console

:: 3. Iniciar la aplicacion sin ventana negra de consola (usando pythonw)
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw main.py %*
    exit /b 0
)

:run_console
python main.py %*
if %errorlevel% neq 0 (
    echo.
    echo [AVISO] La aplicacion se cerro con codigo de error %errorlevel%.
    pause
)
exit /b %errorlevel%
