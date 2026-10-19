#!/usr/bin/env bash
# ==============================================================================
# Instalador de Usuario para Linux (Sin necesidad de permisos root / sudo)
# MyFFmpeg GUI - Suite Multimedia Sin Pérdida
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/myffmpeg-gui"
BIN_DIR="$HOME/.local/bin"
APP_DESKTOP="$HOME/.local/share/applications/myffmpeg-gui.desktop"

echo "=============================================================================="
echo "          INSTALADOR DE USUARIO PARA LINUX - MyFFmpeg GUI"
echo "               (Instalación en espacio de usuario sin sudo)"
echo "=============================================================================="
echo ""

# 1. Comprobar Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Error: Python 3 no está instalado en tu sistema."
    exit 1
fi

# 2. Comprobar PyQt5
if ! python3 -c "import PyQt5" >/dev/null 2>&1; then
    echo "⚠️ Advertencia: PyQt5 no parece estar instalado en tu entorno de Python."
    echo "   Puedes instalarlo fácilmente con:"
    echo "     pip install -r requirements.txt"
    echo "   o en Debian/Ubuntu con:"
    echo "     sudo apt install python3-pyqt5"
    echo ""
    read -p "¿Deseas continuar con la instalación de todos modos? (s/N): " resp
    if [[ ! "$resp" =~ ^[sSyY]$ ]]; then
        exit 1
    fi
fi

# 3. Crear carpetas de destino
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$HOME/.local/share/applications"

# 4. Copiar archivos de la aplicación
echo "[*] Instalando archivos en: $INSTALL_DIR ..."
cp "$PROJECT_DIR/main.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/ffmpeg_core.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/ffmpeg_worker.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/config_manager.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/context_menu_manager.py" "$INSTALL_DIR/"
cp -r "$PROJECT_DIR/ui" "$INSTALL_DIR/"

chmod +x "$INSTALL_DIR/main.py"

# 5. Crear ejecutable de acceso rápido en ~/.local/bin/myffmpeg-gui
PYTHON_BIN="$(which python3)"
cat << EOF > "$BIN_DIR/myffmpeg-gui"
#!/bin/sh
exec "$PYTHON_BIN" "$INSTALL_DIR/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/myffmpeg-gui"

# 6. Crear acceso directo en el Menú de Aplicaciones (.desktop)
cat << EOF > "$APP_DESKTOP"
[Desktop Entry]
Type=Application
Name=MyFFmpeg GUI
GenericName=Suite Multimedia FFmpeg
Comment=Herramienta gráfica y atajos rápidos para FFmpeg sin pérdida
Exec=$BIN_DIR/myffmpeg-gui
Icon=applications-multimedia
Terminal=false
Categories=AudioVideo;AudioVideoEditing;
EOF
chmod 644 "$APP_DESKTOP"

# 7. Actualizar base de datos de escritorios
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

# 8. Instalar integración con menú contextual (KDE Dolphin / GNOME Nautilus)
echo "[*] Integrando opciones en el menú contextual de clic derecho..."
"$PYTHON_BIN" "$INSTALL_DIR/main.py" --install-context

echo ""
echo "=============================================================================="
echo "🎉 [INSTALACION EXITOSA]"
echo "La suite MyFFmpeg GUI está instalada y lista para usarse:"
echo ""
echo "  1. Menú de Inicio: Busca 'MyFFmpeg GUI' en tu lanzador de aplicaciones."
echo "  2. Clic Derecho: Haz clic derecho sobre cualquier video o audio en Dolphin o Nautilus."
echo "  3. Desde Terminal: Ejecuta 'myffmpeg-gui'"
echo ""
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "ℹ️ Nota: Para ejecutar 'myffmpeg-gui' directamente en tu terminal actual,"
    echo "   asegúrate de que $BIN_DIR esté en tu PATH (añade 'export PATH=\"\$HOME/.local/bin:\$PATH\"' a tu ~/.bashrc)."
fi
echo "=============================================================================="
