#!/usr/bin/env bash
# ==============================================================================
# Desinstalador de Usuario para Linux
# MyFFmpeg GUI - Suite Multimedia Sin Pérdida
# ==============================================================================
set -e

INSTALL_DIR="$HOME/.local/share/myffmpeg-gui"
BIN_LINK="$HOME/.local/bin/myffmpeg-gui"
APP_DESKTOP="$HOME/.local/share/applications/myffmpeg-gui.desktop"

echo "=============================================================================="
echo "          DESINSTALADOR DE USUARIO PARA LINUX - MyFFmpeg GUI"
echo "=============================================================================="
echo ""

# 1. Desinstalar menú contextual si python3 y main.py existen
if [ -f "$INSTALL_DIR/main.py" ] && command -v python3 >/dev/null 2>&1; then
    echo "[*] Desinstalando opciones del menú contextual..."
    python3 "$INSTALL_DIR/main.py" --uninstall-context >/dev/null 2>&1 || true
fi

# 2. Eliminar lanzadores
if [ -f "$BIN_LINK" ]; then
    echo "[*] Eliminando enlace ejecutable $BIN_LINK..."
    rm -f "$BIN_LINK"
fi

if [ -f "$APP_DESKTOP" ]; then
    echo "[*] Eliminando lanzador de aplicaciones $APP_DESKTOP..."
    rm -f "$APP_DESKTOP"
fi

# 3. Eliminar archivos de la aplicación
if [ -d "$INSTALL_DIR" ]; then
    echo "[*] Eliminando carpeta de aplicación $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
fi

# 4. Actualizar base de datos de escritorios
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

echo ""
echo "=============================================================================="
echo "✅ MyFFmpeg GUI ha sido desinstalado completamente de tu sistema."
echo "=============================================================================="
