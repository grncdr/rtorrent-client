Name "wrTc"
InstallDir "$PROGRAMFILES\wrtc"

!include "MUI.nsh"
!insertmacro MUI_PAGE_DIRECTORY

Page custom StartMenuGroupSelect "" ": Start Menu Folder"
Function StartMenuGroupSelect
	Push $R1

	StartMenu::Select /checknoshortcuts "Don't create a start menu folder" /autoadd /lastused $R0 "wrTc - wxPython rTorrent Client"
	Pop $R1

	StrCmp $R1 "success" success
	StrCmp $R1 "cancel" done
		; error
		MessageBox MB_OK $R1
		StrCpy $R0 "wrTc - wxPython rTorrent Client" # use default
		Return
	success:
	Pop $R0

	done:
	Pop $R1
FunctionEnd

!insertmacro MUI_PAGE_INSTFILES

Section 
	SetOutPath $INSTDIR
	File /r dist\*
SectionEnd

Section
	# this part is only necessary if you used /checknoshortcuts
	StrCpy $R1 $R0 1
	StrCmp $R1 ">" skip

		CreateDirectory $SMPROGRAMS\$R0
		CreateShortCut $SMPROGRAMS\$R0\wrTc.lnk $INSTDIR\wrtc.exe

		SetShellVarContext All
		CreateDirectory $SMPROGRAMS\$R0
		CreateShortCut "$SMPROGRAMS\$R0\wrTc.lnk" $INSTDIR\wrtc.exe

	skip:
SectionEnd

OutFile "wrtc-installer.exe"
