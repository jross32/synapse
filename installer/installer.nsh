!include "LogicLib.nsh"
!include "nsDialogs.nsh"

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
  ${NSD_CreateLabel} 0 0 100% 48u "Synapse is already installed at:$\\r$\\n$ExistingInstallPath$\\r$\\n$\\r$\\nYou can repair missing files and update Synapse without deleting your projects, account settings, or local data."
  Pop $ExistingInstallLabel
  ${NSD_CreateCheckbox} 0 58u 100% 22u "Repair / update existing Synapse installation (recommended)"
  Pop $ExistingInstallChoice
  ${NSD_Check} $ExistingInstallChoice
  ${NSD_CreateLabel} 0 88u 100% 38u "If you uncheck repair, Setup will continue as a regular installation. Existing Synapse app files are still replaced."
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

!macro customInit
  StrCpy $BundleResearchState 1
  StrCpy $BundleFactoryState 1
  StrCpy $BundleRescueState 1
  StrCpy $BundleHarvestState 0
  StrCpy $BundleImageStudioState 1
!macroend

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
