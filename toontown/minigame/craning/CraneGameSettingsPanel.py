from direct.gui.DirectGui import *
from panda3d.core import *
from toontown.toonbase import ToontownGlobals
from toontown.toonbase import TTLocalizer

class CraneGameSettingsPanel(DirectFrame):
    def __init__(self, gameTitle, doneEvent):
        DirectFrame.__init__(self, relief=None,
                           geom=DGG.getDefaultDialogGeom(),
                           geom_color=ToontownGlobals.GlobalDialogColor[:3] + (0.8,),
                           geom_scale=(1.75, 1, 1.25),
                           pos=(0, 0, 0))

        self.initialiseoptions(CraneGameSettingsPanel)
        self.doneEvent = doneEvent
        self.gameTitle = gameTitle

        self.load()

    def load(self):
        # Create the main panel frame
        self.frame = DirectFrame(parent=self,
                               relief=None,
                               pos=(0, 0, 0),
                               scale=1.0)

        # Create title text
        self.titleText = DirectLabel(parent=self.frame,
                                   relief=None,
                                   text=self.gameTitle,
                                   text_scale=0.1,
                                   text_fg=(0.2, 0.2, 0.2, 1),
                                   pos=(0, 0, 0.6))

    def cleanup(self):
        if hasattr(self, 'frame') and self.frame is not None:
            self.titleText.destroy()
            self.titleText.removeNode()
            self.frame.destroy()
            self.frame.removeNode()
            self.titleText = None
            self.frame = None

        # Call parent's destroy
        DirectFrame.destroy(self)
