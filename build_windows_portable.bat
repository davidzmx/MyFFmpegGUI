@echo off
setlocal enabledelayedexpansion
title Generador de Version Portable para Windows - MyFFmpeg GUI
color 0a

echo =======================================================================
echo         CONSTRUCTOR DE VERSION PORTABLE (Windows 64-bit)
echo                         MyFFmpeg GUI
echo =======================================================================
echo.

:: 1. Verificar Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python en el PATH. Por favor instala Python 3.8+
    pause
    exit /b 1
)

:: 2. Instalar dependencias necesarias
echo [*] Verificando dependencias necesarias (PyQt5, PyInstaller)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

:: 3. Preparar directorios de salida
set "PORTABLE_DIR=dist\MyFFmpegGUI_Portable"
echo [*] Limpiando compilaciones anteriores...
rmdir /s /q build 2>nul
rmdir /s /q "%PORTABLE_DIR%" 2>nul
rmdir /s /q dist\MyFFmpegGUI 2>nul

:: 4. Compilar ejecutable portable sin consola
echo [*] Compilando con PyInstaller en modo carpeta portable (arranque instantaneo)...
pyinstaller --noconsole ^
            --name "MyFFmpegGUI" ^
            --add-data "ui;ui" ^
            --hidden-import "PyQt5.QtCore" ^
            --hidden-import "PyQt5.QtWidgets" ^
            --hidden-import "PyQt5.QtGui" ^
            main.py

if not exist "dist\MyFFmpegGUI\MyFFmpegGUI.exe" (
    echo [ERROR] No se pudo compilar el ejecutable.
    pause
    exit /b 1
)

:: Mover a carpeta portable
rename "dist\MyFFmpegGUI" "MyFFmpegGUI_Portable"

:: 5. Copiar FFmpeg y FFprobe si existen localmente
mkdir "%PORTABLE_DIR%\bin" 2>nul
if exist "bin\ffmpeg.exe" (
    echo [*] Copiando bin\ffmpeg.exe incluido...
    copy /y "bin\ffmpeg.exe" "%PORTABLE_DIR%\bin\" >nul
) else if exist "ffmpeg.exe" (
    echo [*] Copiando ffmpeg.exe...
    copy /y "ffmpeg.exe" "%PORTABLE_DIR%\bin\" >nul
) else (
    echo [INFO] No se encontro ffmpeg.exe en la raiz o en bin\
    echo        Para que sea 100%% autosuficiente, puedes colocar ffmpeg.exe y ffprobe.exe
    echo        dentro de la carpeta: %PORTABLE_DIR%\bin\
)

if exist "bin\ffprobe.exe" (
    copy /y "bin\ffprobe.exe" "%PORTABLE_DIR%\bin\" >nul
) else if exist "ffprobe.exe" (
    copy /y "ffprobe.exe" "%PORTABLE_DIR%\bin\" >nul
)

:: 6. Copiar archivos auxiliares
copy /y "README.md" "%PORTABLE_DIR%\" >nul 2>&1
copy /y "instalar_menu_contextual_windows.reg" "%PORTABLE_DIR%\" >nul 2>&1
copy /y "desinstalar_menu_contextual_windows.reg" "%PORTABLE_DIR%\" >nul 2>&1

:: Crear archivo de instrucciones portables
(
echo ====================================================================
echo                   MyFFmpeg GUI - Version Portable
echo ====================================================================
echo.
echo COMO USAR ESTA VERSION PORTABLE:
echo 1. No requiere instalacion. Puedes colocar esta carpeta en cualquier
echo    lugar (disco C:, D:, disco externo o pendrive USB).
echo.
echo 2. Para abrir la aplicacion:
echo    Haz doble clic sobre "MyFFmpegGUI.exe".
echo.
echo 3. FFMPEG INTEGRADO:
echo    Si colocas ffmpeg.exe y ffprobe.exe en la subcarpeta "bin\",
echo    la aplicacion los detectara automaticamente sin configurar nada.
echo.
echo 4. MENU CONTEXTUAL (OPCIONAL):
echo    Dentro del programa, ve a "Ajustes" y haz clic en:
echo    "Integrar en el Menu Contextual" para poder hacer clic derecho
echo    sobre cualquier video/audio. No requiere permisos de administrador.
echo.
) > "%PORTABLE_DIR%\LEEME_PORTABLE.txt"

:: 7. Crear archivo ZIP empaquetado listo para distribuir
echo [*] Creando archivo ZIP comprimido portable...
powershell -Command "Compress-Archive -Path '%PORTABLE_DIR%' -DestinationPath 'dist\MyFFmpegGUI_Portable_Windows.zip' -Force" 2>nul

echo.
echo =======================================================================
echo [EXITO] Version Portable generada exitosamente:
echo.
echo 1. Carpeta portable lista para usar:
echo    %PORTABLE_DIR%\
echo.
if exist "dist\MyFFmpegGUI_Portable_Windows.zip" (
    echo 2. Archivo ZIP comprimido para distribuir:
    echo    dist\MyFFmpegGUI_Portable_Windows.zip
)
echo =======================================================================
echo.
pause
