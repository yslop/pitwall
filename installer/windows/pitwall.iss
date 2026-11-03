; Pitwall Setup (Inno Setup 6). Built by installer/build.py:
;   ISCC /DVersion=0.2.0 /DPayload=<folder> /DOutDir=<folder> /DOutName=<name> pitwall.iss
#ifndef Version
  #define Version "dev"
#endif
#ifndef Payload
  #define Payload "payload"
#endif
#ifndef OutDir
  #define OutDir "."
#endif
#ifndef OutName
  #define OutName "Pitwall-setup"
#endif

[Setup]
AppId={{6F1C9C1E-5B7B-4C8A-9E0A-3D2F1A7B9C41}
AppName=Pitwall
AppVersion={#Version}
AppPublisher=yslop
AppPublisherURL=https://github.com/yslop/pitwall
DefaultDirName={userdocs}\Pitwall
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutDir}
OutputBaseFilename={#OutName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UsePreviousAppDir=yes
Uninstallable=no
CreateUninstallRegKey=no

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; program files are replaced on update; your own data (config, pipeline, preferences, profile) is never overwritten
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "config\*,_system\pipeline.csv,_system\preferences.json,_system\profile.json"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userdesktop}\Pitwall"; Filename: "{app}\pitwall.cmd"; WorkingDir: "{app}"; Comment: "Pitwall Cockpit"
Name: "{userprograms}\Pitwall"; Filename: "{app}\pitwall.cmd"; WorkingDir: "{app}"; Comment: "Pitwall Cockpit"

[Run]
Filename: "{app}\pitwall.cmd"; WorkingDir: "{app}"; Flags: postinstall nowait shellexec skipifsilent; Description: "{cm:LaunchProgram,Pitwall}"
