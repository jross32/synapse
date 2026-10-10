!include "LogicLib.nsh"
!include "nsDialogs.nsh"

; Before setup tries to replace Electron files, allow graceful cleanup of a
; desktop process that remained hidden after its window closed. The helper
; checks the *exact executable path*, never the developer daemon or other apps.
!macro customInit
  InitPluginsDir
  File /oname=$PLUGINSDIR\synapse-close-desktop.ps1 "${PROJECT_DIR}\installer\synapse-close-desktop.ps1"
  StrCpy $R8 "$INSTDIR"
  IfFileExists "$R8\Synapse.exe" synapse_desktop_check
    StrCpy $R8 "$LOCALAPPDATA\Programs\synapse"
  synapse_desktop_check:
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\synapse-close-desktop.ps1" -Action Check -InstallDir "$R8"'
  Pop $R7
  Pop $R6
  ${If} $R7 == 10
    Sleep 1500
    nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\synapse-close-desktop.ps1" -Action Check -InstallDir "$R8"'
    Pop $R7
    Pop $R6
    ${If} $R7 == 10
      IfSilent synapse_desktop_close_done
      MessageBox MB_YESNO|MB_ICONQUESTION "Synapse is still running in the background. Allow Setup to close the Synapse desktop app (not development workers), then continue the update?" IDNO synapse_desktop_close_done
      nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\synapse-close-desktop.ps1" -Action Close -InstallDir "$R8"'
      Pop $R7
      Pop $R6
      ${If} $R7 == 0
        Sleep 1500
      ${Else}
        MessageBox MB_OK|MB_ICONEXCLAMATION "Synapse could not close automatically. Save your work, close Synapse in Task Manager, then choose Retry if prompted."
      ${EndIf}
    ${EndIf}
  ${EndIf}
  synapse_desktop_close_done:
  StrCpy $RepairMode 0
  ; Silent reinstallation preserves the user's existing optional bundle choices.
  IfSilent 0 +4
    IfFileExists "$INSTDIR\Synapse.exe" 0 +2
      StrCpy $RepairMode 1
    IfFileExists "$INSTDIR\resources\app\package.json" 0 +2
      StrCpy $RepairMode 1
  StrCpy $BundleResearchState 1
  StrCpy $BundleFactoryState 1
  StrCpy $BundleRescueState 1
  StrCpy $BundleHarvestState 0
  StrCpy $BundleImageStudioState 1
!macroend
Var ExistingInstallDialog
Var ExistingInstallLabel
Var ExistingInstallChoice
Var ExistingInstallPath
Var RepairMode
Var ExistingInstallDetected

; Run before optional bundle page. NSIS keeps all account/project files outside
; the application folder; never remove $APPDATA or local data on repair.
Page custom SynapseExistingInstallPageCreate SynapseExistingInstallPageLeave

Function SynapseExistingInstallPageCreate
  StrCpy $ExistingInstallDetected 0
  StrCpy $ExistingInstallPath "$INSTDIR"
  IfFileExists "$INSTDIR\Synapse.exe" 0 +2
    StrCpy $ExistingInstallDetected 1
  ${If} $ExistingInstallDetected == 0
    IfFileExists "$INSTDIR\resources\app\package.json" 0 +2
      StrCpy $ExistingInstallDetected 1
  ${EndIf}
  ${If} $ExistingInstallDetected == 0
    IfFileExists "$LOCALAPPDATA\Programs\synapse\Synapse.exe" 0 +3
      StrCpy $ExistingInstallDetected 1
      StrCpy $ExistingInstallPath "$LOCALAPPDATA\Programs\synapse"
  ${EndIf}
  ${If} $ExistingInstallDetected == 0
    Abort ; fresh install; no repair page needed
  ${EndIf}
  ; Silent installs must repair/update existing files without blocking.
  IfSilent 0 +3
    StrCpy $RepairMode 1
    Abort
  nsDialogs::Create 1018
  Pop $ExistingInstallDialog
  ${If} $ExistingInstallDialog == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 28u "SYNAPSE  /  REPAIR & UPDATE"
  Pop $ExistingInstallLabel
  SetCtlColors $ExistingInstallLabel 8A42CF transparent
  ${NSD_CreateLabel} 0 30u 100% 32u "Existing workspace detected. Refresh application components without deleting accounts or project data."
  Pop $ExistingInstallLabel
  ${NSD_CreateCheckbox} 0 66u 100% 23u "Repair + update Synapse (recommended)"
  Pop $ExistingInstallChoice
  ${NSD_Check} $ExistingInstallChoice
  ${NSD_CreateLabel} 0 94u 100% 38u "Installed at: $ExistingInstallPath. Unchecking performs a standard install; your personal data is preserved either way."
  Pop $0
  nsDialogs::Show
FunctionEnd

Function SynapseExistingInstallPageLeave
  ${If} $ExistingInstallDetected == 1
    IfSilent +2 0
      ${NSD_GetState} $ExistingInstallChoice $RepairMode
    ${If} $RepairMode == 1
      StrCpy $INSTDIR "$ExistingInstallPath"
    ${EndIf}
  ${EndIf}
FunctionEnd
; Branded journey pages follow the approved Synapse installer storyboard.
; The NSIS wizard keeps system-native installation semantics and silent mode.
Var SynapseCheckDialog
Var SynapseCheckText
Var SynapseReleaseDialog

Page custom SynapseReadinessPage
Page custom SynapseReleasePage

Function SynapseReadinessPage
  IfSilent 0 +2
    Abort
  nsDialogs::Create 1018
  Pop $SynapseCheckDialog
  ${If} $SynapseCheckDialog == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 19u "SYNAPSE  /  SYSTEM READINESS"
  Pop $0
  SetCtlColors $0 8141D9 transparent
  ${NSD_CreateLabel} 0 24u 100% 34u "Getting this computer ready for your connected AI workspace. Setup will preserve your project files, settings, and existing credentials."
  Pop $0
  ${NSD_CreateLabel} 0 66u 100% 15u "01    Windows desktop available"
  Pop $0
  ${NSD_CreateLabel} 0 86u 100% 15u "02    Install or repair application files"
  Pop $0
  ${NSD_CreateLabel} 0 106u 100% 15u "03    Account connection checked after installation"
  Pop $0
  ${NSD_CreateLabel} 0 137u 100% 30u "Automatic diagnostics run when setup finishes. Connection problems can be repaired or reported without deleting your workspace."
  Pop $0
  SetCtlColors $0 5352BD transparent
  nsDialogs::Show
FunctionEnd

Function SynapseReleasePage
  IfSilent 0 +2
    Abort
  nsDialogs::Create 1018
  Pop $SynapseReleaseDialog
  ${If} $SynapseReleaseDialog == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 18u "SYNAPSE  /  WHAT'S NEW"
  Pop $0
  SetCtlColors $0 8141D9 transparent
  ${NSD_CreateLabel} 0 24u 100% 27u "Your AI workspace, with smarter installation and recovery."
  Pop $0
  ${NSD_CreateLabel} 0 62u 100% 14u "* Repair and update an existing installation"
  Pop $0
  ${NSD_CreateLabel} 0 82u 100% 14u "* Connect devices through your Synapse account"
  Pop $0
  ${NSD_CreateLabel} 0 102u 100% 14u "* Keep projects and local credentials in place"
  Pop $0
  ${NSD_CreateLabel} 0 122u 100% 14u "* Diagnose account service and daemon connectivity"
  Pop $0
  ${NSD_CreateLabel} 0 148u 100% 25u "Continue to choose your AI bundles and start installation."
  Pop $0
  SetCtlColors $0 5352BD transparent
  nsDialogs::Show
FunctionEnd
Var BundleDialog
Var BundleResearchHandle
Var BundleFactoryHandle
Var BundleRescueHandle
Var BundleHarvestHandle
Var BundleImageStudioHandle
Var BundleResearchState
Var BundleFactoryState
Var BundleRescueState
Var BundleHarvestState
Var BundleImageStudioState

Page custom SynapseBundlesPageCreate SynapseBundlesPageLeave

Function SynapseBundlesPageCreate
  ${If} $RepairMode == 1
    Abort ; previous selections are intentionally preserved on repair
  ${EndIf}
  nsDialogs::Create 1018
  Pop $BundleDialog
  ${If} $BundleDialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 26u "Choose AI bundles to bootstrap with Synapse on first launch. These packs add AI roles, quick actions, personalities, and reusable factory assets."
  Pop $0

  ${NSD_CreateCheckbox} 0 34u 100% 10u "Deep Research Council"
  Pop $BundleResearchHandle
  ${If} $BundleResearchState == 1
    ${NSD_Check} $BundleResearchHandle
  ${EndIf}

  ${NSD_CreateCheckbox} 0 50u 100% 10u "Fullstack App Factory"
  Pop $BundleFactoryHandle
  ${If} $BundleFactoryState == 1
    ${NSD_Check} $BundleFactoryHandle
  ${EndIf}

  ${NSD_CreateCheckbox} 0 66u 100% 10u "Repo Rescue Lab"
  Pop $BundleRescueHandle
  ${If} $BundleRescueState == 1
    ${NSD_Check} $BundleRescueHandle
  ${EndIf}

  ${NSD_CreateCheckbox} 0 82u 100% 10u "Parallel Harvest + Bakeoff"
  Pop $BundleHarvestHandle
  ${If} $BundleHarvestState == 1
    ${NSD_Check} $BundleHarvestHandle
  ${EndIf}

  ${NSD_CreateCheckbox} 0 98u 100% 10u "Synapse Image Studio — by The WhatIf Company (AI image generation + editing)"
  Pop $BundleImageStudioHandle
  ${If} $BundleImageStudioState == 1
    ${NSD_Check} $BundleImageStudioHandle
  ${EndIf}

  ${NSD_CreateLabel} 0 118u 100% 22u "Image Studio is a first-party Synapse component and is selected by default. You can uninstall/reinstall it later from Discover."
  Pop $0

  nsDialogs::Show
FunctionEnd

Function SynapseBundlesPageLeave
  ${NSD_GetState} $BundleResearchHandle $BundleResearchState
  ${NSD_GetState} $BundleFactoryHandle $BundleFactoryState
  ${NSD_GetState} $BundleRescueHandle $BundleRescueState
  ${NSD_GetState} $BundleHarvestHandle $BundleHarvestState
  ${NSD_GetState} $BundleImageStudioHandle $BundleImageStudioState
FunctionEnd



!macro customInstall
  ${If} $RepairMode == 1
    Goto synapse_bundle_config_done
  ${EndIf}
  CreateDirectory "$APPDATA\Synapse"
  FileOpen $0 "$APPDATA\Synapse\bootstrap-ai-bundles.json" w
  FileWrite $0 "{$\r$\n  $\"bundle_ids$\": ["
  StrCpy $R9 1

  ${If} $BundleResearchState == 1
    ${If} $R9 == 1
      StrCpy $R9 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"deep-research-council$\""
  ${EndIf}

  ${If} $BundleFactoryState == 1
    ${If} $R9 == 1
      StrCpy $R9 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"fullstack-app-factory$\""
  ${EndIf}

  ${If} $BundleRescueState == 1
    ${If} $R9 == 1
      StrCpy $R9 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"repo-rescue-lab$\""
  ${EndIf}

  ${If} $BundleHarvestState == 1
    ${If} $R9 == 1
      StrCpy $R9 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"parallel-harvest-bakeoff$\""
  ${EndIf}

  FileWrite $0 "]$\r$\n}$\r$\n"
  FileClose $0

  FileOpen $1 "$APPDATA\Synapse\bootstrap-optional-tools.json" w
  ${If} $BundleImageStudioState == 1
    FileWrite $1 "{$\r$\n  $\"install_tool_ids$\": [$\"synapse-image-studio$\"],$\r$\n  $\"uninstall_tool_ids$\": []$\r$\n}$\r$\n"
  ${Else}
    FileWrite $1 "{$\r$\n  $\"install_tool_ids$\": [],$\r$\n  $\"uninstall_tool_ids$\": [$\"synapse-image-studio$\"]$\r$\n}$\r$\n"
  ${EndIf}
  FileClose $1
  synapse_bundle_config_done:
  ; Post-install diagnostics are non-destructive and write a report for support.
  IfFileExists "$INSTDIR\resources\repair\synapse-repair-check.ps1" 0 synapse_repair_done
  ${If} $RepairMode == 1
    nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\resources\repair\synapse-repair-check.ps1" -InstallDir "$INSTDIR" -Repair'
  ${Else}
    nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\resources\repair\synapse-repair-check.ps1" -InstallDir "$INSTDIR"'
  ${EndIf}
  synapse_repair_done:
!macroend
