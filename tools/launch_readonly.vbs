' launch_readonly.vbs - Lanza el .exe de DaniBOD ZZZ Analytics en modo READONLY.
'
' Un acceso directo (.lnk) no puede setear variables de entorno. Este launcher VBS
' setea DANIBOD_READONLY=1 en el entorno del proceso y lanza el .exe, que lo HEREDA.
' Corre bajo wscript (subsistema GUI) -> SIN ventana de consola (cero flash).
'
' En modo readonly la app detecta y loguea normal pero NO escribe nada (DB ni la
' libreria de avatares). Ideal para QA sin tocar datos. Ver app/db/connection.py y
' qa_launch.ps1 (-ReadOnly).
'
' El path del .exe se resuelve relativo a la ubicacion de este script (tools\), asi
' que sobrevive a rebuilds sin editar nada.

Option Explicit
Dim sh, fso, scriptDir, repoRoot, exePath
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)   ' ...\tools
repoRoot  = fso.GetParentFolderName(scriptDir)                ' raiz del repo
exePath   = repoRoot & "\app\build\dist\DaniBOD_ZZZ_Analytics\DaniBOD_ZZZ_Analytics.exe"

If Not fso.FileExists(exePath) Then
    MsgBox "No se encontro el .exe en:" & vbCrLf & exePath & vbCrLf & _
           "Rebuildea con tools\rebuild.ps1.", vbExclamation, "DaniBOD ZZZ Analytics (ReadOnly)"
    WScript.Quit 1
End If

' Setear el flag en el entorno del proceso; el .exe hijo lo hereda.
sh.Environment("Process").Item("DANIBOD_READONLY") = "1"
sh.CurrentDirectory = fso.GetParentFolderName(exePath)
' windowStyle=1 (normal), waitOnReturn=False (no bloquear; el launcher sale enseguida).
sh.Run """" & exePath & """", 1, False
