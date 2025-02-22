from direct.gui.DirectGui import *
from panda3d.core import *
from toontown.toonbase import ToontownGlobals
from toontown.toonbase import TTLocalizer

class CraneGameSettingsPanel(DirectFrame):
    def __init__(self, gameTitle, doneEvent):
        DirectFrame.__init__(self)
        self.initialiseoptions(self)
        self.doneEvent = doneEvent
        self.gameTitle = gameTitle

        self.load()

    def load(self):
        self.frame = DirectFrame(
            self, relief=None,
            geom=DGG.getDefaultDialogGeom(),
            geom_color=ToontownGlobals.GlobalDialogColor,
            geom_scale=(1.75, 1, 1.25),
            pos=(0, 0, 0)
        )

        # Create title text
        self.titleText = DirectLabel(
            parent=self,
            relief=None,
            text=self.gameTitle,
            text_scale=0.1,
            text_fg=(0.2, 0.2, 0.2, 1),
            pos=(0, 0, 0.6)
        )

    def cleanup(self):
        self.titleText.destroy()
        self.titleText.removeNode()
        self.destroy()
        self.removeNode()
        self.titleText = None
