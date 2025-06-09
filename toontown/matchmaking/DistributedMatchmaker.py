from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobal import DistributedObjectGlobal
from direct.gui.DirectLabel import DirectLabel

from toontown.toonbase import ToontownGlobals


class DistributedMatchmaker(DistributedObjectGlobal):
    neverDisable = 1

    Notify = DirectNotifyGlobal.directNotify.newCategory('DistributedMatchmaker')

    def __init__(self, cr):
        super().__init__(cr)
        self.text_update: DirectLabel | None = None
        self.Notify.setDebug(True)

    def announceGenerate(self):
        super().announceGenerate()
        self.Notify.debug('Generated!')
        self.text_update = DirectLabel(parent=base.a2dBottomCenter, pos=(0, 0, .55), text='', textMayChange=1, text_scale=.25,
                    text_shadow=(0, 0, 0, 1), text_fg=(.15, .9, .15, 1), text_font=ToontownGlobals.getCompetitionFont())

    def delete(self):
        super().delete()
        self.Notify.debug('Deleting!')
        if self.text_update is not None:
            self.text_update.destroy()
            self.text_update = None

    def __updateText(self, text: str, color: tuple[float, float, float, float]):
        if self.text_update is not None:
            self.text_update['text'] = text
            self.text_update['text_fg'] = color

    """
    Astron methods
    """

    def setMinigameZone(self, minigameZone, minigameGameId):

        self.Notify.debug(f"Found match for zone {minigameZone} with game {minigameGameId}")
        playground = base.cr.playGame.getPlace()

        # First, freeze the toon. We need to prevent softlocks.
        playground.setState('stopped')

        def __updateText(i):

            if i <= -2:
                self.__updateText('', color=(.6, .6, .6, 1))
                self.text_update.hide()
                return

            self.text_update.show()
            if i <= 0:
                self.__updateText('Have fun!', color=(.15, .9, .15, 1))
            else:
                self.__updateText(f"Match found!\nLeaving in {i}...", color=(.6, .6, .6, 1))
            taskMgr.remove(self.uniqueName('teleportToMinigameTextUpdate'))
            taskMgr.doMethodLater(1, __updateText, self.uniqueName('teleportToMinigameTextUpdate'), extraArgs=[i-1])

        def __teleportToMinigame(_=None):
            doneStatus = {
                'loader': 'minigame',
                'where': 'minigame',
                'hoodId': playground.loader.hood.id,
                'zoneId': minigameZone,
                'shardId': None,
                'minigameId': minigameGameId,
                'avId': None,
            }
            playground.doneStatus = doneStatus
            playground.fsm.forceTransition('teleportOut', [doneStatus])
            base.render.setColorScale(1, 1, 1, 1)

        # Next, in 3 seconds we should teleport to where we need to go.
        taskMgr.doMethodLater(5, __teleportToMinigame, self.uniqueName('teleportToMinigame'))
        __updateText(5)
        base.render.setColorScale(.3, .3, .3, 1)
        base.playSfx(loader.loadSfx('phase_11/audio/sfx/LB_toonup.ogg'))