import builtins
import os
import re
from direct.showbase.DirectObject import DirectObject
from direct.gui.DirectGui import *
from otp.otpbase import OTPGlobals
from otp.otpgui import OTPDialog
from otp.otpbase.OTPLocalizer import (
    CREnterUsername,
    CRInvalidUsername,
    CREmptyUsername,
    CREnterGameserver,
    CREmptyGameserver,
    CRLoadingGameServices,
    CRSpecifyServerSelection,
    CRSingleplayer,
    CRLocalMultiplayer,
    CRPublicServer
)

class OpeningUserInput(DirectObject):
    def __init__(self, cr, launcher):
        self.cr = cr
        self.launcher = launcher
        self.dialogClass = OTPGlobals.getGlobalDialogClass()

        self.askForPlaytoken()

    def cleanup(dialogClass):
        dialogClass.cleanup()
        del dialogClass

    def clearText(self):
        self.entry.enterText('')

    def determineUsernameAuthenticity(self, textEntered):
        username = textEntered
        if not username:
            self.askForUsername['text'] = CREmptyUsername
        elif username in ['dev', 'NO PLAYTOKEN']:
            self.askForUsername['text'] = CRInvalidUsername
        else:
            self.cr.playToken = username
            self.askServerPreference()

    def specifyGameserver(self, textEntered):
        gameserver = textEntered
        if not gameserver:
            base.startShow(self.cr, '127.0.0.1:7198')
        else:
            base.startShow(self.cr, gameserver)

    def askForPlaytoken(self):

        self.askForUsername = self.dialogClass(message=CREnterUsername, style=OTPDialog.NoButtons,
                                     doneEvent='cleanup', text_wordwrap=16, midPad=0.2, extraArgs=['askForUsername'])
        self.accept('cleanup', self.cleanup, extraArgs=[self.askForUsername])

        self.entry = DirectEntry(parent=self.askForUsername , text="", scale=0.0625, pos=(-0.3, 0, -0.19), command=self.determineUsernameAuthenticity,
                                 cursorKeys=1, obscured=1, initialText="Username", numLines=1, focus=1, focusInCommand=self.clearText)

        self.askForUsername.show()

        # Is an environment variable already set? Skip the process if so.
        token = os.getenv('PLAYTOKEN')
        os.unsetenv('PLAYTOKEN')  # Get rid of it after one attempt at this.
        if token is not None:
            self.entry.setText(token)
            self.determineUsernameAuthenticity(token)

    def localMultiplayerScreen(self):
        self.askForGameserver = self.dialogClass(message=CREnterGameserver, style=OTPDialog.NoButtons,
                                     doneEvent='cleanup', text_wordwrap=20, midPad=0.2, extraArgs=['askForGameserver'])
        self.accept('cleanup', self.cleanup, extraArgs=[self.askForGameserver])

        self.entry = DirectEntry(parent=self.askForGameserver , text="", scale=0.075, pos=(-0.6, 0, -0.3), command=self.specifyGameserver,
                                 width=16, cursorKeys=1, obscured=0, initialText="Gameserver", numLines=1, focus=1, focusInCommand=self.clearText)

        self.askForGameserver.show()

    def publicServerScreen(self):
        base.startShow(self.cr, config.ConfigVariableString('public-server-ip', '').getValue())

    def singlePlayerScreen(self):
        # Start DedicatedServer
        builtins.gameServicesDialog = self.dialogClass(message=CRLoadingGameServices)
        builtins.gameServicesDialog.show()

        from toontown.toonbase.DedicatedServer import DedicatedServer
        builtins.clientServer = DedicatedServer(localServer=True)
        builtins.clientServer.start()

        def localServerReady():
            builtins.gameServicesDialog.cleanup()
            del builtins.gameServicesDialog
            base.startShow(self.cr)

        self.accept('localServerReady', localServerReady)

    def decision(self, buttonValue = None):
        if buttonValue == -1: # buttonValue returning -1 will connect us to the Local Multiplayer server.
            self.localMultiplayerScreen()
        elif buttonValue == 0: # buttonValue returning 0 will connect us to the public server.
            self.publicServerScreen()
        elif buttonValue == 1: # buttonValue returning 1 will startup the Singleplayer server.
            self.singlePlayerScreen()

    def askServerPreference(self):

        # Is an env var set?
        gameserver = os.getenv('GAMESERVER')
        if gameserver is not None:
            base.startShow(self.cr, gameserver)
            return

        if not config.ConfigVariableBool('local-multiplayer', False).getValue():
            self.askServerSpecification = self.dialogClass(message=CRSpecifyServerSelection, style=OTPDialog.ThreeChoiceCustom,
                                                           yesButtonText=CRSingleplayer, noButtonText=CRPublicServer, cancelButtonText=CRLocalMultiplayer,
                                                           command=self.decision, doneEvent='cleanup', text_wordwrap=20, buttonPadSF=5)
            self.askServerSpecification.show()
            self.accept('cleanup', self.cleanup, extraArgs=[self.askServerSpecification])
            return

        # Default behavior
        if not self.launcher.isDummy():
            base.startShow(self.cr, self.launcher.getGameServer())
        else:
            base.startShow(self.cr)