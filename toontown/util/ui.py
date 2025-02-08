from direct.gui import DirectGuiGlobals
from direct.gui.DirectScrolledList import DirectScrolledList
from panda3d.core import PGButton, MouseButton


def make_dsl_scrollable(dsl: DirectScrolledList):
    affected_ui = [dsl.itemFrame, dsl]
    for item in dsl['items']:
        if not isinstance(item, str):
            affected_ui.append(item)

    WHEELUP = PGButton.getReleasePrefix() + MouseButton.wheelUp().getName() + '-'
    WHEELDOWN = PGButton.getReleasePrefix() + MouseButton.wheelDown().getName() + '-'
    for ui in affected_ui:
        ui.bind(WHEELUP, lambda *_: dsl.scrollTo(dsl.index - 1))
        ui.bind(WHEELDOWN, lambda *_: dsl.scrollTo(dsl.index + 1))

