#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Suite Completa para MyFFmpegGUI
Verifica:
1. Rutas y versión de FFmpeg/FFprobe.
2. Extracción de metadatos con FFprobe.
3. Conversión de Video a MP3 y a WAV.
4. Conversión entre formatos de video (MP4 a MKV, WebM, etc.).
5. Extracción de fotogramas sin pérdida (PNG).
6. Ensamblado de video a partir de fotogramas.
7. Segmentación (Split) y Unión (Concat demuxer sin pérdida).
8. Configuración de Carpeta Base y Sugerencia de Subcarpetas.
9. Inicialización de la GUI con las 7 pestañas.
"""

import os
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path

from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
import ffmpeg_core
import config_manager


class TestFFmpegSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ui.styles import DARK_THEME_QSS, get_dark_palette, configure_dark_icon_theme
        cls.app = QApplication.instance() or QApplication(sys.argv)
        from PyQt5.QtGui import QFont
        font_family = "Segoe UI" if sys.platform == "win32" else "Ubuntu"
        cls.app.setFont(QFont(font_family, 9 if sys.platform == "win32" else 10))
        configure_dark_icon_theme()
        cls.app.setPalette(get_dark_palette())
        cls.app.setStyleSheet(DARK_THEME_QSS)
        cls.ffmpeg_path, cls.ffprobe_path = ffmpeg_core.get_default_ffmpeg_paths()
        print(f"\n[TEST SETUP] FFmpeg: {cls.ffmpeg_path} | FFprobe: {cls.ffprobe_path}")

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = self.tmp_dir.name

        # Generar un video sintético de prueba de 5 segundos con audio
        self.test_video = os.path.join(self.tmp_path, "sample_test.mp4")
        cmd_gen = [
            self.ffmpeg_path, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            self.test_video
        ]
        res = subprocess.run(cmd_gen, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 0, "No se pudo generar el video sintético de prueba")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_01_paths_and_version(self):
        self.assertTrue(self.ffmpeg_path and os.path.isfile(self.ffmpeg_path))
        ver = ffmpeg_core.get_ffmpeg_version(self.ffmpeg_path)
        self.assertIn("ffmpeg", ver.lower())

    def test_02_media_info(self):
        info = ffmpeg_core.get_media_info(self.test_video, self.ffprobe_path)
        self.assertGreater(info["duration"], 3.5)
        self.assertEqual(info["width"], 320)
        self.assertEqual(info["height"], 240)
        self.assertEqual(info["video_codec"], "h264")
        self.assertEqual(info["audio_codec"], "aac")

    def test_03a_convert_to_mp3(self):
        out_mp3 = os.path.join(self.tmp_path, "output.mp3")
        cmd = ffmpeg_core.build_audio_convert_command(
            self.ffmpeg_path, self.test_video, out_mp3, mode="mp3_320k"
        )
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 0)
        self.assertTrue(os.path.isfile(out_mp3))
        self.assertGreater(os.path.getsize(out_mp3), 1000)

    def test_03b_convert_to_wav(self):
        out_wav = os.path.join(self.tmp_path, "output.wav")
        cmd = ffmpeg_core.build_audio_convert_command(
            self.ffmpeg_path, self.test_video, out_wav, mode="wav_16", sample_rate=44100
        )
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 0)
        self.assertTrue(os.path.isfile(out_wav))
        # Verificar con ffprobe que el códec de audio sea pcm_s16le
        info = ffmpeg_core.get_media_info(out_wav, self.ffprobe_path)
        self.assertEqual(info["audio_codec"], "pcm_s16le")

    def test_04_convert_video_format(self):
        # Conversión de MP4 a MKV con Stream Copy (Sin Pérdida)
        out_mkv = os.path.join(self.tmp_path, "converted.mkv")
        cmd_copy = ffmpeg_core.build_convert_video_command(
            self.ffmpeg_path, self.test_video, out_mkv, mode="copy"
        )
        res_copy = subprocess.run(cmd_copy, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_copy.returncode, 0)
        self.assertTrue(os.path.isfile(out_mkv))

        # Conversión de MP4 a WebM
        out_webm = os.path.join(self.tmp_path, "converted.webm")
        cmd_webm = ffmpeg_core.build_convert_video_command(
            self.ffmpeg_path, self.test_video, out_webm, mode="vp9", audio_mode="aac"
        )
        res_webm = subprocess.run(cmd_webm, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_webm.returncode, 0)
        self.assertTrue(os.path.isfile(out_webm))

    def test_05_extract_frames(self):
        frames_pattern = os.path.join(self.tmp_path, "frame_%04d.png")
        cmd = ffmpeg_core.build_extract_frames_command(
            self.ffmpeg_path, self.test_video, frames_pattern, fmt="png", fps_mode="all"
        )
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 0)
        frames = [f for f in os.listdir(self.tmp_path) if f.startswith("frame_") and f.endswith(".png")]
        self.assertGreaterEqual(len(frames), 100)

    def test_06_create_video_from_frames(self):
        frames_pattern = os.path.join(self.tmp_path, "seq_%03d.png")
        cmd_extract = ffmpeg_core.build_extract_frames_command(
            self.ffmpeg_path, self.test_video, frames_pattern, fmt="png", fps_mode="all", duration="1"
        )
        subprocess.run(cmd_extract, check=True)

        out_assembled = os.path.join(self.tmp_path, "assembled.mp4")
        cmd_create = ffmpeg_core.build_create_video_command(
            self.ffmpeg_path, frames_pattern, out_assembled, fps=30.0, codec_preset="h264_lossless"
        )
        res = subprocess.run(cmd_create, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 0)
        self.assertTrue(os.path.isfile(out_assembled))
        self.assertGreater(os.path.getsize(out_assembled), 5000)

    def test_07_segment_and_concat(self):
        seg_pattern = os.path.join(self.tmp_path, "part_%03d.mp4")
        cmd_seg = ffmpeg_core.build_segment_command(
            self.ffmpeg_path, self.test_video, seg_pattern, segment_duration_sec=2, mode="exact"
        )
        res_seg = subprocess.run(cmd_seg, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_seg.returncode, 0)

        segments = sorted([
            os.path.join(self.tmp_path, f)
            for f in os.listdir(self.tmp_path)
            if f.startswith("part_") and f.endswith(".mp4")
        ])
        self.assertGreaterEqual(len(segments), 2)

        # Unir de nuevo mediante concat demuxer
        list_txt = os.path.join(self.tmp_path, "list.txt")
        ffmpeg_core.create_concat_list_file(segments, list_txt)

        out_merged = os.path.join(self.tmp_path, "merged.mp4")
        cmd_concat = ffmpeg_core.build_concat_command(
            self.ffmpeg_path, list_txt, out_merged, mode="copy"
        )
        res_concat = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_concat.returncode, 0)
        self.assertTrue(os.path.isfile(out_merged))

    def test_08_base_dir_and_subfolder_suggestion(self):
        base_dir = os.path.join(self.tmp_path, "MyBaseOutput")
        test_file = os.path.join(self.tmp_path, "vacaciones_2026.mp4")

        # 1. Guardar en la misma carpeta que el original (mismo nombre, nueva extensión)
        # como en: ffmpeg -i "mi_archivo.mp4" "mi_archivo.mp3"
        same_folder_mp3 = config_manager.suggest_output_path(
            test_file,
            suffix="",
            extension=".mp3",
            same_folder_as_input=True
        )
        self.assertEqual(same_folder_mp3, os.path.join(self.tmp_path, "vacaciones_2026.mp3"))

        # Con WAV
        same_folder_wav = config_manager.suggest_output_path(
            test_file,
            suffix="",
            extension=".wav",
            same_folder_as_input=True
        )
        self.assertEqual(same_folder_wav, os.path.join(self.tmp_path, "vacaciones_2026.wav"))

        # Con misma extensión (.mp4 a .mp4) debe añadir _convertido para no sobreescribir el original
        same_folder_mp4 = config_manager.suggest_output_path(
            test_file,
            suffix="",
            extension=".mp4",
            same_folder_as_input=True
        )
        self.assertEqual(same_folder_mp4, os.path.join(self.tmp_path, "vacaciones_2026_convertido.mp4"))

        # 2. Con sugerencia de subcarpeta en Carpeta Base activada
        suggested_with_sub = config_manager.suggest_output_path(
            test_file,
            suffix="_audio",
            extension=".wav",
            override_base_dir=base_dir,
            override_auto_subfolders=True,
            same_folder_as_input=False
        )
        expected_with = os.path.join(base_dir, "vacaciones_2026", "vacaciones_2026_audio.wav")
        self.assertEqual(suggested_with_sub, expected_with)

        # 3. Con sugerencia en Carpeta Base desactivada
        suggested_without_sub = config_manager.suggest_output_path(
            test_file,
            suffix="_audio",
            extension=".wav",
            override_base_dir=base_dir,
            override_auto_subfolders=False,
            same_folder_as_input=False
        )
        expected_without = os.path.join(base_dir, "vacaciones_2026_audio.wav")
        self.assertEqual(suggested_without_sub, expected_without)

        # Creación automática de carpeta si no existe
        config_manager.ensure_dir_exists(os.path.dirname(suggested_with_sub))
        self.assertTrue(os.path.isdir(os.path.dirname(suggested_with_sub)))

    def test_09_gui_initialization(self):
        from ui.main_window import MainWindow
        win = MainWindow()
        self.assertIsNotNone(win)
        # 10 pestañas completas (incluye Aislar Voces)
        self.assertEqual(win.tabs.count(), 10)
        win.close()

    def test_10_command_preview_and_base_folder_visibility(self):
        from ui.main_window import MainWindow
        win = MainWindow()
        win.show()

        # 1. Verificar format_command_for_display
        sample_cmd = ["ffmpeg", "-i", "/tmp/espacio en nombre.mp4", "-c:v", "copy", "/tmp/salida.mkv"]
        formatted = ffmpeg_core.format_command_for_display(sample_cmd)
        self.assertTrue(formatted.startswith("ffmpeg"))
        self.assertIn("espacio en nombre.mp4", formatted)

        # 2. Verificar visibilidad en TabAudio
        audio_tab = win.tab_audio
        audio_tab.radio_same_folder.setChecked(True)
        self.assertTrue(audio_tab.container_base_opts.isHidden())

        audio_tab.radio_base_folder.setChecked(True)
        self.assertFalse(audio_tab.container_base_opts.isHidden())
        self.assertIn("Carpeta Base actual:", audio_tab.lbl_base_info.text())

        # Probar preview de comando en audio
        audio_tab.input_selector.set_path(self.test_video)
        cmd_text = audio_tab.cmd_preview.get_command()
        self.assertTrue(len(cmd_text) > 0)
        self.assertTrue(audio_tab.cmd_preview.btn_copy.isEnabled())

        # 3. Verificar visibilidad en TabConvertVideo
        win.tabs.setCurrentIndex(1)
        convert_tab = win.tab_convert
        convert_tab.radio_same_folder.setChecked(True)
        self.assertTrue(convert_tab.container_base_opts.isHidden())

        convert_tab.radio_base_folder.setChecked(True)
        self.assertFalse(convert_tab.container_base_opts.isHidden())
        self.assertIn("Carpeta Base actual:", convert_tab.lbl_base_info.text())

        convert_tab.input_selector.set_path(self.test_video)
        cmd_text_conv = convert_tab.cmd_preview.get_command()
        self.assertTrue(len(cmd_text_conv) > 0)
        self.assertTrue(convert_tab.cmd_preview.btn_copy.isEnabled())

        win.close()

    def test_11_file_dialog_dark_palette_and_contrast(self):
        from PyQt5.QtWidgets import QFileDialog
        from PyQt5.QtGui import QPalette

        dlg = QFileDialog(None, "Test Dialog", "/home/david")
        # Verificar que la paleta del diálogo tenga fondo oscuro (Base) y texto claro (Text)
        pal = dlg.palette()
        base_color = pal.color(QPalette.Base)
        text_color = pal.color(QPalette.Text)

        # Base debe ser un color oscuro (luminancia baja)
        self.assertTrue(base_color.lightness() < 50, f"Base color lightness {base_color.lightness()} no es oscuro")
        # Text debe ser un color claro (luminancia alta)
        self.assertTrue(text_color.lightness() > 180, f"Text color lightness {text_color.lightness()} no es claro")
        dlg.close()

    def test_12_context_menu_generation_and_cli(self):
        import context_menu_manager
        from ui.main_window import MainWindow

        # 1. Verificar generación dinámica para KDE Dolphin con atajos rápidos
        kde_content = context_menu_manager.generate_kde_dolphin_desktop("/app/main.py", "python3")
        self.assertIn("X-KDE-Submenu=MyFFmpeg GUI", kde_content)
        self.assertIn('--quick-action "quick_mp3"', kde_content)
        self.assertIn("--tab audio", kde_content)

        # 2. Verificar generación de FreeDesktop .desktop
        fdo_content = context_menu_manager.generate_freedesktop_app("/app/main.py", "python3")
        self.assertIn("Name=MyFFmpeg GUI", fdo_content)
        self.assertIn('Exec=python3 "/app/main.py"', fdo_content)

        # 3. Verificar generación de archivo .reg para Windows HKCU
        reg_content = context_menu_manager.generate_windows_reg_content("C:\\App\\main.py", "pythonw.exe")
        self.assertIn(r"HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\video\shell\MyFFmpegGUI", reg_content)
        self.assertIn(r"HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\audio\shell\MyFFmpegGUI", reg_content)
        self.assertIn('--quick-action \\"quick_mp3\\"', reg_content)
        self.assertIn("--tab audio", reg_content)

        # 4. Probar exportación de archivos .reg a carpeta temporal
        inst_f, uninst_f = context_menu_manager.export_windows_reg_files(self.tmp_path)
        self.assertTrue(os.path.exists(inst_f))
        self.assertTrue(os.path.exists(uninst_f))
        self.assertGreater(os.path.getsize(inst_f), 100)

        # 5. Probar MainWindow cargando archivo y pestaña directamente (como invocado desde clic derecho)
        win = MainWindow(initial_tab="video", initial_file=self.test_video)
        self.assertEqual(win.tabs.currentIndex(), 1)  # Tab Convertir Video
        self.assertEqual(win.tab_convert.input_selector.get_path(), self.test_video)
        self.assertGreater(win.tab_convert.media_duration, 0)
        win.close()

        # Probar MainWindow con initial_tab="audio" y archivo
        win_audio = MainWindow(initial_tab="audio", initial_file=self.test_video)
        self.assertEqual(win_audio.tabs.currentIndex(), 0)  # Tab Audio
        self.assertEqual(win_audio.tab_audio.input_selector.get_path(), self.test_video)
        win_audio.close()

    def test_13_quick_action_execution_and_custom_shortcuts(self):
        import context_menu_manager
        import config_manager
        from ui.main_window import MainWindow

        # 1. Probar ejecución de atajo rápido a MP3 sin abrir GUI
        ok = context_menu_manager.execute_quick_action("quick_mp3", self.test_video)
        self.assertTrue(ok)
        expected_mp3 = os.path.splitext(self.test_video)[0] + ".mp3"
        self.assertTrue(os.path.exists(expected_mp3))
        self.assertGreater(os.path.getsize(expected_mp3), 1000)

        # 2. Probar creación de atajo personalizado
        custom = config_manager.add_custom_quick_action(
            "⚡ Test Custom Action",
            'ffmpeg -y -i "{input}" "{output_no_ext}_test.wav"'
        )
        self.assertTrue(custom["is_custom"])
        self.assertIn("custom_", custom["id"])

        # Verificar que la acción se refleja en la generación
        kde_content = context_menu_manager.generate_kde_dolphin_desktop("/app/main.py", "python3")
        self.assertIn(custom["id"], kde_content)
        self.assertIn("Test Custom Action", kde_content)

        # 3. Probar reordenación de acciones
        actions_before = config_manager.get_context_actions()
        first_id = actions_before[0]["id"]
        second_id = actions_before[1]["id"]
        # Mover el segundo elemento hacia arriba
        moved_up = config_manager.move_context_action(second_id, -1)
        self.assertTrue(moved_up)
        actions_after = config_manager.get_context_actions()
        self.assertEqual(actions_after[0]["id"], second_id)
        self.assertEqual(actions_after[1]["id"], first_id)
        # Regresar a su posición original
        config_manager.move_context_action(second_id, 1)

        # 4. Probar eliminación del atajo personalizado
        deleted = config_manager.delete_context_action(custom["id"])
        self.assertTrue(deleted)

        # 5. Probar inserción de variables en CustomActionDialog haciendo clic
        from ui.tab_settings import CustomActionDialog
        dlg = CustomActionDialog()
        dlg.edit_cmd.clear()
        dlg._insert_variable('ffmpeg -i "')
        dlg._insert_variable('{input}')
        dlg._insert_variable('" "')
        dlg._insert_variable('{output_no_ext}.mp3')
        dlg._insert_variable('"')
        self.assertEqual(dlg.edit_cmd.text(), 'ffmpeg -i "{input}" "{output_no_ext}.mp3"')
        dlg.close()

        # 6. Probar que la tabla en TabSettings se inicializa con filas y controles
        win = MainWindow(initial_tab="settings")
        settings_tab = win.tab_settings
        self.assertGreater(settings_tab.table_actions.rowCount(), 0)
        win.close()

        # 7. Probar CLI flags --install-context y --uninstall-context
        res_inst = subprocess.run([sys.executable, "main.py", "--install-context"], capture_output=True, text=True)
        self.assertEqual(res_inst.returncode, 0)
        res_uninst = subprocess.run([sys.executable, "main.py", "--uninstall-context"], capture_output=True, text=True)
        self.assertEqual(res_uninst.returncode, 0)
        # Reinstalar para mantener la integración activa en el entorno del usuario
        subprocess.run([sys.executable, "main.py", "--install-context"], capture_output=True)

    def test_14_tab_concat_interactions(self):
        """Verifica que TabConcat agregue archivos, ordene naturalmente y actualice vista previa sin cerrarse."""
        win = MainWindow(initial_tab="concat")
        concat_tab = win.tab_concat

        # Crear archivos de prueba desordenados
        f1 = os.path.join(self.tmp_path, "clip_1.mp4")
        f2 = os.path.join(self.tmp_path, "clip_2.mp4")
        f10 = os.path.join(self.tmp_path, "clip_10.mp4")
        for f in [f1, f2, f10]:
            with open(f, "wb") as fp:
                fp.write(b"dummy")

        # 1. Insertar archivos en orden inverso
        concat_tab._insert_paths([f10, f2, f1])
        self.assertEqual(concat_tab.list_widget.count(), 3)
        # Verificar ordenamiento natural (1 -> 2 -> 10, no 1 -> 10 -> 2)
        self.assertEqual(concat_tab.list_widget.item(0).text(), f1)
        self.assertEqual(concat_tab.list_widget.item(1).text(), f2)
        self.assertEqual(concat_tab.list_widget.item(2).text(), f10)

        # 2. Verificar que la vista previa del comando se generó correctamente
        preview_text = concat_tab.cmd_preview.text_cmd.toPlainText()
        self.assertIn("ffmpeg", preview_text)
        self.assertIn("-f concat", preview_text)
        self.assertIn("-c copy", preview_text)

        # 3. Cambiar a modo recodificación y verificar actualización
        concat_tab.combo_mode.setCurrentIndex(1)
        preview_reencode = concat_tab.cmd_preview.text_cmd.toPlainText()
        self.assertIn("libx264", preview_reencode)

        # 4. Probar mover elementos arriba y abajo
        concat_tab.list_widget.setCurrentRow(1)
        concat_tab._move_up()
        self.assertEqual(concat_tab.list_widget.item(0).text(), f2)

        # 5. Probar que _update_output_suggestion limpia sufijos de fragmento (_part_XXX)
        concat_tab._clear_list()
        p1 = os.path.join(self.tmp_path, "vacaciones_part_001.mp4")
        p2 = os.path.join(self.tmp_path, "vacaciones_part_002.mp4")
        for p in [p1, p2]:
            with open(p, "wb") as fp:
                fp.write(b"dummy")
        concat_tab._insert_paths([p1, p2])
        out_suggested = concat_tab.output_selector.get_path()
        self.assertIn("vacaciones_unido.mp4", out_suggested)
        self.assertNotIn("part_001", out_suggested)

        # 6. Probar limpieza
        concat_tab._clear_list()
        self.assertEqual(concat_tab.list_widget.count(), 0)
        self.assertIn("Seleccione los archivos", concat_tab.cmd_preview.text_cmd.toPlainText())

        win.close()

    def test_15_post_actions_and_resizable_splitter(self):
        """Verifica el divisor redimensionable en TabConcat, OutputActionsWidget y etiquetas de carpeta base clicables."""
        from PyQt5.QtWidgets import QSplitter, QLabel
        from ui.widgets import OutputActionsWidget

        win = MainWindow(initial_tab="concat")
        concat_tab = win.tab_concat

        # 1. Comprobar que TabConcat utiliza un QSplitter para redimensionar la lista
        splitters = concat_tab.findChildren(QSplitter)
        self.assertGreater(len(splitters), 0, "TabConcat debe contener un QSplitter")
        self.assertTrue(hasattr(concat_tab, "content_splitter"), "TabConcat debe tener content_splitter para redimensionar la lista")
        self.assertEqual(concat_tab.content_splitter.count(), 2)
        self.assertGreaterEqual(concat_tab.splitter.count(), 2, "El splitter principal debe contener las secciones de contenido y panel de salida")
        self.assertGreater(concat_tab.list_widget.minimumHeight(), 0)

        # Verificar que los botones estén en una sola fila si la terminal no está visible
        from PyQt5.QtWidgets import QHBoxLayout, QGridLayout
        win.sync_console_panels(visible=False)
        self.assertIsInstance(concat_tab.tools_container.layout(), QHBoxLayout, "Los botones deben estar en 1 fila si la terminal está oculta")

        # Verificar que los botones pasen a 2 filas compactas si la terminal está visible en lateral
        win.sync_console_panels(pos="side", visible=True)
        self.assertIsInstance(concat_tab.tools_container.layout(), QGridLayout, "Los botones deben ser compactos en modo lateral")

        # Verificar que vuelvan a 1 fila en modo inferior
        win.sync_console_panels(pos="bottom", visible=True)
        self.assertIsInstance(concat_tab.tools_container.layout(), QHBoxLayout, "Los botones deben estar en 1 fila en modo inferior")

        # 2. Comprobar presencia de OutputActionsWidget en las pestañas principales
        for tab_name, tab_obj in [
            ("concat", win.tab_concat),
            ("create", win.tab_create),
            ("convert", win.tab_convert),
            ("segment", win.tab_segment),
            ("audio", win.tab_audio),
            ("extract", win.tab_extract),
        ]:
            self.assertTrue(hasattr(tab_obj, "output_actions"), f"{tab_name} debe tener output_actions")
            self.assertIsInstance(tab_obj.output_actions, OutputActionsWidget)
            self.assertFalse(tab_obj.output_actions.isVisible(), f"{tab_name}.output_actions debe iniciar oculto")

            # Comprobar que la etiqueta de carpeta base contiene enlace HTML clicable
            if hasattr(tab_obj, "lbl_base_info"):
                self.assertIn("Carpeta Base actual:", tab_obj.lbl_base_info.text())
                self.assertIn("<a href=", tab_obj.lbl_base_info.text())

        # 3. Comprobar funcionamiento de OutputActionsWidget
        actions_w = OutputActionsWidget(file_label="Abrir Video")
        dummy_file = os.path.join(self.tmp_path, "test_out.mp4")
        with open(dummy_file, "w") as f:
            f.write("content")

        actions_w.show_output(dummy_file)
        self.assertTrue(actions_w.isVisible())
        self.assertTrue(actions_w.btn_open_file.isVisible())
        self.assertTrue(actions_w.btn_open_folder.isVisible())
        self.assertEqual(actions_w.btn_open_file.text(), "Abrir Video")
        self.assertFalse(actions_w.btn_open_file.icon().isNull())
        self.assertFalse(actions_w.btn_open_folder.icon().isNull())

        actions_w.hide_output()
        self.assertFalse(actions_w.isVisible())

        # 4. Comprobar helpers de apertura segura
        res_dir = config_manager.open_path_in_os(self.tmp_path, is_directory=True)
        # En entorno sin display real (offscreen), puede devolver False o lanzar xdg-open/QDesktopServices sin error
        self.assertIsInstance(res_dir, bool)

        win.close()

    def test_16_segment_default_and_concat_audio(self):
        """Verifica que 'Corte Exacto' sea la opción predeterminada en Segmentar Video
        y que Unir Segmentos soporte incorporar pista de audio (replace, mix, add_track)."""
        win = MainWindow(initial_tab="segment")

        # 1. Comprobar que en TabSegment la opción por defecto sea 'exact' (Corte Exacto)
        seg_tab = win.tab_segment
        self.assertEqual(seg_tab.combo_mode.currentIndex(), 0)
        self.assertEqual(seg_tab.combo_mode.currentData(), "exact")
        self.assertIn("Corte Exacto", seg_tab.combo_mode.currentText())

        # Comprobar que build_segment_command utiliza 'exact' por defecto
        cmd_default_seg = ffmpeg_core.build_segment_command(
            self.ffmpeg_path, self.test_video, "part_%03d.mp4"
        )
        self.assertIn("libx264", cmd_default_seg)
        self.assertIn("17", cmd_default_seg)

        # 2. Comprobar controles de audio en TabConcat
        concat_tab = win.tab_concat
        self.assertTrue(hasattr(concat_tab, "audio_selector"))
        self.assertTrue(hasattr(concat_tab, "btn_clear_audio"))
        self.assertTrue(hasattr(concat_tab, "combo_audio_mode"))
        self.assertTrue(hasattr(concat_tab, "chk_shortest"))

        # Iniciar sin audio: widget de opciones oculto y botón limpiar deshabilitado
        self.assertFalse(concat_tab.btn_clear_audio.isEnabled())
        self.assertFalse(concat_tab.widget_audio_opts.isVisible())

        # 3. Comprobar generación de comandos de concat con audio
        dummy_list = os.path.join(self.tmp_path, "dummy_list.txt")
        dummy_audio = os.path.join(self.tmp_path, "bg_music.mp3")
        dummy_out = os.path.join(self.tmp_path, "output_with_audio.mp4")

        # Modo replace (por defecto con audio)
        cmd_replace = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            dummy_list,
            dummy_out,
            mode="copy",
            audio_file=dummy_audio,
            audio_mode="replace",
            shortest=True
        )
        self.assertIn("-i", cmd_replace)
        self.assertIn(dummy_audio, cmd_replace)
        self.assertIn("-map", cmd_replace)
        self.assertIn("0:v:0", cmd_replace)
        self.assertIn("1:a:0", cmd_replace)
        self.assertIn("-shortest", cmd_replace)

        # Modo mix (mezclar con amix)
        cmd_mix = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            dummy_list,
            dummy_out,
            mode="copy",
            audio_file=dummy_audio,
            audio_mode="mix",
            shortest=True
        )
        self.assertIn("-filter_complex", cmd_mix)
        self.assertTrue(any("amix" in arg for arg in cmd_mix))

        # Modo add_track (pista secundaria)
        cmd_track = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            dummy_list,
            dummy_out,
            mode="copy",
            audio_file=dummy_audio,
            audio_mode="add_track",
            shortest=True
        )
        self.assertIn("0:a?", cmd_track)
        self.assertIn("1:a:0", cmd_track)

        # 4. Probar ejecución real de concat con pista de audio incorporada
        # Generar pista de audio sintética de 4 segundos
        music_file = os.path.join(self.tmp_path, "sample_audio.mp3")
        subprocess.run([
            self.ffmpeg_path, "-y",
            "-f", "lavfi", "-i", "sine=frequency=330:duration=4",
            "-c:a", "libmp3lame", music_file
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Segmentar test_video en 2 partes
        seg_pat = os.path.join(self.tmp_path, "seg_audio_%03d.mp4")
        subprocess.run(ffmpeg_core.build_segment_command(
            self.ffmpeg_path, self.test_video, seg_pat, segment_duration_sec=2, mode="exact"
        ), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        segments = sorted([
            os.path.join(self.tmp_path, f)
            for f in os.listdir(self.tmp_path)
            if f.startswith("seg_audio_") and f.endswith(".mp4")
        ])
        real_list = os.path.join(self.tmp_path, "real_concat_list.txt")
        ffmpeg_core.create_concat_list_file(segments, real_list)

        out_final = os.path.join(self.tmp_path, "final_unified_with_audio.mp4")
        cmd_exec = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            real_list,
            out_final,
            mode="copy",
            audio_file=music_file,
            audio_mode="replace",
            shortest=True
        )
        res_exec = subprocess.run(cmd_exec, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_exec.returncode, 0, f"Error en concat con audio: {res_exec.stderr.decode('utf-8')}")
        self.assertTrue(os.path.isfile(out_final))

        # Verificar con ffprobe que el video resultante contiene video y audio
        info = ffmpeg_core.get_media_info(out_final, self.ffprobe_path)
        self.assertEqual(info["video_codec"], "h264")
        self.assertEqual(info["audio_codec"], "aac")
        self.assertGreater(info["duration"], 3.0)

        # 5. Probar interacción UI en TabConcat
        concat_tab._insert_paths(segments)
        concat_tab.audio_selector.set_path(music_file)
        self.assertTrue(concat_tab.btn_clear_audio.isEnabled())
        self.assertFalse(concat_tab.widget_audio_opts.isHidden())
        self.assertIn(music_file, concat_tab.cmd_preview.text_cmd.toPlainText())

        # Limpiar audio con el botón
        concat_tab.btn_clear_audio.click()
        self.assertEqual(concat_tab.audio_selector.get_path(), "")
        self.assertFalse(concat_tab.btn_clear_audio.isEnabled())
        self.assertTrue(concat_tab.widget_audio_opts.isHidden())
        self.assertNotIn(music_file, concat_tab.cmd_preview.text_cmd.toPlainText())

        win.close()

    def test_18_video_comparison_and_metrics(self):
        """Verifica la lógica de comparación de videos, filtros FFmpeg, cálculo SSIM/PSNR y UI de TabCompare."""
        # 1. Crear un segundo video (comprimido/reducido) a partir de self.test_video
        compressed_video = os.path.join(self.tmp_path, "sample_compressed.mp4")
        cmd_comp = [
            self.ffmpeg_path, "-y",
            "-i", self.test_video,
            "-vf", "scale=160:120",
            "-c:v", "libx264", "-crf", "32",
            "-c:a", "aac", "-b:a", "64k",
            compressed_video
        ]
        res_comp = subprocess.run(cmd_comp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_comp.returncode, 0, "No se pudo generar el video comprimido de prueba")

        # 2. Probar construcción de comandos de comparación
        out_split = os.path.join(self.tmp_path, "compare_split.mp4")
        cmd_split = ffmpeg_core.build_compare_video_command(
            self.ffmpeg_path, self.test_video, compressed_video, out_split, mode="split_screen"
        )
        self.assertIn("drawbox", "".join(cmd_split))
        self.assertIn("crop", "".join(cmd_split))

        out_sbs = os.path.join(self.tmp_path, "compare_sbs.mp4")
        cmd_sbs = ffmpeg_core.build_compare_video_command(
            self.ffmpeg_path, self.test_video, compressed_video, out_sbs, mode="side_by_side"
        )
        self.assertIn("hstack", "".join(cmd_sbs))

        out_diff = os.path.join(self.tmp_path, "compare_diff.mp4")
        cmd_diff = ffmpeg_core.build_compare_video_command(
            self.ffmpeg_path, self.test_video, compressed_video, out_diff, mode="diff"
        )
        self.assertIn("blend=all_mode=difference", "".join(cmd_diff))

        # 3. Probar ejecución real de generación de video comparativo (split_screen)
        res_exec = subprocess.run(cmd_split, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_exec.returncode, 0, f"Error generando video comparativo: {res_exec.stderr.decode('utf-8')}")
        self.assertTrue(os.path.isfile(out_split))

        # 4. Probar comando y cálculo de métricas SSIM y PSNR reales
        cmd_metrics = ffmpeg_core.build_compare_metrics_command(
            self.ffmpeg_path, self.test_video, compressed_video
        )
        res_metrics = subprocess.run(cmd_metrics, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_metrics.returncode, 0)
        logs = res_metrics.stderr.decode("utf-8", errors="replace").splitlines()

        parsed = ffmpeg_core.parse_comparison_metrics(logs)
        self.assertIsNotNone(parsed["ssim"])
        self.assertIsNotNone(parsed["psnr"])
        self.assertGreaterEqual(parsed["ssim"], 0.0)
        self.assertLessEqual(parsed["ssim"], 1.0)
        self.assertGreater(parsed["psnr"], 10.0)
        self.assertIn("rating", parsed)

        # 5. Probar parsing con mock text
        mock_logs = [
            "Parsed_ssim_1: SSIM Y:0.952100 (13.197022) U:0.970123 (15.247190) V:0.965432 (14.613892) All:0.958200 (13.789123)",
            "Parsed_psnr_0: PSNR y:38.25 u:41.50 v:40.80 average:39.10 min:32.40 max:inf"
        ]
        parsed_mock = ffmpeg_core.parse_comparison_metrics(mock_logs)
        self.assertAlmostEqual(parsed_mock["ssim"], 0.9582, places=4)
        self.assertAlmostEqual(parsed_mock["psnr"], 39.10, places=2)
        self.assertIn("Muy Buena", parsed_mock["rating"])

        # 6. Probar integración en MainWindow y TabCompare
        win = MainWindow(initial_tab="compare")
        self.assertEqual(win.tabs.count(), 10)
        compare_tab = win.tab_compare

        # Cargar videos en la interfaz
        compare_tab.input_a.set_path(self.test_video)
        compare_tab.input_b.set_path(compressed_video)

        # Verificar que se cargaron los metadatos y se actualizó la reducción de tamaño
        self.assertIn("320x240", compare_tab.lbl_meta_a.text())
        self.assertIn("160x120", compare_tab.lbl_meta_b.text())
        self.assertTrue(compare_tab.btn_play_both.isEnabled())
        self.assertIn("Ahorro de tamaño", compare_tab.lbl_diff_summary.text())

        # 7. Probar Arrastrar y Soltar (Drag & Drop) con URIs tipo file:// de Linux (Dolphin / Nautilus)
        from PyQt5.QtCore import Qt, QMimeData, QUrl, QPoint
        from PyQt5.QtGui import QDropEvent

        uri_a = "file://" + self.test_video + "\r\n"
        compare_tab.input_a.edit.setText(uri_a)
        # Debe haberse limpiado automáticamente
        self.assertEqual(compare_tab.input_a.get_path(), self.test_video)
        self.assertIsNotNone(compare_tab.info_a)

        # Probar dropEvent real en DropLineEdit
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(compressed_video)])
        drop_evt = QDropEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        compare_tab.input_b.edit.dropEvent(drop_evt)
        self.assertEqual(compare_tab.input_b.get_path(), compressed_video)
        self.assertIsNotNone(compare_tab.info_b)

        # 8. Probar opciones de reproducción en paralelo (Sincronizada, Dos Ventanas, OS)
        from ui.tab_compare import ParallelPlayDialog
        dlg = ParallelPlayDialog(compare_tab, has_ffplay=True)
        self.assertIsNotNone(dlg.btn_opt_sync)
        self.assertIsNotNone(dlg.btn_opt_dual)
        dlg.close()

        # Probar comandos de ffplay en core
        ffplay_p = ffmpeg_core.get_ffplay_path(self.ffmpeg_path)
        self.assertIsNotNone(ffplay_p)

        cmd_sync_ff = ffmpeg_core.build_compare_live_stream_command(
            self.ffmpeg_path, self.test_video, compressed_video, mode="split_screen"
        )
        self.assertIn("nut", cmd_sync_ff)

        cmd_a_dual, cmd_b_dual = ffmpeg_core.build_ffplay_dual_window_commands(
            ffplay_p, self.test_video, compressed_video
        )
        self.assertIn("-window_title", cmd_a_dual)
        self.assertIn("-window_title", cmd_b_dual)

        # Probar ejecución de modo "os" con mock
        opened_paths = []
        orig_open = config_manager.open_path_in_os
        config_manager.open_path_in_os = lambda p, is_directory=False: opened_paths.append(p)
        config_manager.set_parallel_playback_pref("os")
        try:
            compare_tab._play_both()
            self.assertIn(self.test_video, opened_paths)
        finally:
            config_manager.open_path_in_os = orig_open
            config_manager.set_parallel_playback_pref("integrated")

        # 9. Probar VideoComparePlayerDialog (Lienzo interactivo, cortina y controles)
        from ui.compare_player import VideoComparePlayerDialog
        player = VideoComparePlayerDialog(
            None, video_a=self.test_video, video_b=compressed_video, ffmpeg_path=self.ffmpeg_path
        )
        self.assertIsNotNone(player.canvas)
        self.assertEqual(player.canvas.mode, "split")
        self.assertEqual(player.canvas.split_ratio, 0.5)

        # Mover cortina divisoria
        player.canvas.set_split_ratio(0.35)
        self.assertAlmostEqual(player.canvas.split_ratio, 0.35, places=2)

        # Alternar a modo Lado a Lado
        player._set_mode("side_by_side")
        self.assertEqual(player.canvas.mode, "side_by_side")
        self.assertTrue(player.btn_mode_sbs.isChecked())
        self.assertFalse(player.btn_mode_split.isChecked())

        # Volver a modo dividido
        player._set_mode("split")
        self.assertEqual(player.canvas.mode, "split")
        self.assertTrue(player.btn_mode_split.isChecked())

        # Probar controles de velocidad y audio
        player.combo_speed.setCurrentIndex(0)  # 0.5x
        self.assertEqual(player.worker._speed, 0.5)

        player.combo_audio.setCurrentIndex(1)  # Audio Video A
        self.assertEqual(player.worker._audio_source, "a")
        self.assertTrue(player.slider_volume.isEnabled())
        self.assertTrue(player.btn_volume.isEnabled())

        # Probar control de volumen y silenciado
        player.slider_volume.setValue(75)
        player._apply_volume_to_worker()
        self.assertEqual(player.worker._volume, 75)
        self.assertEqual(player.lbl_volume.text(), "75%")

        player._toggle_mute()
        self.assertEqual(player.slider_volume.value(), 0)

        player._toggle_mute()
        self.assertEqual(player.slider_volume.value(), 75)

        # Silenciado desactiva controles de volumen
        player.combo_audio.setCurrentIndex(0)
        self.assertFalse(player.slider_volume.isEnabled())

        # Probar paso de fotograma / salto
        player.worker.step(1.0)
        self.assertEqual(player.worker._seek_requested, 1.0)

        # Probar repetición continua (bucle - activado por defecto)
        self.assertTrue(player.btn_loop.isChecked())
        self.assertTrue(player.worker._loop)
        player.btn_loop.setChecked(False)
        player._toggle_loop()
        self.assertFalse(player.worker._loop)
        player._toggle_loop_shortcut()
        self.assertTrue(player.worker._loop)
        self.assertTrue(player.btn_loop.isChecked())

        # Probar clic simple en el lienzo para alternar reproducir / pausa
        self.assertFalse(player.worker._is_playing)
        player.canvas.play_pause_requested.emit()
        self.assertTrue(player.worker._is_playing)
        player.canvas.play_pause_requested.emit()
        self.assertFalse(player.worker._is_playing)

        # Probar que al llegar al final, reproducir reinicia desde el inicio (0.0s)
        player.worker._current_time = player.duration
        player._on_toggle_play()
        self.assertEqual(player.worker._seek_requested, 0.0)

        # Verificar etiquetas de resolución y fps en cada lado
        self.assertIn("Original (A)", player.canvas.label_a)
        self.assertIn("Procesado (B)", player.canvas.label_b)
        self.assertIn("fps", player.canvas.label_a)
        self.assertIn("fps", player.canvas.label_b)

        # Verificar flags de ventana (Minimizar, Maximizar/Restaurar y Cerrar)
        from PyQt5.QtCore import Qt
        flags = int(player.windowFlags())
        self.assertTrue(flags & int(Qt.WindowMinMaxButtonsHint))

        # Cerrar el reproductor
        player.close()
        self.assertFalse(player.worker.isRunning())

        win.close()

    def test_all_tabs_on_finished_success_notifications(self):
        """Verifica que todos los tabs puedan mostrar su notificación de éxito sin errores de NameError o Qt."""
        from unittest.mock import patch
        from ui.tab_audio import TabAudio
        from ui.tab_convert_video import TabConvertVideo
        from ui.tab_extract_frames import TabExtractFrames
        from ui.tab_create_video import TabCreateVideo
        from ui.tab_segment import TabSegment
        from ui.tab_concat import TabConcat

        from ui.tab_add_audio import TabAddAudio

        get_paths = lambda: (self.ffmpeg_path, self.ffprobe_path)

        tabs = [
            TabAudio(get_paths),
            TabAddAudio(get_paths),
            TabConvertVideo(get_paths),
            TabExtractFrames(get_paths),
            TabCreateVideo(get_paths),
            TabSegment(get_paths),
            TabConcat(get_paths),
        ]

        from PyQt5.QtWidgets import QMessageBox

        with patch.object(QMessageBox, "exec_", return_value=0), \
             patch.object(QMessageBox, "exec", return_value=0), \
             patch.object(QMessageBox, "warning", return_value=0), \
             patch.object(QMessageBox, "information", return_value=0):
            for tab in tabs:
                # Debe ejecutarse limpiamente sin lanzar NameError (ej: Qt.RichText)
                tab._on_finished(True, "Proceso completado con éxito", self.test_video)
                tab._on_finished(False, "Error simulado", "")
                tab.close()

    def test_add_audio_to_video_core_and_ui(self):
        """Verifica la generación de comandos y la funcionalidad del tab 'Poner Audio a Video'."""
        audio_file = os.path.join(self.tmp_path, "sample_audio.mp3")
        cmd_aud = [
            self.ffmpeg_path, "-y",
            "-f", "lavfi", "-i", "sine=frequency=520:duration=4",
            "-c:a", "libmp3lame", "-b:a", "192k",
            audio_file
        ]
        res = subprocess.run(cmd_aud, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 0, "No se pudo generar el audio sintético de prueba")

        out_replace = os.path.join(self.tmp_path, "out_replace.mp4")
        out_mix = os.path.join(self.tmp_path, "out_mix.mp4")
        out_add_track = os.path.join(self.tmp_path, "out_add_track.mp4")

        # 1. Probar comando replace
        cmd1 = ffmpeg_core.build_add_audio_to_video_command(
            self.ffmpeg_path, self.test_video, audio_file, out_replace,
            audio_mode="replace", audio_codec="aac", shortest=True
        )
        self.assertIn("-c:v", cmd1)
        self.assertIn("copy", cmd1)
        self.assertIn("-shortest", cmd1)
        res1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res1.returncode, 0, f"Error en replace audio: {res1.stderr.decode()}")
        self.assertTrue(os.path.isfile(out_replace))

        # 2. Probar comando mix
        cmd2 = ffmpeg_core.build_add_audio_to_video_command(
            self.ffmpeg_path, self.test_video, audio_file, out_mix,
            audio_mode="mix", audio_codec="aac", shortest=True, has_original_audio=True
        )
        self.assertIn("amix=inputs=2", " ".join(cmd2))
        res2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res2.returncode, 0, f"Error en mix audio: {res2.stderr.decode()}")
        self.assertTrue(os.path.isfile(out_mix))

        # 3. Probar comando add_track
        cmd3 = ffmpeg_core.build_add_audio_to_video_command(
            self.ffmpeg_path, self.test_video, audio_file, out_add_track,
            audio_mode="add_track", audio_codec="mp3", shortest=True
        )
        self.assertIn("0:a?", " ".join(cmd3))
        res3 = subprocess.run(cmd3, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res3.returncode, 0, f"Error en add_track audio: {res3.stderr.decode()}")
        self.assertTrue(os.path.isfile(out_add_track))

        # 3b. Probar comando con retraso en el video (adelay) y punto de inicio del audio (-ss)
        out_timed = os.path.join(self.tmp_path, "out_timed.mp4")
        cmd_timed = ffmpeg_core.build_add_audio_to_video_command(
            self.ffmpeg_path, self.test_video, audio_file, out_timed,
            audio_mode="mix", audio_codec="aac", shortest=True,
            audio_delay_sec=1.5, audio_start_offset_sec=0.5
        )
        cmd_timed_str = " ".join(cmd_timed)
        self.assertIn("adelay=1500:all=1", cmd_timed_str)
        self.assertIn("-ss", cmd_timed)
        self.assertIn("0.500", cmd_timed)
        res_timed = subprocess.run(cmd_timed, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_timed.returncode, 0, f"Error en timed audio: {res_timed.stderr.decode()}")
        self.assertTrue(os.path.isfile(out_timed))

        # 4. Probar TabAddAudio en MainWindow
        win = MainWindow()
        self.assertTrue(hasattr(win, "tab_add_audio"))
        self.assertIn("add_audio", win.tab_map)

        tab = win.tab_add_audio
        tab.video_selector.set_path(self.test_video)
        self.assertTrue(tab.has_original_audio)
        self.assertGreater(tab.video_duration, 0.0)

        tab.audio_selector.set_path(audio_file)
        self.assertTrue(tab.btn_clear_audio.isEnabled())

        # Probar controles de sincronización y desfase de tiempo
        self.assertTrue(hasattr(tab, "spin_delay"))
        self.assertTrue(hasattr(tab, "spin_offset"))
        tab.spin_delay.setValue(1.25)
        tab.spin_offset.setValue(0.75)
        self.assertEqual(tab.lbl_delay_fmt.text(), "00:00:01.25")
        self.assertEqual(tab.lbl_offset_fmt.text(), "00:00:00.75")
        preview_timed = tab.cmd_preview.get_command()
        self.assertIn("adelay=1250:all=1", preview_timed)
        self.assertIn("-ss", preview_timed)

        # Probar cambio de modo
        tab.combo_audio_mode.setCurrentIndex(1)  # mix
        self.assertFalse(tab.widget_mix_volumes.isHidden())
        tab.slider_vol_orig.setValue(80)
        tab.slider_vol_added.setValue(35)
        preview_text = tab.cmd_preview.get_command()
        self.assertIn("amix", preview_text)
        self.assertIn("volume=0.8", preview_text)
        self.assertIn("volume=0.35", preview_text)

        tab.combo_audio_mode.setCurrentIndex(2)  # add_track
        self.assertTrue(tab.widget_mix_volumes.isHidden())
        preview_text = tab.cmd_preview.get_command()
        self.assertIn("0:a?", preview_text)

        # Probar limpiar audio
        tab._clear_audio()
        self.assertEqual(tab.audio_selector.get_path(), "")
        self.assertFalse(tab.btn_clear_audio.isEnabled())

        win.close()

    def test_console_output_panel_collapsible_and_position(self):
        """Verifica que el panel de comando y terminal sea ocultable, alternable entre abajo y lateral, y persistente."""
        from PyQt5.QtCore import Qt
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox

        win = MainWindow()

        # Tabs que contienen el panel
        tabs_with_console = [
            win.tab_convert,
            win.tab_audio,
            win.tab_add_audio,
            win.tab_extract,
            win.tab_create,
            win.tab_segment,
            win.tab_concat
        ]

        for tab in tabs_with_console:
            self.assertTrue(hasattr(tab, "console_panel"))
            self.assertTrue(hasattr(tab, "btn_show_console"))
            self.assertTrue(hasattr(tab, "cmd_preview"))
            self.assertTrue(hasattr(tab, "log_console"))
            self.assertTrue(hasattr(tab, "splitter_console"))

        # 1. Probar sincronización a panel lateral ("side")
        win.sync_console_panels("side", True)
        self.assertEqual(config_manager.get_console_panel_position(), "side")
        self.assertTrue(config_manager.get_console_panel_visible())
        for tab in tabs_with_console:
            self.assertEqual(tab.splitter_console.orientation(), Qt.Horizontal)
            self.assertFalse(tab.console_panel.isHidden())
            self.assertTrue(tab.btn_show_console.isHidden())
            self.assertEqual(tab.console_panel.position, "side")
            self.assertTrue(tab.log_console.btn_toggle_height.isHidden(), "El botón expandir/reducir debe estar oculto en modo lateral")

        # 2. Probar ocultar el panel desde la pestaña
        tab0 = tabs_with_console[0]
        tab0.console_panel.btn_hide.click()
        # Verificar que se ocultó y se muestra el botón para restaurar
        self.assertTrue(tab0.console_panel.isHidden())
        self.assertFalse(tab0.btn_show_console.isHidden())
        self.assertFalse(config_manager.get_console_panel_visible())

        # 3. Probar restaurar con el botón
        tab0.btn_show_console.click()
        self.assertFalse(tab0.console_panel.isHidden())
        self.assertTrue(tab0.btn_show_console.isHidden())
        self.assertTrue(config_manager.get_console_panel_visible())

        # 4. Probar alternar posición con el botón del panel (de lateral a abajo)
        tab0.console_panel.btn_toggle_pos.click()
        self.assertEqual(config_manager.get_console_panel_position(), "bottom")
        for tab in tabs_with_console:
            self.assertEqual(tab.splitter_console.orientation(), Qt.Vertical)
            self.assertEqual(tab.console_panel.position, "bottom")
            self.assertFalse(tab.log_console.btn_toggle_height.isHidden(), "El botón expandir/reducir debe estar visible en modo inferior")

        # 5. Probar configuración desde TabSettings
        settings = win.tab_settings
        settings.radio_panel_side.setChecked(True)
        settings.chk_panel_visible.setChecked(False)
        with patch.object(QMessageBox, "information", return_value=0):
            settings._save_settings()

        self.assertEqual(config_manager.get_console_panel_position(), "side")
        self.assertFalse(config_manager.get_console_panel_visible())

        # Restaurar a bottom y visible para dejar limpio
        win.sync_console_panels("bottom", True)
        win.close()

    def test_22_concat_anti_stutter(self):
        """Verifica la lógica de eliminación de micro-stutter (automático mpdecimate y manual gte(n,N)) y sus controles de UI."""
        dummy_list = os.path.join(self.tmp_path, "dummy_list_stutter.txt")
        dummy_out = os.path.join(self.tmp_path, "output_anti_stutter.mp4")
        seg1 = os.path.join(self.tmp_path, "seg1.mp4")
        seg2 = os.path.join(self.tmp_path, "seg2.mp4")
        seg3 = os.path.join(self.tmp_path, "seg3.mp4")
        files = [seg1, seg2, seg3]

        # 1. Modo automático inteligente (mpdecimate)
        cmd_auto = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            list_file_path=dummy_list,
            output_file=dummy_out,
            mode="copy",
            anti_stutter=True,
            stutter_mode="auto"
        )
        self.assertIn("-vf", cmd_auto)
        self.assertTrue(any("mpdecimate" in arg for arg in cmd_auto))
        self.assertIn("-af", cmd_auto)
        self.assertTrue(any("aresample" in arg for arg in cmd_auto))
        self.assertIn("libx264", cmd_auto)

        # 2. Modo manual (omitir N fotogramas con filter_complex)
        cmd_manual = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            list_file_path=dummy_list,
            output_file=dummy_out,
            mode="copy",
            anti_stutter=True,
            stutter_mode="manual",
            drop_start_frames=2,
            file_paths=files
        )
        self.assertIn("-filter_complex", cmd_manual)
        self.assertIn("-fps_mode", cmd_manual)
        self.assertIn("passthrough", cmd_manual)
        fc_str = [cmd_manual[i+1] for i, arg in enumerate(cmd_manual) if arg == "-filter_complex"][0]
        self.assertIn("select=gte(n\\,2)", fc_str)
        self.assertIn("concat=n=3:v=1:a=0", fc_str)
        self.assertIn("concat=n=3:v=0:a=1", fc_str)

        # 3. Modo manual con audio externo (replace)
        dummy_audio = os.path.join(self.tmp_path, "audio_stutter.mp3")
        cmd_manual_aud = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            list_file_path=dummy_list,
            output_file=dummy_out,
            mode="copy",
            anti_stutter=True,
            stutter_mode="manual",
            drop_start_frames=1,
            file_paths=files,
            audio_file=dummy_audio,
            audio_mode="replace"
        )
        self.assertIn(dummy_audio, cmd_manual_aud)
        self.assertIn("-map", cmd_manual_aud)
        self.assertIn("3:a:0", cmd_manual_aud)

        # 4. Probar ejecución real de concat con anti-stutter
        # Segmentar test_video en 2 partes
        seg_pat = os.path.join(self.tmp_path, "seg_stutter_%03d.mp4")
        subprocess.run(ffmpeg_core.build_segment_command(
            self.ffmpeg_path, self.test_video, seg_pat, segment_duration_sec=2, mode="exact"
        ), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        real_segments = sorted([
            os.path.join(self.tmp_path, f)
            for f in os.listdir(self.tmp_path)
            if f.startswith("seg_stutter_") and f.endswith(".mp4")
        ])
        real_list = os.path.join(self.tmp_path, "real_stutter_list.txt")
        ffmpeg_core.create_concat_list_file(real_segments, real_list)

        # Ejecutar real en modo auto (mpdecimate)
        out_real_auto = os.path.join(self.tmp_path, "out_real_auto.mp4")
        cmd_exec_auto = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            list_file_path=real_list,
            output_file=out_real_auto,
            anti_stutter=True,
            stutter_mode="auto"
        )
        res_auto = subprocess.run(cmd_exec_auto, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_auto.returncode, 0, f"Error en concat auto anti-stutter: {res_auto.stderr.decode('utf-8')}")
        self.assertTrue(os.path.isfile(out_real_auto))

        # Ejecutar real en modo manual (descartando 1 frame de seg 1)
        out_real_manual = os.path.join(self.tmp_path, "out_real_manual.mp4")
        cmd_exec_manual = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            output_file=out_real_manual,
            anti_stutter=True,
            stutter_mode="manual",
            drop_start_frames=1,
            file_paths=real_segments
        )
        res_manual = subprocess.run(cmd_exec_manual, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res_manual.returncode, 0, f"Error en concat manual anti-stutter: {res_manual.stderr.decode('utf-8')}")
        self.assertTrue(os.path.isfile(out_real_manual))

        # 5. Probar interacción de UI en TabConcat
        win = MainWindow()
        concat_tab = win.tab_concat
        concat_tab._insert_paths(real_segments)

        self.assertFalse(concat_tab.chk_anti_stutter.isChecked())
        self.assertTrue(concat_tab.widget_anti_stutter_opts.isHidden())

        # Activar anti-stutter
        concat_tab.chk_anti_stutter.setChecked(True)
        self.assertFalse(concat_tab.widget_anti_stutter_opts.isHidden())
        self.assertEqual(concat_tab.combo_mode.currentData(), "reencode")
        self.assertIn("mpdecimate", concat_tab.cmd_preview.text_cmd.toPlainText())

        # Cambiar a modo manual
        concat_tab.radio_stutter_manual.setChecked(True)
        self.assertTrue(concat_tab.spin_drop_frames.isEnabled())
        concat_tab.spin_drop_frames.setValue(2)
        preview_text = concat_tab.cmd_preview.text_cmd.toPlainText()
        self.assertIn("filter_complex", preview_text)
        self.assertIn("select=gte(n\\,2)", preview_text)

        # Si el usuario cambia de nuevo a Stream Copy, anti-stutter se desactiva automáticamente
        concat_tab.combo_mode.setCurrentIndex(0)  # "copy"
        self.assertFalse(concat_tab.chk_anti_stutter.isChecked())
        self.assertTrue(concat_tab.widget_anti_stutter_opts.isHidden())

        win.close()

    def test_23_audio_mix_volume_controls(self):
        """Verifica el control individual de volumen al mezclar audio en Poner Audio a Video y Unir Segmentos."""
        # 1. Probar build_add_audio_to_video_command con volúmenes personalizados
        cmd_add_vol = ffmpeg_core.build_add_audio_to_video_command(
            self.ffmpeg_path,
            video_file=self.test_video,
            audio_file=os.path.join(self.tmp_path, "audio.mp3"),
            output_file=os.path.join(self.tmp_path, "out_vol.mp4"),
            audio_mode="mix",
            has_original_audio=True,
            volume_orig=0.9,
            volume_added=0.35
        )
        cmd_str = " ".join(cmd_add_vol)
        self.assertIn("volume=0.9", cmd_str)
        self.assertIn("volume=0.35", cmd_str)
        self.assertIn("amix=inputs=2", cmd_str)

        # 2. Probar build_concat_command con modo mix y volúmenes personalizados
        dummy_list = os.path.join(self.tmp_path, "concat_list_vol.txt")
        dummy_audio = os.path.join(self.tmp_path, "bg_music_vol.mp3")
        dummy_out = os.path.join(self.tmp_path, "concat_out_vol.mp4")

        cmd_concat_vol = ffmpeg_core.build_concat_command(
            self.ffmpeg_path,
            list_file_path=dummy_list,
            output_file=dummy_out,
            mode="copy",
            audio_file=dummy_audio,
            audio_mode="mix",
            volume_orig=0.75,
            volume_added=0.25
        )
        cmd_concat_str = " ".join(cmd_concat_vol)
        self.assertIn("volume=0.75", cmd_concat_str)
        self.assertIn("volume=0.25", cmd_concat_str)
        self.assertIn("amix=inputs=2", cmd_concat_str)

        # 3. Probar interacción UI en TabConcat
        f_seg1 = os.path.join(self.tmp_path, "seg_vol_1.mp4")
        f_seg2 = os.path.join(self.tmp_path, "seg_vol_2.mp4")
        with open(f_seg1, "w") as f:
            f.write("dummy1")
        with open(f_seg2, "w") as f:
            f.write("dummy2")

        win = MainWindow()
        concat_tab = win.tab_concat
        concat_tab._insert_paths([f_seg1, f_seg2])

        # Sin archivo de audio, el subpanel de volumen debe estar oculto
        self.assertTrue(concat_tab.widget_concat_mix_vol.isHidden())

        # Seleccionar archivo de audio y cambiar a mix
        concat_tab.audio_selector.set_path(dummy_audio)
        concat_tab.combo_audio_mode.setCurrentIndex(1)  # "mix"
        self.assertFalse(concat_tab.widget_concat_mix_vol.isHidden())

        # Modificar deslizadores
        concat_tab.slider_vol_orig.setValue(70)
        concat_tab.slider_vol_added.setValue(40)
        preview_text = concat_tab.cmd_preview.text_cmd.toPlainText()
        self.assertIn("volume=0.7", preview_text)
        self.assertIn("volume=0.4", preview_text)

        # Limpiar audio -> se oculta el subpanel
        concat_tab.btn_clear_audio.click()
        self.assertTrue(concat_tab.widget_concat_mix_vol.isHidden())

        win.close()

    def test_24_segment_exact_10s_on_assembled_video_with_missing_first_frame(self):
        frames_dir = os.path.join(self.tmp_path, "frames_seq")
        os.makedirs(frames_dir, exist_ok=True)

        # Generar 660 fotogramas sintéticos (22 segundos a 30 fps)
        pattern = os.path.join(frames_dir, "frame_%06d.png")
        subprocess.run([
            self.ffmpeg_path, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=22:size=160x120:rate=30",
            pattern
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Simular caso de uso: usuario elimina el primer fotograma (frame_000001.png)
        first_frame = os.path.join(frames_dir, "frame_000001.png")
        self.assertTrue(os.path.isfile(first_frame))
        os.remove(first_frame)
        self.assertFalse(os.path.isfile(first_frame))

        # Detectar número inicial automáticamente (debe ser 2)
        start_num = ffmpeg_core.find_sequence_start_number(frames_dir, "frame_%06d.png")
        self.assertEqual(start_num, 2)

        # Crear video a partir de la secuencia comenzando en fotograma 2
        assembled_video = os.path.join(self.tmp_path, "assembled.mp4")
        cmd_create = ffmpeg_core.build_create_video_command(
            self.ffmpeg_path,
            input_pattern=pattern,
            output_file=assembled_video,
            fps=30.0,
            codec_preset="h264_visually_lossless",
            start_number=start_num
        )
        self.assertIn("-start_number", cmd_create)
        self.assertIn("-g", cmd_create)
        subprocess.run(cmd_create, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(os.path.isfile(assembled_video))

        # Segmentar a 10 segundos en modo exacto
        seg_dir = os.path.join(self.tmp_path, "segs_10s")
        os.makedirs(seg_dir, exist_ok=True)
        seg_pattern = os.path.join(seg_dir, "seg_%03d.mp4")
        cmd_seg = ffmpeg_core.build_segment_command(
            self.ffmpeg_path,
            input_file=assembled_video,
            output_pattern=seg_pattern,
            segment_duration_sec=10,
            mode="exact"
        )
        self.assertIn("-segment_time_delta", cmd_seg)
        subprocess.run(cmd_seg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        segs = sorted([os.path.join(seg_dir, f) for f in os.listdir(seg_dir) if f.endswith(".mp4")])
        self.assertGreaterEqual(len(segs), 2)

        # El primer segmento debe medir exactamente 10 segundos (no 18 segundos)
        info_first = ffmpeg_core.get_media_info(segs[0], self.ffprobe_path)
        self.assertAlmostEqual(info_first["duration"], 10.0, delta=0.15)

    def test_25_tab_drag_hover_activation_and_drop(self):
        from PyQt5.QtCore import QPoint, Qt, QMimeData, QUrl
        from PyQt5.QtGui import QDragEnterEvent, QDropEvent

        win = MainWindow()
        win.show()

        # Iniciar en pestaña 0
        win.tabs.setCurrentIndex(0)
        self.assertEqual(win.tabs.currentIndex(), 0)

        # 1. Simular arrastrar sobre pestaña 5 ('Segmentar Video')
        bar = win.tabs.tab_bar
        rect_tab5 = bar.tabRect(5)
        pos5 = rect_tab5.center()

        test_file = os.path.join(self.tmp_path, "drag_test.mp4")
        with open(test_file, "w") as f:
            f.write("test")

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(test_file)])

        ev_enter = QDragEnterEvent(pos5, Qt.CopyAction, mime, Qt.NoButton, Qt.NoModifier)
        bar.dragEnterEvent(ev_enter)
        self.assertTrue(ev_enter.isAccepted())
        self.assertEqual(bar._pending_tab_index, 5)

        # Activar hover
        bar._activate_pending_tab()
        self.assertEqual(win.tabs.currentIndex(), 5)

        # 2. Soltar (drop) en la cabecera de la pestaña 5
        ev_drop = QDropEvent(pos5, Qt.CopyAction, mime, Qt.NoButton, Qt.NoModifier)
        bar.dropEvent(ev_drop)
        self.assertTrue(ev_drop.isAccepted())
        self.assertEqual(
            os.path.normpath(win.tab_segment.input_selector.get_path()),
            os.path.normpath(test_file)
        )

        # 3. Soltar en cabecera de pestaña 1 ('Convertir Video')
        rect_tab1 = bar.tabRect(1)
        ev_drop1 = QDropEvent(rect_tab1.center(), Qt.CopyAction, mime, Qt.NoButton, Qt.NoModifier)
        bar.dropEvent(ev_drop1)
        self.assertEqual(win.tabs.currentIndex(), 1)
        self.assertEqual(
            os.path.normpath(win.tab_convert.input_selector.get_path()),
            os.path.normpath(test_file)
        )

        win.close()

    def test_26_voice_isolation_and_diarization(self):
        """Verifica la lógica de comandos FFmpeg de aislamiento vocal, ensamblado de muestras y diarización tímbrica."""
        import numpy as np
        import diarization_core
        from ui.main_window import MainWindow

        # 1. Comandos de aislamiento vocal en ffmpeg_core
        cmd_clean = ffmpeg_core.build_voice_isolation_command(
            ffmpeg_path="ffmpeg",
            input_file="interview.mp4",
            output_file="interview_clean.wav",
            profile="studio",
            normalize_speech=True,
            remove_silence=True,
            audio_format="wav_24"
        )
        cmd_str = " ".join(cmd_clean)
        self.assertIn("-vn", cmd_str)
        self.assertIn("afftdn", cmd_str)
        self.assertIn("speechnorm", cmd_str)
        self.assertIn("silenceremove", cmd_str)
        self.assertIn("pcm_s24le", cmd_str)

        # 2. Comando de extracción mono 16kHz
        cmd_mono = ffmpeg_core.build_extract_mono_wav_command("ffmpeg", "test.mp4", "mono.wav")
        self.assertIn("-ar 16000", " ".join(cmd_mono))
        self.assertIn("-ac 1", " ".join(cmd_mono))

        # 3. Detección de silencios y parseo de segmentos de voz
        mock_silence_log = """
        [Parsed_silencedetect_1 @ 0x123] silence_start: 2.500
        [Parsed_silencedetect_1 @ 0x123] silence_end: 4.000 | silence_duration: 1.500
        [Parsed_silencedetect_1 @ 0x123] silence_start: 7.200
        [Parsed_silencedetect_1 @ 0x123] silence_end: 8.500 | silence_duration: 1.300
        """
        speech_segs = ffmpeg_core.parse_silence_detect_output(mock_silence_log, total_duration=10.0)
        self.assertEqual(len(speech_segs), 3)
        self.assertEqual(speech_segs[0], (0.0, 2.5))
        self.assertEqual(speech_segs[1], (4.0, 7.2))
        self.assertEqual(speech_segs[2], (8.5, 10.0))

        # 4. Ensamble de segmentos con atrim y concat
        cmd_stitch = ffmpeg_core.build_stitch_segments_command(
            ffmpeg_path="ffmpeg",
            input_file="input.mp4",
            segments=[(1.0, 4.0), (6.0, 9.5)],
            output_file="speaker_sample.wav",
            apply_cleanup=True
        )
        stitch_str = " ".join(cmd_stitch)
        self.assertIn("atrim=start=1.000:end=4.000", stitch_str)
        self.assertIn("atrim=start=6.000:end=9.500", stitch_str)
        self.assertIn("concat=n=2:v=0:a=1", stitch_str)

        # 5. Motor de diarización acústica con Scipy / NumPy
        sr = 16000
        t = np.linspace(0, 1.0, sr)
        # Generar audio sintético con 2 personas (Hombre: ~130Hz, Mujer: ~240Hz)
        sig_male = (0.6 * np.sin(2 * np.pi * 130 * t)).astype(np.float32)
        sig_female = (0.6 * np.sin(2 * np.pi * 240 * t)).astype(np.float32)

        feat_m = diarization_core.compute_acoustic_features(sig_male, sr)
        feat_f = diarization_core.compute_acoustic_features(sig_female, sr)
        self.assertEqual(feat_m.shape, (29,))
        self.assertEqual(feat_f.shape, (29,))

        # Crear archivo temporal WAV con turnos alternados
        test_wav = os.path.join(self.tmp_path, "synthetic_dialog.wav")
        combined_audio = np.concatenate([sig_male, sig_female, sig_male, sig_female])
        combined_int16 = (combined_audio * 32767).astype(np.int16)
        import scipy.io.wavfile as wavfile
        wavfile.write(test_wav, sr, combined_int16)

        test_segments = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]
        diar_res = diarization_core.perform_speaker_diarization(test_wav, test_segments, num_speakers=2)
        self.assertEqual(diar_res["num_speakers"], 2)
        self.assertEqual(len(diar_res["speakers"]), 2)
        self.assertGreater(diar_res["total_speech_duration"], 0.0)

        # Probar diarización automática sobre un único segmento continuo de habla (sin pre-segmentar)
        diar_continuous = diarization_core.perform_speaker_diarization(test_wav, [(0.0, 4.0)], num_speakers=2)
        self.assertEqual(diar_continuous["num_speakers"], 2)
        self.assertEqual(len(diar_continuous["speakers"]), 2)

        # 6. Interfaz gráfica MainWindow y TabVoiceIsolation
        win = MainWindow(initial_tab="voice")
        win.show()
        self.assertEqual(win.tabs.currentIndex(), 7)
        voice_tab = win.tab_voice
        self.assertIsNotNone(voice_tab)

        # Probar cambio de modos en UI (Limpieza, Diarización y Manual)
        voice_tab.radio_mode_diar.setChecked(True)
        self.assertFalse(voice_tab.panel_diar.isHidden())
        self.assertTrue(voice_tab.panel_clean.isHidden())
        self.assertTrue(voice_tab.panel_manual.isHidden())

        voice_tab.radio_mode_manual.setChecked(True)
        self.assertFalse(voice_tab.panel_manual.isHidden())
        self.assertTrue(voice_tab.panel_clean.isHidden())
        self.assertTrue(voice_tab.panel_diar.isHidden())

        voice_tab.radio_mode_clean.setChecked(True)
        self.assertFalse(voice_tab.panel_clean.isHidden())
        self.assertTrue(voice_tab.panel_diar.isHidden())
        self.assertTrue(voice_tab.panel_manual.isHidden())

        # 7. Línea de tiempo gráfica interactiva y selector de segmentos de voz
        from ui.timeline_waveform import AudioTimelineCanvas, AudioSegmentSelectorWidget, format_seconds_exact
        self.assertEqual(format_seconds_exact(75.5), "01:15.50")
        self.assertEqual(format_seconds_exact(0.0), "00:00.00")

        canvas = AudioTimelineCanvas()
        canvas.set_media(10.0, np.zeros(100, dtype=np.float32))
        canvas.set_segments([(1.0, 3.5), (6.0, 8.5)])
        self.assertEqual(len(canvas.segments), 2)
        self.assertEqual(canvas.get_selected_segment(), (1.0, 3.5))

        # Borrar segmento seleccionado
        canvas.delete_selected_segment()
        self.assertEqual(len(canvas.segments), 1)
        self.assertEqual(canvas.segments[0], (6.0, 8.5))

        # Limpiar todo
        canvas.clear_all_segments()
        self.assertEqual(len(canvas.segments), 0)

        # Probar zoom y navegación en la forma de onda
        canvas.set_media(10.0, np.zeros(2400, dtype=np.float32))
        self.assertEqual(canvas.zoom_level, 1.0)
        self.assertEqual(canvas.view_start, 0.0)

        canvas.set_zoom(2.0)
        self.assertEqual(canvas.zoom_level, 2.0)
        canvas.set_view_start(2.5)
        self.assertEqual(canvas.view_start, 2.5)

        canvas.zoom_in()
        self.assertGreater(canvas.zoom_level, 2.0)
        canvas.reset_zoom()
        self.assertEqual(canvas.zoom_level, 1.0)
        self.assertEqual(canvas.view_start, 0.0)

        # Probar arrastre del marcador playhead por el triángulo superior
        canvas.resize(400, 130)
        canvas.set_playhead(2.0)
        px = canvas._time_to_x(2.0)
        from PyQt5.QtGui import QMouseEvent
        from PyQt5.QtCore import Qt, QPointF

        # Simular clic en el triángulo superior
        press_ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(px, 10.0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        canvas.mousePressEvent(press_ev)
        self.assertEqual(canvas._drag_mode, 'playhead')

        # Simular arrastre a 5.0 segundos
        seek_vals = []
        canvas.seek_requested.connect(seek_vals.append)
        px_new = canvas._time_to_x(5.0)
        move_ev = QMouseEvent(QMouseEvent.MouseMove, QPointF(px_new, 10.0), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        canvas.mouseMoveEvent(move_ev)
        self.assertAlmostEqual(canvas.playhead_pos, 5.0, delta=0.1)
        self.assertTrue(len(seek_vals) > 0)

        # Soltar ratón
        release_ev = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(px_new, 10.0), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        canvas.mouseReleaseEvent(release_ev)
        self.assertIsNone(canvas._drag_mode)

        # Probar interacción con el widget contenedor y carga desde tarjeta de hablante
        timeline_widget = voice_tab.timeline_widget
        timeline_widget.set_segments([(2.0, 5.0), (7.0, 9.0)])
        self.assertEqual(len(timeline_widget.get_segments()), 2)

        # Controles de Zoom en timeline_widget
        self.assertIsNotNone(timeline_widget.btn_zoom_in)
        self.assertIsNotNone(timeline_widget.btn_zoom_out)
        self.assertIsNotNone(timeline_widget.btn_zoom_fit)
        self.assertIsNotNone(timeline_widget.scrollbar)
        self.assertEqual(timeline_widget.lbl_zoom.text(), "100%")

        timeline_widget.btn_zoom_in.click()
        self.assertGreater(timeline_widget.canvas.zoom_level, 1.0)
        self.assertFalse(timeline_widget.scrollbar.isHidden())
        self.assertNotEqual(timeline_widget.lbl_zoom.text(), "100%")

        timeline_widget.btn_zoom_fit.click()
        self.assertEqual(timeline_widget.canvas.zoom_level, 1.0)
        self.assertTrue(timeline_widget.scrollbar.isHidden())
        self.assertEqual(timeline_widget.lbl_zoom.text(), "100%")

        mock_spk_data = {
            "id": 1,
            "name": "Hablante 1",
            "segments": [(0.5, 2.5), (4.0, 6.2)],
            "segment_count": 2,
            "total_duration_fmt": "00:04"
        }
        voice_tab._edit_speaker_in_timeline(mock_spk_data)
        self.assertTrue(voice_tab.radio_mode_manual.isChecked())
        self.assertEqual(timeline_widget.get_segments(), [(0.5, 2.5), (4.0, 6.2)])

        # Probar botones de reproducción normal y selección
        self.assertIsNotNone(timeline_widget.btn_play_normal)
        self.assertIsNotNone(timeline_widget.btn_play_seg)
        timeline_widget.set_playing_state(True, mode="normal")
        self.assertEqual(timeline_widget.btn_play_normal.text(), " Detener")
        timeline_widget.set_playing_state(True, mode="selection")
        self.assertEqual(timeline_widget.btn_play_seg.text(), " Detener")
        timeline_widget.set_playing_state(False)
        self.assertEqual(timeline_widget.btn_play_normal.text(), " Reproducir")
        self.assertEqual(timeline_widget.btn_play_seg.text(), " Reproducir Selección")

        # Probar temporizador suave y persistencia del marcador al detenerse
        self.assertIsNotNone(voice_tab._smooth_timer)
        self.assertEqual(voice_tab._smooth_timer.interval(), 25)

        # Detener reproducción no debe resetear el marcador rojo a 0.0
        timeline_widget.set_playhead_pos(4.5)
        voice_tab._on_timeline_stop_requested()
        self.assertEqual(timeline_widget.canvas.playhead_pos, 4.5)

        # Señales de posición 0 al detenerse no deben sobreescribir la posición
        voice_tab._on_player_position_changed(0)
        self.assertEqual(timeline_widget.canvas.playhead_pos, 4.5)

        win.close()


if __name__ == "__main__":
    unittest.main()



