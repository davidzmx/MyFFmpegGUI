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
        # 7 pestañas completas
        self.assertEqual(win.tabs.count(), 7)

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

        # 5. Probar limpieza
        concat_tab._clear_list()
        self.assertEqual(concat_tab.list_widget.count(), 0)
        self.assertIn("Seleccione los archivos", concat_tab.cmd_preview.text_cmd.toPlainText())

        win.close()


if __name__ == "__main__":
    unittest.main()

