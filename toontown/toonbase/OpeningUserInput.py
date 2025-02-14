import builtins
from direct.showbase.DirectObject import DirectObject
from direct.gui.DirectGui import *
from otp.otpbase import OTPGlobals
from otp.otpgui import OTPDialog
from otp.otpbase.OTPLocalizer import CREnterUsername, CRInvalidUsername, CREmptyUsername, CRLoadingGameServices, CRSpecifyServerSelection, CRSingleplayer, CRPublicServer

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

    def determineAuthenticity(self, textEntered):
        username = textEntered
        if not username:
            self.askForUsername['text'] = CREmptyUsername
        elif username in ['dev', 'NO PLAYTOKEN']:
            self.askForUsername['text'] = CRInvalidUsername
        else:
            self.cr.playToken = username
            self.askServerPreference()

    def askForPlaytoken(self):
        self.askForUsername = self.dialogClass(message=CREnterUsername, style=OTPDialog.NoButtons,
                                     doneEvent='cleanup', text_wordwrap=16, midPad=0.2, extraArgs=['askForUsername'])
        self.accept('cleanup', self.cleanup, extraArgs=[self.askForUsername])

        self.entry = DirectEntry(parent=self.askForUsername , text="", scale=0.0625, pos=(-0.3, 0, -0.19), command=self.determineAuthenticity,
                            cursorKeys=1, obscured=1, initialText="Username", numLines=1, focus=1, focusInCommand=self.clearText)

        self.askForUsername.show()
        self.accept('determineAuthenticity', self.determineAuthenticity)

    def decision(self, buttonValue = None):
        if buttonValue == -1: # buttonValue returning -1 will connect us to the public seever.
            base.startShow(self.cr, config.ConfigVariableString('public-server-ip', '').getValue())
        else: # buttonValue returning any other value will startup the Singleplayer server.
            # Start DedicatedServer
            builtins.gameServicesDialog = self.dialogClass(message = CRLoadingGameServices)
            builtins.gameServicesDialog.show()

            from toontown.toonbase.DedicatedServer import DedicatedServer
            builtins.clientServer = DedicatedServer(localServer=True)
            builtins.clientServer.start()

            def localServerReady():
                builtins.gameServicesDialog.cleanup()
                del builtins.gameServicesDialog
                base.startShow(self.cr)
            self.accept('localServerReady', localServerReady)

    def askServerPreference(self):
        if not config.ConfigVariableBool('local-multiplayer', False).getValue():
            from otp.otpgui import OTPDialog

            self.askServerSpecification = self.dialogClass(message=CRSpecifyServerSelection, style=OTPDialog.TwoChoiceCustom,
                                                 okButtonText=CRSingleplayer, cancelButtonText=CRPublicServer, command=self.decision,
                                                 doneEvent='cleanup', text_wordwrap=16, buttonPadSF=5)
            self.askServerSpecification.show()
            self.accept('cleanup', self.cleanup, extraArgs=[self.askServerSpecification])
        else:
            if not self.launcher.isDummy():
                base.startShow(self.cr, self.launcher.getGameServer())
            else:
                base.startShow(self.cr)