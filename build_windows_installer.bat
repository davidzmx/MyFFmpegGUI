@echo off
setlocal enabledelayedexpansion
title Generador de Instalador de Windows - MyFFmpeg GUI
color 0b

echo =======================================================================
echo          CONSTRUCTOR DE INSTALADOR PARA WINDOWS (MyFFmpeg GUI)
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

:: 3. Exportar archivos de registro actualizados
echo [*] Generando configuraciones del menu contextual...
python main.py --install-context >nul 2>&1

:: 4. Compilar con PyInstaller
echo [*] Compilando ejecutable con PyInstaller (modo directorio para maxima velocidad de arranque)...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

pyinstaller --noconsole ^
            --name "MyFFmpegGUI" ^
            --add-data "ui;ui" ^
            --hidden-import "PyQt5.QtCore" ^
            --hidden-import "PyQt5.QtWidgets" ^
            --hidden-import "PyQt5.QtGui" ^
            main.py

if not exist "dist\MyFFmpegGUI\MyFFmpegGUI.exe" (
    echo [ERROR] No se genero el archivo dist\MyFFmpegGUI\MyFFmpegGUI.exe
    pause
    exit /b 1
)

:: 4.5 Buscar e incluir FFmpeg y FFprobe si estan en PATH
if not exist "bin\ffmpeg.exe" (
    where ffmpeg.exe >nul 2>&1
    if !errorlevel! equ 0 (
        echo [*] Detectado ffmpeg.exe en PATH, copiando a bin\ para incluirlo...
        mkdir bin 2>nul
        for /f "delims=" %%F in ('where ffmpeg.exe') do copy /y "%%F" "bin\ffmpeg.exe" >nul & goto :found_ffmpeg
    )
    :found_ffmpeg
)
if not exist "bin\ffprobe.exe" (
    where ffprobe.exe >nul 2>&1
    if !errorlevel! equ 0 (
        mkdir bin 2>nul
        for /f "delims=" %%F in ('where ffprobe.exe') do copy /y "%%F" "bin\ffprobe.exe" >nul & goto :found_ffprobe
    )
    :found_ffprobe
)

echo [OK] Compilacion completada con exito en dist\MyFFmpegGUI\
echo.

:: 5. Verificar Inno Setup
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
) else (
    where iscc >nul 2>&1
    if !errorlevel! equ 0 set "ISCC=iscc"
)

if defined ISCC (
    echo [*] Compilando instalador ejecutable con Inno Setup...
    "%ISCC%" installer_windows.iss
    if !errorlevel! equ 0 (
        echo.
        echo =======================================================================
        echo [EXITO] Instalador generado exitosamente en la carpeta 'Output\':
        dir /b Output\*.exe
        echo =======================================================================
    ) else (
        echo [ADVERTENCIA] Error al compilar con Inno Setup. Revisa installer_windows.iss
    )
) else (
    echo =======================================================================
    echo [INFO] Inno Setup 6 no esta instalado en las rutas por defecto.
    echo Puedes descargar Inno Setup gratis de: https://jrsoftware.org/isdl.php
    echo Una vez instalado, abre 'installer_windows.iss' con Inno Setup y pulsa 'Compile' (F9)
    echo para generar tu instalador Setup.exe final.
    echo.
    echo El ejecutable portable ya esta listo en: dist\MyFFmpegGUI\
    echo =======================================================================
)

echo.
pause
