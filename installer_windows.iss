; ========================================================
; Inno Setup Script para MyFFmpeg GUI (Windows x64)
; ========================================================
; Permite generar un instalador ejecutable profesional (.exe)
; Requiere Inno Setup 6 o superior (https://jrsoftware.org/isdl.php)

#define MyAppName "MyFFmpeg GUI"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "MyTests"
#define MyAppExeName "MyFFmpegGUI.exe"

[Setup]
AppId={{E39B1E47-8140-42DE-8373-E75FF8B4019E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Permite instalar sin permisos de administrador si el usuario no los tiene
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=MyFFmpegGUI_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableDirPage=no
DisableProgramGroupPage=no
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "Integrar atajos en el Menú Contextual (Clic derecho en videos y audios)"; GroupDescription: "Integración en el Sistema:"; Flags: checkedonce

[Files]
; Archivos compilados con PyInstaller (carpeta dist\MyFFmpegGUI)
Source: "dist\MyFFmpegGUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Iconos y recursos
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

; Binarios de FFmpeg si están incluidos en bin\ (opcional)
Source: "bin\ffmpeg.exe"; DestDir: "{app}\bin"; Flags: ignoreversion skipifsourcedoesntexist
Source: "bin\ffprobe.exe"; DestDir: "{app}\bin"; Flags: ignoreversion skipifsourcedoesntexist

; Archivos auxiliares de registro
Source: "instalar_menu_contextual_windows.reg"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "desinstalar_menu_contextual_windows.reg"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
; Si el usuario marcó la opción de menú contextual, registrarlo automáticamente usando la propia app
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-context"; Flags: runhidden; Tasks: contextmenu
; Ofrecer ejecutar la aplicación al finalizar la instalación
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Limpiar las entradas del menú contextual al desinstalar
Filename: "{app}\{#MyAppExeName}"; Parameters: "--uninstall-context"; Flags: runhidden
