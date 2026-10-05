!include "LogicLib.nsh"
!include "nsDialogs.nsh"

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
Var BundleBootstrapFile
Var OptionalToolsBootstrapFile
Var BundleFirstItem

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
  StrCpy $BundleBootstrapFile "$APPDATA\Synapse\bootstrap-ai-bundles.json"
  CreateDirectory "$APPDATA\Synapse"
  FileOpen $0 $BundleBootstrapFile w
  FileWrite $0 "{$\r$\n  $\"bundle_ids$\": ["
  StrCpy $BundleFirstItem 1

  ${If} $BundleResearchState == 1
    ${If} $BundleFirstItem == 1
      StrCpy $BundleFirstItem 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"deep-research-council$\""
  ${EndIf}

  ${If} $BundleFactoryState == 1
    ${If} $BundleFirstItem == 1
      StrCpy $BundleFirstItem 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"fullstack-app-factory$\""
  ${EndIf}

  ${If} $BundleRescueState == 1
    ${If} $BundleFirstItem == 1
      StrCpy $BundleFirstItem 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"repo-rescue-lab$\""
  ${EndIf}

  ${If} $BundleHarvestState == 1
    ${If} $BundleFirstItem == 1
      StrCpy $BundleFirstItem 0
    ${Else}
      FileWrite $0 ", "
    ${EndIf}
    FileWrite $0 "$\"parallel-harvest-bakeoff$\""
  ${EndIf}

  FileWrite $0 "]$\r$\n}$\r$\n"
  FileClose $0

  StrCpy $OptionalToolsBootstrapFile "$APPDATA\Synapse\bootstrap-optional-tools.json"
  FileOpen $1 $OptionalToolsBootstrapFile w
  ${If} $BundleImageStudioState == 1
    FileWrite $1 "{$\r$\n  $\"install_tool_ids$\": [$\"synapse-image-studio$\"],$\r$\n  $\"uninstall_tool_ids$\": []$\r$\n}$\r$\n"
  ${Else}
    FileWrite $1 "{$\r$\n  $\"install_tool_ids$\": [],$\r$\n  $\"uninstall_tool_ids$\": [$\"synapse-image-studio$\"]$\r$\n}$\r$\n"
  ${EndIf}
  FileClose $1
!macroend
