!include "LogicLib.nsh"
!include "nsDialogs.nsh"

Var BundleDialog
Var BundleResearchHandle
Var BundleFactoryHandle
Var BundleRescueHandle
Var BundleHarvestHandle
Var BundleResearchState
Var BundleFactoryState
Var BundleRescueState
Var BundleHarvestState
Var BundleBootstrapFile
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

  ${NSD_CreateLabel} 0 102u 100% 20u "Cloudtap is still included with Synapse. These checkboxes only control the AI-first bundle bootstrap file used on first launch."
  Pop $0

  nsDialogs::Show
FunctionEnd

Function SynapseBundlesPageLeave
  ${NSD_GetState} $BundleResearchHandle $BundleResearchState
  ${NSD_GetState} $BundleFactoryHandle $BundleFactoryState
  ${NSD_GetState} $BundleRescueHandle $BundleRescueState
  ${NSD_GetState} $BundleHarvestHandle $BundleHarvestState
FunctionEnd

!macro customInit
  StrCpy $BundleResearchState 1
  StrCpy $BundleFactoryState 1
  StrCpy $BundleRescueState 1
  StrCpy $BundleHarvestState 0
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
!macroend
