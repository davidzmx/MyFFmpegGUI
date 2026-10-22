#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo para Gestión e Integración Dinámica en el Menú Contextual (Clic Derecho)
Soporta:
1. Atajos rápidos en segundo plano (sin abrir GUI) como "Convertir a MP3".
2. Configuración personalizada de atajos y apertura de herramientas.
3. Multiplataforma (Linux: KDE Dolphin, GNOME Nautilus, FreeDesktop | Windows: HKCU Explorer).
"""

import os
import sys
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Tuple, List, Dict, Optional

import config_manager
import ffmpeg_core


def get_main_script_path() -> str:
    """Devuelve la ruta absoluta al script principal main.py."""
    current_dir = Path(__file__).resolve().parent
    main_py = current_dir / "main.py"
    return str(main_py)


def get_python_executable() -> str:
    """Devuelve el ejecutable de python apropiado."""
    if sys.platform.startswith("win"):
        # En Windows, pythonw.exe evita abrir la consola negra de cmd
        exe = sys.executable
        if exe.lower().endswith("python.exe"):
            pythonw = exe[:-10] + "pythonw.exe"
            if os.path.exists(pythonw):
                return pythonw
        return exe
    return sys.executable or "python3"


def send_desktop_notification(title: str, message: str, timeout_sec: int = 4):
    """Envía una notificación de escritorio nativa y ligera sin bloquear."""
    try:
        if sys.platform.startswith("win"):
            # En Windows invocar balloon tooltip mediante PowerShell
            ps_script = (
                "[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
                "$notify = New-Object System.Windows.Forms.NotifyIcon; "
                "$notify.Icon = [System.Drawing.SystemIcons]::Information; "
                "$notify.Visible = $True; "
                f"$notify.ShowBalloonTip({timeout_sec * 1000}, '{title}', '{message}', [System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Seconds 1; "
                "$notify.Dispose();"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return

        # En Linux
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if hasattr(os, "setsid"):
            kwargs["start_new_session"] = True

        if shutil.which("kdialog"):
            subprocess.Popen(
                ["kdialog", "--title", title, "--passivepopup", message, str(timeout_sec)],
                **kwargs
            )
        elif shutil.which("zenity"):
            subprocess.Popen(
                ["zenity", "--notification", f"--text={title}\n{message}"],
                **kwargs
            )
        elif shutil.which("notify-send"):
            subprocess.Popen(
                ["notify-send", "-t", str(timeout_sec * 1000), title, message],
                **kwargs
            )
    except Exception:
        pass


def execute_quick_action(action_id: str, file_path: str) -> bool:
    """
    Ejecuta un atajo rápido en segundo plano sin abrir la interfaz gráfica.
    Reemplaza variables en la plantilla del comando y notifica al usuario.
    """
    import urllib.parse

    if not file_path:
        send_desktop_notification("MyFFmpeg GUI", "Error: No se especificó ningún archivo de entrada.")
        return False

    # Manejar posibles URIs tipo file:// pasadas por KDE / GNOME
    if file_path.startswith("file://"):
        parsed = urllib.parse.urlparse(file_path)
        file_path = urllib.parse.unquote(parsed.path)
    file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        send_desktop_notification("MyFFmpeg GUI", f"Error: Archivo no encontrado:\n{file_path}")
        return False

    actions = config_manager.get_context_actions()
    action = next((a for a in actions if a.get("id") == action_id), None)
    if not action:
        # Fallback para quick_mp3 si no se halló por id
        if action_id == "quick_mp3":
            action = {
                "id": "quick_mp3",
                "name": "Rápido: Convertir a MP3",
                "command_template": 'ffmpeg -y -i "{input}" "{output_no_ext}.mp3"'
            }
        else:
            send_desktop_notification("MyFFmpeg GUI", f"Error: Acción rápida '{action_id}' no encontrada.")
            return False

    input_dir = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    stem, ext = os.path.splitext(filename)
    output_no_ext = os.path.join(input_dir, stem)

    template = action.get("command_template")
    if not template:
        template = 'ffmpeg -y -i "{input}" "{output_no_ext}.mp3"'

    # Resolver ejecutable FFmpeg
    cfg = config_manager.load_config()
    configured_ffmpeg = cfg.get("ffmpeg_path")
    if not configured_ffmpeg or not os.path.isfile(configured_ffmpeg):
        configured_ffmpeg, _ = ffmpeg_core.get_default_ffmpeg_paths()
    if not configured_ffmpeg:
        configured_ffmpeg = "ffmpeg"

    action_name = action.get("name", "Conversión Rápida")
    send_desktop_notification("MyFFmpeg GUI", f"Iniciando: {action_name}\n{filename}")

    # Reemplazo de marcadores de posición
    cmd_str = template
    cmd_str = cmd_str.replace("{input}", file_path)
    cmd_str = cmd_str.replace("{output_dir}", input_dir)
    cmd_str = cmd_str.replace("{file_stem}", stem)
    cmd_str = cmd_str.replace("{output_no_ext}", output_no_ext)
    cmd_str = cmd_str.replace("{filename}", filename)
    cmd_str = cmd_str.replace("{ext}", ext)

    try:
        parts = [p.strip('"\'') for p in shlex.split(cmd_str, posix=False)]
        if parts and parts[0] == "ffmpeg":
            parts[0] = configured_ffmpeg
    except Exception:
        parts = [configured_ffmpeg, "-y", "-i", file_path, f"{output_no_ext}.mp3"]

    try:
        res = subprocess.run(parts, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if res.returncode == 0:
            send_desktop_notification(
                "MyFFmpeg GUI",
                f"Éxito: {action_name} finalizada:\n{stem}"
            )
            return True
        else:
            err_line = res.stderr.strip().splitlines()[-1] if res.stderr else f"Código {res.returncode}"
            send_desktop_notification(
                "MyFFmpeg GUI",
                f"Error en la conversión ({filename}):\n{err_line[:120]}"
            )
            return False
    except Exception as e:
        send_desktop_notification("MyFFmpeg GUI", f"Error al ejecutar proceso: {e}")
        return False


# ============================================================================
# GESTIÓN EN LINUX (KDE Dolphin, GNOME Nautilus, FreeDesktop)
# ============================================================================

def get_linux_destinations() -> Dict[str, Path]:
    """Devuelve las rutas de instalación en el directorio de usuario de Linux."""
    home = Path.home()
    return {
        "dolphin": home / ".local" / "share" / "kio" / "servicemenus" / "myffmpeg_actions.desktop",
        "desktop": home / ".local" / "share" / "applications" / "myffmpeg-gui.desktop",
        "nautilus_dir": home / ".local" / "share" / "nautilus" / "scripts" / "MyFFmpeg GUI",
    }


def generate_kde_dolphin_desktop(main_py: str, python_bin: str, actions: Optional[List[dict]] = None) -> str:
    """Genera el contenido del archivo de servicio para KDE Dolphin con las acciones activas ordenadas numéricamente."""
    if actions is None:
        actions = config_manager.get_context_actions()

    enabled_actions = [a for a in actions if a.get("enabled", True)]
    # Usar prefijo numérico 01_, 02_ para los IDs de acción y forzar orden determinista en KDE
    action_ids = [f"{idx:02d}_{a['id']}" for idx, a in enumerate(enabled_actions, start=1)]
    actions_line = ";".join(action_ids) + ";" if action_ids else ""

    lines = [
        "[Desktop Entry]",
        "Type=Service",
        "ServiceTypes=KonqPopupMenu/Plugin",
        "MimeType=video/mp4;video/x-matroska;video/quicktime;video/x-msvideo;video/webm;video/x-flv;video/mpeg;video/ogg;audio/mpeg;audio/x-wav;audio/mp4;audio/flac;audio/ogg;all/allfiles;",
        f"Actions={actions_line}",
        "X-KDE-Submenu=MyFFmpeg GUI",
        "X-KDE-Priority=TopLevel",
        ""
    ]

    for idx, a in enumerate(enabled_actions, start=1):
        a_id = f"{idx:02d}_{a['id']}"
        base_name = a.get("name", "Acción")
        # Prefijo numérico en el nombre para garantizar que KDE respete la secuencia visual
        name = f"{idx}. {base_name}"
        icon = a.get("icon", "video-x-generic")

        if a.get("type") == "quick":
            exec_cmd = f'{python_bin} "{main_py}" --quick-action "{a["id"]}" %f'
        else:
            tab = a.get("tab")
            tab_flag = f'--tab {tab}' if tab else ''
            exec_cmd = f'{python_bin} "{main_py}" {tab_flag} %f'.strip()

        lines.extend([
            f"[Desktop Action {a_id}]",
            f"Name={name}",
            f"Icon={icon}",
            f"Exec={exec_cmd}",
            ""
        ])

    return "\n".join(lines)


def generate_freedesktop_app(main_py: str, python_bin: str, actions: Optional[List[dict]] = None) -> str:
    """
    Genera la entrada .desktop para el menú de aplicaciones / inicio del sistema.
    No define MimeType ni Actions para evitar que el explorador de archivos muestre
    un 'Abrir con MyFFmpeg GUI' no deseado en la raíz del menú contextual.
    """
    return f"""[Desktop Entry]
Type=Application
Name=MyFFmpeg GUI
GenericName=Suite Multimedia FFmpeg
Comment=Herramienta gráfica y atajos rápidos para FFmpeg sin pérdida
Exec={python_bin} "{main_py}"
Icon=applications-multimedia
Terminal=false
Categories=AudioVideo;AudioVideoEditing;
"""


def install_linux_context_menu(main_py: str = None, python_bin: str = None, actions: Optional[List[dict]] = None) -> Tuple[bool, str]:
    """Instala las opciones de clic derecho para KDE Dolphin, GNOME y el sistema Linux."""
    main_py = main_py or get_main_script_path()
    python_bin = python_bin or get_python_executable()
    actions = actions or config_manager.get_context_actions()
    dests = get_linux_destinations()
    installed_places = []

    try:
        # 1. KDE Dolphin ServiceMenu
        dolphin_path = dests["dolphin"]
        dolphin_path.parent.mkdir(parents=True, exist_ok=True)
        dolphin_content = generate_kde_dolphin_desktop(main_py, python_bin, actions)
        dolphin_path.write_text(dolphin_content, encoding="utf-8")
        dolphin_path.chmod(0o755)
        installed_places.append("KDE Plasma (Dolphin)")

        # 2. FreeDesktop .desktop
        desktop_path = dests["desktop"]
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        desktop_content = generate_freedesktop_app(main_py, python_bin, actions)
        desktop_path.write_text(desktop_content, encoding="utf-8")
        desktop_path.chmod(0o755)
        installed_places.append("Lanzador de aplicaciones y 'Abrir con...'")

        # 3. GNOME / Nautilus scripts
        nautilus_dir = dests["nautilus_dir"]
        if nautilus_dir.exists():
            shutil.rmtree(nautilus_dir, ignore_errors=True)
        nautilus_dir.mkdir(parents=True, exist_ok=True)

        idx = 1
        for a in actions:
            if not a.get("enabled", True):
                continue
            name = a.get("name", f"Accion {idx}")
            clean_name = f"{idx}. {name}".replace("/", "-")

            if a.get("type") == "quick":
                script_body = (
                    f'#!/bin/bash\n'
                    f'{python_bin} "{main_py}" --quick-action "{a["id"]}" "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS"\n'
                )
            else:
                tab = a.get("tab")
                tab_flag = f'--tab {tab}' if tab else ''
                script_body = (
                    f'#!/bin/bash\n'
                    f'{python_bin} "{main_py}" {tab_flag} "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS"\n'
                )

            s_file = nautilus_dir / clean_name
            s_file.write_text(script_body, encoding="utf-8")
            s_file.chmod(0o755)
            idx += 1

        installed_places.append("GNOME Files (Nautilus scripts)")

        if shutil.which("update-desktop-database"):
            try:
                subprocess.run(
                    ["update-desktop-database", str(desktop_path.parent)],
                    capture_output=True,
                    timeout=3
                )
            except Exception:
                pass

        # Reconstruir caché de servicios de KDE para reflejar inmediatamente el nuevo orden en Dolphin
        for ksycoca_bin in ("kbuildsycoca5", "kbuildsycoca6"):
            if shutil.which(ksycoca_bin):
                try:
                    subprocess.run(
                        [ksycoca_bin, "--noincremental"],
                        capture_output=True,
                        timeout=3
                    )
                    break
                except Exception:
                    pass

        return True, f"Instalado exitosamente en: {', '.join(installed_places)}"

    except Exception as e:
        return False, f"Error al instalar en Linux: {e}"


def uninstall_linux_context_menu() -> Tuple[bool, str]:
    """Elimina las entradas de clic derecho instaladas en Linux."""
    dests = get_linux_destinations()
    removed = []

    try:
        if dests["dolphin"].exists():
            dests["dolphin"].unlink()
            removed.append("KDE Dolphin")

        if dests["desktop"].exists():
            dests["desktop"].unlink()
            removed.append("Menú de aplicaciones")

        if dests["nautilus_dir"].exists():
            shutil.rmtree(dests["nautilus_dir"], ignore_errors=True)
            removed.append("Nautilus scripts")

        if shutil.which("update-desktop-database"):
            try:
                subprocess.run(
                    ["update-desktop-database", str(dests["desktop"].parent)],
                    capture_output=True,
                    timeout=3
                )
            except Exception:
                pass

        for ksycoca_bin in ("kbuildsycoca5", "kbuildsycoca6"):
            if shutil.which(ksycoca_bin):
                try:
                    subprocess.run(
                        [ksycoca_bin, "--noincremental"],
                        capture_output=True,
                        timeout=3
                    )
                    break
                except Exception:
                    pass

        return True, f"Desinstalado correctamente de: {', '.join(removed) if removed else 'Ninguna entrada activa'}"
    except Exception as e:
        return False, f"Error al desinstalar: {e}"


def is_linux_context_menu_installed() -> bool:
    """Verifica si las entradas de clic derecho de Linux existen."""
    dests = get_linux_destinations()
    return dests["dolphin"].exists() or dests["desktop"].exists() or dests["nautilus_dir"].exists()


# ============================================================================
# GESTIÓN EN WINDOWS (Registro HKCU y archivos .reg)
# ============================================================================

def generate_windows_reg_content(main_py: str = None, python_bin: str = None, actions: Optional[List[dict]] = None) -> str:
    """
    Genera el archivo .reg para Windows Explorer basado en las acciones activas.
    Usa HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations
    por lo que no requiere ningún permiso de administrador.
    """
    is_frozen = getattr(sys, "frozen", False) and (main_py is None and python_bin is None)
    if is_frozen:
        esc_exe = sys.executable.replace("\\", "\\\\")
        icon_entry = f'"Icon"="\\"{esc_exe}\\",0"'
    else:
        main_py = main_py or get_main_script_path()
        python_bin = python_bin or get_python_executable()
        esc_main = main_py.replace("\\", "\\\\")
        esc_python = python_bin.replace("\\", "\\\\")
        icon_entry = f'"Icon"="\\"{esc_python}\\",0"'

    if actions is None:
        actions = config_manager.get_context_actions()

    enabled_actions = [a for a in actions if a.get("enabled", True)]

    lines = [
        "Windows Registry Editor Version 5.00",
        "",
        "; ========================================================",
        "; MyFFmpeg GUI - Menú Contextual Configurable (Windows)",
        "; Sin necesidad de permisos de Administrador (HKEY_CURRENT_USER)",
        "; ========================================================",
        "",
        "[HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\video\\shell\\MyFFmpegGUI]",
        '"MUIVerb"="MyFFmpeg GUI"',
        '"SubCommands"=""',
        icon_entry,
        ""
    ]

    for idx, a in enumerate(enabled_actions, start=1):
        sub_key = f"{idx:02d}_{a['id']}"
        base_name = a.get("name", "Acción").replace('"', '\\"')
        name = f"{idx}. {base_name}"

        if is_frozen:
            if a.get("type") == "quick":
                cmd = f'\\"{esc_exe}\\" --quick-action \\"{a["id"]}\\" \\"%1\\"'
            else:
                tab = a.get("tab")
                tab_flag = f'--tab {tab}' if tab else ''
                cmd = f'\\"{esc_exe}\\" {tab_flag} \\"%1\\"'.replace("  ", " ").strip()
        else:
            if a.get("type") == "quick":
                cmd = f'\\"{esc_python}\\" \\"{esc_main}\\" --quick-action \\"{a["id"]}\\" \\"%1\\"'
            else:
                tab = a.get("tab")
                tab_flag = f'--tab {tab}' if tab else ''
                cmd = f'\\"{esc_python}\\" \\"{esc_main}\\" {tab_flag} \\"%1\\"'.replace("  ", " ").strip()

        lines.extend([
            f"[HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\video\\shell\\MyFFmpegGUI\\shell\\{sub_key}]",
            f'@="{name}"',
            "",
            f"[HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\video\\shell\\MyFFmpegGUI\\shell\\{sub_key}\\command]",
            f'@="{cmd}"',
            ""
        ])

    # Submenú también en audio
    lines.extend([
        "[HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\audio\\shell\\MyFFmpegGUI]",
        '"MUIVerb"="MyFFmpeg GUI"',
        '"SubCommands"=""',
        icon_entry,
        ""
    ])

    for idx, a in enumerate(enabled_actions, start=1):
        sub_key = f"{idx:02d}_{a['id']}"
        base_name = a.get("name", "Acción").replace('"', '\\"')
        name = f"{idx}. {base_name}"

        if is_frozen:
            if a.get("type") == "quick":
                cmd = f'\\"{esc_exe}\\" --quick-action \\"{a["id"]}\\" \\"%1\\"'
            else:
                tab = a.get("tab")
                tab_flag = f'--tab {tab}' if tab else ''
                cmd = f'\\"{esc_exe}\\" {tab_flag} \\"%1\\"'.replace("  ", " ").strip()
        else:
            if a.get("type") == "quick":
                cmd = f'\\"{esc_python}\\" \\"{esc_main}\\" --quick-action \\"{a["id"]}\\" \\"%1\\"'
            else:
                tab = a.get("tab")
                tab_flag = f'--tab {tab}' if tab else ''
                cmd = f'\\"{esc_python}\\" \\"{esc_main}\\" {tab_flag} \\"%1\\"'.replace("  ", " ").strip()

        lines.extend([
            f"[HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\audio\\shell\\MyFFmpegGUI\\shell\\{sub_key}]",
            f'@="{name}"',
            "",
            f"[HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\audio\\shell\\MyFFmpegGUI\\shell\\{sub_key}\\command]",
            f'@="{cmd}"',
            ""
        ])

    return "\n".join(lines)


def generate_windows_unreg_content() -> str:
    """Genera el contenido del archivo .reg para desinstalar de Windows Explorer."""
    return """Windows Registry Editor Version 5.00

; ========================================================
; Desinstalador de Menú Contextual MyFFmpeg GUI
; ========================================================

[-HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\video\\shell\\MyFFmpegGUI]
[-HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\audio\\shell\\MyFFmpegGUI]
"""


def export_windows_reg_files(target_dir: str = None, actions: Optional[List[dict]] = None) -> Tuple[str, str]:
    """Crea los archivos .reg listos para usar en Windows en la carpeta destino."""
    if not target_dir:
        target_dir = str(Path(__file__).resolve().parent)
    dest = Path(target_dir)

    install_file = dest / "instalar_menu_contextual_windows.reg"
    uninstall_file = dest / "desinstalar_menu_contextual_windows.reg"

    install_file.write_text(generate_windows_reg_content(actions=actions), encoding="utf-16le")
    uninstall_file.write_text(generate_windows_unreg_content(), encoding="utf-16le")

    return str(install_file), str(uninstall_file)


def install_windows_context_menu(main_py: str = None, python_bin: str = None, actions: Optional[List[dict]] = None) -> Tuple[bool, str]:
    """Registra las claves en Windows usando winreg directamente con las acciones configuradas."""
    if not sys.platform.startswith("win"):
        inst, uninst = export_windows_reg_files(actions=actions)
        return True, f"Se han generado los archivos de registro de Windows con tus acciones personalizadas:\n{inst}"

    try:
        import winreg

        main_py = main_py or get_main_script_path()
        python_bin = python_bin or get_python_executable()
        if actions is None:
            actions = config_manager.get_context_actions()

        enabled_actions = [a for a in actions if a.get("enabled", True)]

        def set_val(root, subkey, val_name, val):
            with winreg.CreateKey(root, subkey) as k:
                winreg.SetValueEx(k, val_name, 0, winreg.REG_SZ, val)

        def delete_key_tree(root, path):
            try:
                with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
                    while True:
                        try:
                            sub = winreg.EnumKey(key, 0)
                            delete_key_tree(root, f"{path}\\{sub}")
                        except OSError:
                            break
                winreg.DeleteKey(root, path)
            except FileNotFoundError:
                pass

        # Limpiar entradas anteriores para evitar huérfanos
        delete_key_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\video\shell\MyFFmpegGUI")
        delete_key_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\audio\shell\MyFFmpegGUI")

        is_frozen = getattr(sys, "frozen", False)
        exe_path = sys.executable

        for category in ("video", "audio"):
            base_key = rf"Software\Classes\SystemFileAssociations\{category}\shell\MyFFmpegGUI"
            set_val(winreg.HKEY_CURRENT_USER, base_key, "MUIVerb", "MyFFmpeg GUI")
            set_val(winreg.HKEY_CURRENT_USER, base_key, "SubCommands", "")
            icon_val = f'"{exe_path}",0' if is_frozen else f'"{python_bin}",0'
            set_val(winreg.HKEY_CURRENT_USER, base_key, "Icon", icon_val)

            for idx, a in enumerate(enabled_actions, start=1):
                sub_key = f"{idx:02d}_{a['id']}"
                s_key_path = f"{base_key}\\shell\\{sub_key}"
                base_name = a.get("name", "Acción")
                name = f"{idx}. {base_name}"
                set_val(winreg.HKEY_CURRENT_USER, s_key_path, "", name)

                if is_frozen:
                    if a.get("type") == "quick":
                        cmd = f'"{exe_path}" --quick-action "{a["id"]}" "%1"'
                    else:
                        tab = a.get("tab")
                        tab_flag = f'--tab {tab}' if tab else ''
                        cmd = f'"{exe_path}" {tab_flag} "%1"'.replace("  ", " ").strip()
                else:
                    if a.get("type") == "quick":
                        cmd = f'"{python_bin}" "{main_py}" --quick-action "{a["id"]}" "%1"'
                    else:
                        tab = a.get("tab")
                        tab_flag = f'--tab {tab}' if tab else ''
                        cmd = f'"{python_bin}" "{main_py}" {tab_flag} "%1"'.replace("  ", " ").strip()

                set_val(winreg.HKEY_CURRENT_USER, f"{s_key_path}\\command", "", cmd)

        return True, "Menú contextual de Windows Explorer actualizado exitosamente en HKEY_CURRENT_USER."
    except Exception as e:
        return False, f"Error al registrar en Windows: {e}"


def uninstall_windows_context_menu() -> Tuple[bool, str]:
    """Elimina las claves de menú contextual de Windows."""
    if not sys.platform.startswith("win"):
        return True, "No se encuentra en Windows. Se mantienen los archivos .reg generados."

    try:
        import winreg

        def delete_key_tree(root, path):
            try:
                with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
                    while True:
                        try:
                            sub = winreg.EnumKey(key, 0)
                            delete_key_tree(root, f"{path}\\{sub}")
                        except OSError:
                            break
                winreg.DeleteKey(root, path)
            except FileNotFoundError:
                pass

        delete_key_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\video\shell\MyFFmpegGUI")
        delete_key_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\audio\shell\MyFFmpegGUI")
        return True, "Menú contextual desinstalado de Windows Explorer."
    except Exception as e:
        return False, f"Error al desinstalar en Windows: {e}"


def is_windows_context_menu_installed() -> bool:
    """Verifica si el menú contextual de Windows está registrado en el registro."""
    if not sys.platform.startswith("win"):
        return False

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\SystemFileAssociations\video\shell\MyFFmpegGUI"
        )
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


# ============================================================================
# API UNIFICADA MULTIPLATAFORMA
# ============================================================================

def install_context_menu(actions: Optional[List[dict]] = None) -> Tuple[bool, str]:
    """Instala el menú contextual en el sistema actual (Windows o Linux)."""
    if sys.platform.startswith("win"):
        return install_windows_context_menu(actions=actions)
    else:
        return install_linux_context_menu(actions=actions)


def uninstall_context_menu() -> Tuple[bool, str]:
    """Desinstala el menú contextual del sistema actual."""
    if sys.platform.startswith("win"):
        return uninstall_windows_context_menu()
    else:
        return uninstall_linux_context_menu()


def is_context_menu_installed() -> bool:
    """Comprueba si el menú contextual está instalado en el sistema actual."""
    if sys.platform.startswith("win"):
        return is_windows_context_menu_installed()
    else:
        return is_linux_context_menu_installed()
