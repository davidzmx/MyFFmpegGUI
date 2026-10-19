# MyFFmpeg GUI - Suite Multimedia Sin Pérdida (Multiplataforma)

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-41CD52?logo=qt&logoColor=white)
![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-007808?logo=ffmpeg&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-555555)
![Tests](https://img.shields.io/badge/Tests-14%2F14%20Passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

Una suite gráfica moderna, elegante y de alto rendimiento basada en **Python y PyQt5** para aprovechar todo el poder de **FFmpeg** sin pérdida de calidad (*lossless / stream copy*). Soporta tanto ejecución completa con interfaz gráfica como atajos ultrarrápidos en segundo plano integrados en el **menú contextual de clic derecho** de tu explorador de archivos (**KDE Dolphin, GNOME Nautilus y Windows Explorer**).

---

## 🌟 Características Implementadas

### 1. 🎵 Conversión de Video a Audio (WAV y MP3)
- **Formatos WAV sin pérdida:**
  - **WAV 16-bit PCM:** Calidad CD estándar.
  - **WAV 24-bit PCM:** Alta definición de estudio.
  - **WAV 32-bit Float:** Precisión matemática máxima.
- **Formatos MP3 de máxima fidelidad:**
  - **MP3 320 kbps (CBR):** Máxima tasa de bits estándar.
  - **MP3 VBR Calidad 0 (LAME V0):** Máxima fidelidad perceptual dinámica.
  - Opciones de 256 kbps y 192 kbps.
- **Extracción Directa (Stream Copy):** Copia el stream de audio original sin recodificar (`-c:a copy`).
- **Control de Frecuencia de Muestreo (Sample Rate):** 44100 Hz, 48000 Hz, 96000 Hz o tasa original.
- Preservación íntegra de metadatos.

### 2. 🎬 Conversor entre Formatos de Video
- **Contenedores soportados:** MP4, MKV, MOV, WebM, AVI, TS y GIF animado de alta calidad.
- **Modos de procesamiento:**
  - **Copia Directa (Stream Copy - 100% Sin Pérdida):** Cambia el contenedor (ej. de MKV a MP4) en segundos sin tocar un solo píxel.
  - **H.264 Lossless (`CRF 0`):** Matemáticamente sin pérdida.
  - **H.264 Visualmente Idéntico (`CRF 17`):** Indistinguible de la fuente y compatible universalmente.
  - **H.265 / HEVC (`CRF 20`):** Máxima compresión preservando calidad.
  - **Apple ProRes 422 HQ:** Estándar de edición profesional.
  - **WebM VP9 con audio Opus:** Compatible con navegadores y HTML5.
  - **GIF Animado:** Con paleta adaptativa de alta definición (`palettegen`).
- Selección de resolución (Mantener original, 4K, 1080p, 720p, 480p) y mapeo de subtítulos/múltiples pistas de audio (`-map 0`).

### 3. 📁 Configuración de Carpeta Base y Sugerencias Inteligentes
- **Carpeta Base configurable:** Permite definir la carpeta raíz donde se organizará todo el contenido procesado.
- **Sugerencia automática de carpetas:** Si se activa, para un archivo `viaje.mp4`, sugiere automáticamente una subcarpeta `viaje/` dentro de la carpeta base (ej. `.../CarpetaBase/viaje/viaje_audio.wav`).
- **Creación automática:** Si la carpeta sugerida no existe, la aplicación la crea automáticamente en el momento del guardado.
- **Activación / Desactivación:** Se puede activar o desactivar tanto globalmente en Ajustes como individualmente en cada pestaña.

### 4. 📸 Extracción de Fotogramas Sin Pérdida
- Formatos: **PNG (100% Lossless)**, TIFF, WebP Lossless y JPEG q:v 1.
- Opciones: Todos los fotogramas (`-fps_mode passthrough`), 1 FPS, fotogramas clave (*Keyframes / I-Frames*) o FPS personalizado.
- Extracción de intervalos de tiempo específicos.

### 5. 🎞️ Crear Video a partir de Secuencias de Fotogramas
- Ensamblado rápido de imágenes secuenciales (`frame_%06d.png`).
- Selección de FPS y códecs sin pérdida (CRF 0, CRF 17, ProRes, VP9).
- Posibilidad de incorporar una pista de audio sincronizada.

### 6. ✂️ Segmentar Videos en Partes Configurables
- Corta videos en segmentos de duración definida (ej. 15 segundos, 30 segundos, etc.).
- **Modo Stream Copy:** Instantáneo y sin recodificar.
- **Modo Corte Exacto:** Fuerza fotogramas clave en los segundos exactos (`CRF 17`).

### 7. 🔗 Unir Segmentos de Video
- Lista interactiva para añadir archivos, carpetas enteras, reordenar y eliminar con soporte Drag & Drop.
- **Modo Concat Demuxer (`-c copy`):** Unión directa y sin pérdida de calidad.

### 8. 🖱️ Integración y Atajos en el Menú Contextual (Clic Derecho)
- **Atajos Rápidos en Segundo Plano (Sin abrir la interfaz):**
  - **⚡ Rápido: Convertir a MP3:** Ejecuta directamente `ffmpeg -i "mi_archivo.mp4" "mi_archivo.mp3"` en la misma carpeta y emite una notificación de escritorio nativa al finalizar.
  - **⚡ Rápido: Convertir a WAV:** Conversión directa a audio WAV sin compresión.
  - **⚡ Rápido: Extraer Audio Original:** Copia el stream de audio original sin pérdida (`-c:a copy`).
- **Opciones de Apertura de Herramientas (Con GUI):**
  - Abre la aplicación directamente en la pestaña correspondiente (Audio, Video, Fotogramas, Segmentación) cargando de inmediato el archivo seleccionado.
- **Configuración Completa y Atajos Personalizados:**
  - En la pestaña **Ajustes**, una tabla interactiva permite **activar o desactivar** cada atajo individualmente.
  - Botón **`[ ➕ Agregar Atajo Rápido Personalizado ]`** para crear cualquier comando FFmpeg propio con variables como `{input}`, `{output_no_ext}`, `{output_dir}`, etc.
  - Actualización instantánea en Dolphin (KDE), Nautilus (GNOME) y Windows Explorer sin requerir permisos de administrador.

---

## 🚀 Instalación y Ejecución

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Ejecutar la suite de pruebas automatizadas (14/14 pruebas)
python test_gui.py

# 3. Lanzar la aplicación
python main.py
```

---

## 🪟 Compatibilidad con Windows e Instalador (.exe)

La suite cuenta con soporte nativo completo para **Windows 10 y Windows 11**:
1. **Menú contextual en Windows Explorer:**
   - Registrado en `HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations` (no requiere permisos de Administrador).
   - Crea el submenú `MyFFmpeg GUI >` ordenado numéricamente (`1. ⚡...`, `2. 🎵...`).
   - Los atajos rápidos se ejecutan silenciosamente en segundo plano mediante `pythonw.exe` o el ejecutable compilado, sin ventanas negras de consola.
   - Notificaciones nativas tipo Balloon / Toast en Windows.

2. **Crear el Instalador de Windows (`MyFFmpegGUI_Setup.exe`):**
   - Se incluye el script automatizado [build_windows_installer.bat](file:///home/david/mytests/MyffmpegGUI/build_windows_installer.bat) y el archivo de Inno Setup [installer_windows.iss](file:///home/david/mytests/MyffmpegGUI/installer_windows.iss).
   - Para compilar todo automáticamente en Windows:
     ```cmd
     build_windows_installer.bat
     ```
   - Esto compilará la aplicación con PyInstaller en `dist\MyFFmpegGUI\` y generará el asistente de instalación `Output\MyFFmpegGUI_Setup_v1.0.0.exe`.
   - El instalador:
     - Crea accesos directos en el Escritorio y Menú Inicio.
     - Permite instalar en modo usuario (`AppData\Local\Programs`) o administrador (`Program Files`).
     - Registra automáticamente las opciones del menú contextual al instalar (`--install-context`) y las elimina limpiamente al desinstalar (`--uninstall-context`).

3. **Crear la Versión Portable (Sin Instalación / USB Pendrive):**
   - Se incluye el script automatizado [build_windows_portable.bat](file:///home/david/mytests/MyffmpegGUI/build_windows_portable.bat).
   - Para generar el paquete portable en Windows:
     ```cmd
     build_windows_portable.bat
     ```
   - Esto genera:
     - La carpeta autosuficiente `dist\MyFFmpegGUI_Portable\`
     - El archivo comprimido `dist\MyFFmpegGUI_Portable_Windows.zip` listo para compartir.
   - **Ventajas de la versión portable:**
     - No toca el Registro de Windows a menos que el usuario lo active explícitamente en Ajustes.
     - Cero dependencias: almacena su configuración `config.json` en su propia carpeta.
     - Detecta automáticamente `ffmpeg.exe` y `ffprobe.exe` si se colocan dentro de `bin/` o junto al `.exe`.
     - Puede ejecutarse desde un pendrive, disco externo o cualquier carpeta sin requerir derechos de administrador.

---

## 🐧 Instaladores para Linux

Se ofrecen dos métodos de instalación oficiales para Linux:

### Opción 1: Paquete Debian / Ubuntu (.deb)
Para generar el archivo instalador `.deb` oficial de forma automática:
```bash
./build_deb.sh
```
Esto genera `dist/myffmpeg-gui_1.0.0_all.deb`. Para instalarlo:
```bash
sudo apt install ./dist/myffmpeg-gui_1.0.0_all.deb
```
O simplemente haz doble clic sobre el archivo `.deb` en tu gestor de archivos (Discover de KDE, GNOME Software o GDebi). Resuelve automáticamente dependencias (`python3-pyqt5`, `ffmpeg`).

### Opción 2: Instalador de Usuario en 1 Clic (Sin sudo / Sin root)
Para instalar la aplicación en el espacio de usuario (`~/.local/share/myffmpeg-gui`):
```bash
./install.sh
```
- Añade el comando `myffmpeg-gui` a `~/.local/bin/`.
- Integra el icono en el Menú de Aplicaciones del sistema.
- Registra automáticamente las opciones del menú contextual en **KDE Dolphin** y **GNOME Nautilus**.
- Para desinstalarla limpiamente en cualquier momento:
  ```bash
  ./uninstall.sh
  ```

