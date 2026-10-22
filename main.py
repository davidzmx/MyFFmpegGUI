#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MyFFmpeg GUI - Suite de Procesamiento Multimedia Sin Pérdida
Punto de entrada principal para Windows y Linux.
Soporta invocación directa desde menú contextual con argumentos:
  python3 main.py [--tab audio|video|frames|create|segment|concat|settings] [archivo]
"""

import sys
import os
import argparse
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt

import config_manager
from ui.styles import DARK_THEME_QSS, get_dark_palette, configure_dark_icon_theme
from ui.main_window import MainWindow


def parse_args():
    """Analiza argumentos de línea de comando para integración con menú contextual."""
    parser = argparse.ArgumentParser(description="MyFFmpeg GUI - Suite Multimedia Sin Pérdida")
    parser.add_argument(
        "--quick-action",
        dest="quick_action",
        default=None,
        help="ID de la acción rápida a ejecutar en segundo plano sin abrir GUI (ej. quick_mp3)"
    )
    parser.add_argument(
        "--tab",
        choices=["audio", "add_audio", "video", "frames", "create", "segment", "concat", "compare", "settings"],
        default=None,
        help="Pestaña a activar inicialmente al abrir la aplicación"
    )
    parser.add_argument(
        "--install-context",
        action="store_true",
        help="Instala las opciones del menú contextual en el sistema operativo y sale"
    )
    parser.add_argument(
        "--uninstall-context",
        action="store_true",
        help="Elimina las opciones del menú contextual del sistema operativo y sale"
    )
    parser.add_argument(
        "file_path",
        nargs="?",
        default=None,
        help="Ruta al archivo de video o audio a cargar automáticamente"
    )
    # Usar parse_known_args para permitir pasar flags de Qt sin errores
    known, _ = parser.parse_known_args()
    return known


def main():
    args = parse_args()

    # Si se solicitó instalar o desinstalar el menú contextual vía CLI (ideal para instaladores)
    if args.install_context:
        import context_menu_manager
        ok, msg = context_menu_manager.install_context_menu()
        print(msg)
        sys.exit(0 if ok else 1)

    if args.uninstall_context:
        import context_menu_manager
        ok, msg = context_menu_manager.uninstall_context_menu()
        print(msg)
        sys.exit(0 if ok else 1)

    # Si se solicitó una acción rápida por menú contextual, ejecutarla en segundo plano y salir
    if args.quick_action:
        import context_menu_manager
        success = context_menu_manager.execute_quick_action(args.quick_action, args.file_path)
        sys.exit(0 if success else 1)

    # En Windows, asignar ID explícito de aplicación para que la barra de tareas muestre el icono propio
    if sys.platform == "win32":
        try:
            import ctypes
            myappid = "davidzmx.myffmpeggui.app.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
    elif hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
        # En Linux/macOS, guardar estado original de la terminal para garantizar que
        # el eco de teclado (ECHO) y el modo canónico (ICANON) siempre se restablezcan al salir.
        orig_termios = None
        try:
            import termios
            fd = sys.stdin.fileno()
            orig_termios = termios.tcgetattr(fd)

            def restore_terminal():
                try:
                    termios.tcsetattr(fd, termios.TCSANOW, orig_termios)
                except Exception:
                    try:
                        os.system("stty sane 2>/dev/null")
                    except Exception:
                        pass

            import atexit
            atexit.register(restore_terminal)
        except Exception:
            pass

    # Habilitar soporte High DPI para pantallas 2K/4K en Windows y Linux
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Manejador global de excepciones para evitar cierres abruptos silenciosos
    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        import traceback
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"[ERROR NO CONTROLADO]:\n{tb_str}", file=sys.stderr)
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(
                None,
                "Error en la aplicación",
                f"Ocurrió un error inesperado:\n\n{exc_value}\n\nDetalles:\n{tb_str[:800]}"
            )
        except Exception:
            pass

    sys.excepthook = handle_unhandled_exception

    app = QApplication(sys.argv)
    app.setApplicationName("MyFFmpegGUI")
    app.setOrganizationName("MyTests")

    # Establecer icono de la aplicación (barra de tareas, ventanas y diálogos emergentes)
    icon_path = config_manager.get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # Configurar tema de iconos oscuro para máxima legibilidad en botones y carpetas
    configure_dark_icon_theme()

    # Establecer tipografía nativa del sistema para evitar recorte o deformación de fuentes
    font_family = "Segoe UI" if sys.platform == "win32" else "Ubuntu"
    app.setFont(QFont(font_family, 9 if sys.platform == "win32" else 10))

    # Aplicar paleta oscura del sistema (garantiza fondo oscuro en QFileDialog y vistas nativas)
    app.setPalette(get_dark_palette())

    # Aplicar hoja de estilos oscura moderna
    app.setStyleSheet(DARK_THEME_QSS)

    window = MainWindow(initial_tab=args.tab, initial_file=args.file_path)
    window.show()

    exit_code = 0
    try:
        exit_code = app.exec_()
    finally:
        if sys.platform != "win32" and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            try:
                import termios
                if 'orig_termios' in locals() and orig_termios is not None:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, orig_termios)
                else:
                    os.system("stty sane 2>/dev/null")
            except Exception:
                pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

