from direct.gui.DirectButton import DirectButton
from direct.gui.DirectLabel import DirectLabel
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

from toontown.toonbase import ToontownGlobals


class InQueuePanel(DirectLabel):

    FRAME_WIDTH = 0.7
    FRAME_HEIGHT = 0.2
    FRAME_COLOR = (0.1, 0.1, 0.1, 0.9)

    TEXT_SCALE = .05
    TEXT_POS = (-.3, 0.01)
    TEXT_COLOR = (1, 1, 1, 1)
    TEXT_ALIGN = TextNode.ALeft

    def __init__(self, **kw):
        super().__init__(**kw)
        self.initialiseoptions(InQueuePanel)
        self.setText('In queue...\n0:00')
        self.close_button = DirectButton(parent=self, frameColor=(.9, 0.1, 0.1, 1), scale=(.75, 1, .35), pos=(0.268, 0, 0.059), command=self.__handle_exit_queue)
        self.x_label = OnscreenText(parent=self, align=TextNode.ACenter, text='Cancel', fg=(1, 1, 1, 1), scale=.04, pos=(.268, .050), mayChange=True, font=ToontownGlobals.getCompetitionFont())
        self.extra_info = OnscreenText(parent=self, align=TextNode.ACenter, text='#1/1', fg=(.4, .4, .4, 1), scale=.05, pos=(.03, -.02), mayChange=True, font=ToontownGlobals.getCompetitionFont())

    def __handle_exit_queue(self):
        pass

    # Call to reset all options to default, ideally only need to do this once
    def set_default_options(self):

        # Setup the base frame
        self['frameSize'] = (-self.FRAME_WIDTH/2, self.FRAME_WIDTH/2, -self.FRAME_HEIGHT/2, self.FRAME_HEIGHT/2)
        self['frameColor'] = self.FRAME_COLOR

        # Setup the text
        self['text_scale'] = self.TEXT_SCALE
        self['text_pos'] = self.TEXT_POS
        self['text_fg'] = self.TEXT_COLOR
        self['text_align'] = self.TEXT_ALIGN
        self['text_font'] = ToontownGlobals.getCompetitionFont()

    # Updates the time to display. Time parameter is seconds.
    def update_time(self, time: int):
        min = time // 60
        sec = time - 60 * min
        period = '.' * (time % 4)
        self.setText(f"In queue{period}\n{min}:{sec:02}")

    def update_queue_status(self, place: int, total: int):
        self.extra_info['text'] = f"#{place}/{total}"

    def bind_cancel(self, func):
        self.close_button['command'] = func

    def destroy(self):
        self.ignoreAll()
        super().destroy()
