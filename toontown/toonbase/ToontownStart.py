import sys

from panda3d.core import *

if __debug__:
    if len(sys.argv) == 2 and sys.argv[1] == '--dummy':
        loadPrcFile('config/common.prc')
        loadPrcFile('config/development.prc')

        # The VirtualFileSystem, which has already initialized, doesn't see the mount
        # directives in the config(s) yet. We have to force it to load those manually:
        vfs = VirtualFileSystem.getGlobalPtr()
        mounts = ConfigVariableList('vfs-mount')
        for mount in mounts:
            mountFile, mountPoint = (mount.split(' ', 2) + [None, None, None])[:2]
            vfs.mount(Filename(mountFile), Filename(mountPoint), 0)

import builtins

class game:
    name = 'toontown'
    process = 'client'


builtins.game = game()
import time
import os
import random
import builtins
try:
    launcher
except:
    from toontown.launcher.TTOffDummyLauncher import TTOffDummyLauncher
    launcher = TTOffDummyLauncher()
    builtins.launcher = launcher

launcher.setRegistry('EXIT_PAGE', 'normal')
pollingDelay = 0.5
print('ToontownStart: Polling for game2 to finish...')
while not launcher.getGame2Done():
    time.sleep(pollingDelay)

print('ToontownStart: Game2 is finished.')
print('ToontownStart: Starting the game.')
if launcher.isDummy():
    http = HTTPClient()
else:
    http = launcher.http
tempLoader = Loader()
backgroundNode = tempLoader.loadSync(Filename('phase_3/models/gui/loading-background'))
from direct.gui import DirectGuiGlobals
print('ToontownStart: setting default font')
from . import ToontownGlobals
DirectGuiGlobals.setDefaultFontFunc(ToontownGlobals.getInterfaceFont)
launcher.setPandaErrorCode(7)
from . import ToonBase
ToonBase.ToonBase()
if base.win == None:
    print('Unable to open window; aborting.')
    sys.exit()
launcher.setPandaErrorCode(0)
launcher.setPandaWindowOpen()
ConfigVariableDouble('decompressor-step-time').setValue(0.01)
ConfigVariableDouble('extractor-step-time').setValue(0.01)
backgroundNodePath = aspect2d.attachNewNode(backgroundNode, 0)
backgroundNodePath.setPos(0.0, 0.0, 0.0)
backgroundNodePath.setScale(aspect2d, VBase3(1.33, 1, 1))
backgroundNodePath.find('**/fg').setBin('fixed', 20)
backgroundNodePath.find('**/bg').setBin('fixed', 10)
backgroundNodePath.find('**/bg').setScale(aspect2d, VBase3(base.getAspectRatio(), 1, 1))
base.graphicsEngine.renderFrame()
DirectGuiGlobals.setDefaultRolloverSound(base.loader.loadSfx('phase_3/audio/sfx/GUI_rollover.ogg'))
DirectGuiGlobals.setDefaultClickSound(base.loader.loadSfx('phase_3/audio/sfx/GUI_create_toon_fwd.ogg'))
DirectGuiGlobals.setDefaultDialogGeom(loader.loadModel('phase_3/models/gui/dialog_box_gui'))
from . import TTLocalizer
from otp.otpbase import OTPGlobals
OTPGlobals.setDefaultProductPrefix(TTLocalizer.ProductPrefix)
if base.musicManagerIsValid:
    music = base.musicManager.getSound('phase_3/audio/bgm/tt_theme.ogg')
    if music:
        music.setLoop(1)
        music.setVolume(base.settings.get("music-volume") ** 2)
        music.play()
    print('ToontownStart: Loading default gui sounds')
    DirectGuiGlobals.setDefaultRolloverSound(base.loader.loadSfx('phase_3/audio/sfx/GUI_rollover.ogg'))
    DirectGuiGlobals.setDefaultClickSound(base.loader.loadSfx('phase_3/audio/sfx/GUI_create_toon_fwd.ogg'))
else:
    music = None
from panda3d.core import TextNode
font = loader.loadFont('phase_3/models/fonts/ImpressBT.ttf')
TextNode.setDefaultFont(font)
from . import ToontownLoader
from direct.gui.DirectGui import *
serverVersion = base.config.GetString('server-version', 'no_version_set')
print('ToontownStart: serverVersion: ', serverVersion)
version = OnscreenText(serverVersion, parent=base.a2dBottomLeft, pos=(0.033, 0.025), scale=0.06, fg=Vec4(0, 0, 1, 0.6), align=TextNode.ALeft)
loader.beginBulkLoad('init', TTLocalizer.LoaderLabel, 138, 0, TTLocalizer.TIP_NONE)
from .ToonBaseGlobal import *
from direct.showbase.MessengerGlobal import *
from toontown.distributed import ToontownClientRepository
cr = ToontownClientRepository.ToontownClientRepository(serverVersion, launcher)
cr.music = music
del music
base.initNametagGlobals()
base.cr = cr
loader.endBulkLoad('init')
from otp.friends import FriendManager
from otp.distributed.OtpDoGlobals import *
cr.generateGlobalObject(OTP_DO_ID_FRIEND_MANAGER, 'FriendManager')

from otp.otpgui import OTPDialog
from otp.otpbase.OTPLocalizer import CREnterUsername, CRInvalidUsername, CREmptyUsername, CRLoadingGameServices, CRSpecifyServerSelection, CRSingleplayer, CRPublicServer

def cleanup(dialogClass):
    dialogClass.cleanup()
    del dialogClass

def clearText():
    entry.enterText('')

def determineAuthenticity(textEntered):
    username = textEntered
    if not username:
        askForUsername['text'] = CREmptyUsername
    elif username in ['dev', 'NO PLAYTOKEN']:
        askForUsername['text'] = CRInvalidUsername
    else:
        base.cr.playToken = username
        askServerPreference()

dialogClass = OTPGlobals.getGlobalDialogClass()
askForUsername = dialogClass(message=CREnterUsername, style=OTPDialog.NoButtons,
                             doneEvent='cleanup', text_wordwrap=16, midPad=0.2, extraArgs=['askForUsername'])
base.accept('cleanup', cleanup, extraArgs=[askForUsername])

entry = DirectEntry(parent=askForUsername , text="", scale=0.0625, pos=(-0.3, 0, -0.19), command=determineAuthenticity,
                    cursorKeys=1, obscured=1, initialText="Username", numLines=1, focus=1, focusInCommand=clearText)

askForUsername.show()
base.accept('determineAuthenticity', determineAuthenticity)

def decision(buttonValue = None):
    if buttonValue == -1: # buttonValue returning -1 will connect us to the public seever.
        base.startShow(cr, config.ConfigVariableString('public-server-ip', '').getValue())
    else: # buttonValue returning any other value will startup the Singleplayer server.
        # Start DedicatedServer
        builtins.gameServicesDialog = dialogClass(message = CRLoadingGameServices)
        builtins.gameServicesDialog.show()

        from toontown.toonbase.DedicatedServer import DedicatedServer
        builtins.clientServer = DedicatedServer(localServer=True)
        builtins.clientServer.start()

        def localServerReady():
            builtins.gameServicesDialog.cleanup()
            del builtins.gameServicesDialog
            base.startShow(cr)
        base.accept('localServerReady', localServerReady)

def askServerPreference():
    if not config.ConfigVariableBool('local-multiplayer', False).getValue():
        from otp.otpgui import OTPDialog

        askServerSpecification = dialogClass(message=CRSpecifyServerSelection, style=OTPDialog.TwoChoiceCustom,
                                             okButtonText=CRSingleplayer, cancelButtonText=CRPublicServer, command=decision,
                                             doneEvent='cleanup', text_wordwrap=16, buttonPadSF=5)
        askServerSpecification.show()
        base.accept('cleanup', cleanup, extraArgs=[askServerSpecification])
    else:
        if not launcher.isDummy():
            base.startShow(cr, launcher.getGameServer())
        else:
            base.startShow(cr)


backgroundNodePath.reparentTo(hidden)
backgroundNodePath.removeNode()
del backgroundNodePath
del backgroundNode
del tempLoader
version.cleanup()
del version
base.loader = base.loader
builtins.loader = base.loader
autoRun = ConfigVariableBool('toontown-auto-run', 1)
if autoRun and launcher.isDummy() and (not Thread.isTrueThreads() or __name__ == '__main__'):
    try:
        base.run()
    except SystemExit:
        raise
    except:
        from otp.otpbase import PythonUtil
        print(PythonUtil.describeException())
        raise