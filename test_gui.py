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
        # 8 pestañas completas
        self.assertEqual(win.tabs.count(), 8)
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

        # 1. Comprobar que TabConcat utiliza un QSplitter vertical de 3 secciones (lista, controles, terminal)
        splitters = concat_tab.findChildren(QSplitter)
        self.assertGreater(len(splitters), 0, "TabConcat debe contener un QSplitter")
        self.assertEqual(concat_tab.splitter.count(), 3, "El splitter debe contener 3 secciones: lista, opciones y terminal")
        self.assertGreater(concat_tab.list_widget.minimumHeight(), 0)

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
        self.assertEqual(win.tabs.count(), 8)
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

        # Probar repetición continua (bucle)
        self.assertFalse(player.btn_loop.isChecked())
        self.assertFalse(player.worker._loop)
        player.btn_loop.setChecked(True)
        player._toggle_loop()
        self.assertTrue(player.worker._loop)
        player._toggle_loop_shortcut()
        self.assertFalse(player.worker._loop)
        self.assertFalse(player.btn_loop.isChecked())

        # Probar que al llegar al final, reproducir reinicia desde el inicio (0.0s)
        player.worker._current_time = player.duration
        player._on_toggle_play()
        self.assertEqual(player.worker._seek_requested, 0.0)

        # Cerrar el reproductor
        player.close()
        self.assertFalse(player.worker.isRunning())

        win.close()


if __name__ == "__main__":
    unittest.main()


