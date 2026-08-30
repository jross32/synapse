Option Explicit

Dim shell, fso, scriptPath, repoRoot, devScript, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptPath = WScript.ScriptFullName
repoRoot = fso.GetParentFolderName(fso.GetParentFolderName(scriptPath))
devScript = fso.BuildPath(repoRoot, "scripts\dev.ps1")

command = "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File " & _
          Chr(34) & devScript & Chr(34) & " -ShortcutMode"

shell.CurrentDirectory = repoRoot
shell.Run command, 0, False
