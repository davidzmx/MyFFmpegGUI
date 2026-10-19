#!/usr/bin/env bash
# ==============================================================================
# Generador de Paquete de Instalación Debian / Ubuntu (.deb) para MyFFmpeg GUI
# ==============================================================================
set -e

APP_NAME="myffmpeg-gui"
APP_VERSION="1.0.0"
ARCH="all"
PKG_DIR="build_deb_pkg"
DEB_NAME="${APP_NAME}_${APP_VERSION}_${ARCH}.deb"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================================================================="
echo "      CONSTRUCTOR DE PAQUETE DE INSTALACION LINUX (.deb) - MyFFmpeg GUI"
echo "=============================================================================="
echo ""

# 1. Limpiar directorio temporal previo
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/myffmpeg-gui"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/scalable/apps"

# 2. Copiar archivos de la aplicación a /usr/share/myffmpeg-gui
echo "[*] Copiando archivos de la aplicacion..."
cp "$PROJECT_DIR/main.py" "$PKG_DIR/usr/share/myffmpeg-gui/"
cp "$PROJECT_DIR/ffmpeg_core.py" "$PKG_DIR/usr/share/myffmpeg-gui/"
cp "$PROJECT_DIR/ffmpeg_worker.py" "$PKG_DIR/usr/share/myffmpeg-gui/"
cp "$PROJECT_DIR/config_manager.py" "$PKG_DIR/usr/share/myffmpeg-gui/"
cp "$PROJECT_DIR/context_menu_manager.py" "$PKG_DIR/usr/share/myffmpeg-gui/"
cp -r "$PROJECT_DIR/ui" "$PKG_DIR/usr/share/myffmpeg-gui/"

# Permisos de ejecución
chmod +x "$PKG_DIR/usr/share/myffmpeg-gui/main.py"

# 3. Crear script lanzador en /usr/bin/myffmpeg-gui
cat << 'EOF' > "$PKG_DIR/usr/bin/myffmpeg-gui"
#!/bin/sh
exec /usr/bin/python3 /usr/share/myffmpeg-gui/main.py "$@"
EOF
chmod +x "$PKG_DIR/usr/bin/myffmpeg-gui"

# 4. Crear archivo lanzador .desktop para el menú de inicio
cat << 'EOF' > "$PKG_DIR/usr/share/applications/myffmpeg-gui.desktop"
[Desktop Entry]
Type=Application
Name=MyFFmpeg GUI
GenericName=Suite Multimedia FFmpeg
Comment=Herramienta gráfica y atajos rápidos para FFmpeg sin pérdida
Exec=/usr/bin/myffmpeg-gui
Icon=applications-multimedia
Terminal=false
Categories=AudioVideo;AudioVideoEditing;
EOF
chmod 644 "$PKG_DIR/usr/share/applications/myffmpeg-gui.desktop"

# 5. Generar archivo de control DEBIAN/control
cat << EOF > "$PKG_DIR/DEBIAN/control"
Package: $APP_NAME
Version: $APP_VERSION
Section: video
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.8), python3-pyqt5, ffmpeg
Maintainer: MyTests <soporte@mytests.local>
Description: Suite de procesamiento multimedia sin perdida basada en FFmpeg
 Interfaz grafica moderna y elegante para conversion sin perdida,
 extraccion de fotogramas, corte, union de segmentos y menu
 contextual interactivo para KDE Dolphin y GNOME Nautilus.
EOF

# 6. Script post-instalación (postinst)
cat << 'EOF' > "$PKG_DIR/DEBIAN/postinst"
#!/bin/sh
set -e

# Actualizar base de datos de escritorios
if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

echo "================================================================="
echo " MyFFmpeg GUI se ha instalado exitosamente."
echo " Puedes iniciarlo desde tu menu de aplicaciones o con el comando:"
echo "   myffmpeg-gui"
echo ""
echo " Para activar la integracion con clic derecho en tu usuario,"
echo " ejecuta una vez en terminal o pulsa 'Ajustes' en la aplicacion:"
echo "   myffmpeg-gui --install-context"
echo "================================================================="
exit 0
EOF
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# 7. Script post-desinstalación (postrm)
cat << 'EOF' > "$PKG_DIR/DEBIAN/postrm"
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if which update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
fi
exit 0
EOF
chmod 755 "$PKG_DIR/DEBIAN/postrm"

# 8. Empaquetar con dpkg-deb
mkdir -p "$PROJECT_DIR/dist"
echo "[*] Construyendo paquete debian $DEB_NAME..."
dpkg-deb --build --root-owner-group "$PKG_DIR" "$PROJECT_DIR/dist/$DEB_NAME"

# 9. Limpiar carpeta temporal
rm -rf "$PKG_DIR"

echo ""
echo "=============================================================================="
echo "[EXITO] Paquete instalador .deb generado en:"
echo "  $PROJECT_DIR/dist/$DEB_NAME"
echo ""
echo "Para instalarlo en cualquier sistema Debian, Ubuntu o derivados ejecuta:"
echo "  sudo apt install ./dist/$DEB_NAME"
echo "  o haz doble clic sobre el archivo en el explorador de archivos."
echo "=============================================================================="
