import time

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobal import DistributedObjectGlobal
from direct.gui.DirectLabel import DirectLabel
from direct.task import Task

from toontown.matchmaking.in_queue_panel import InQueuePanel
from toontown.toonbase import ToontownGlobals


class DistributedMatchmaker(DistributedObjectGlobal):
    neverDisable = 1

    Notify = DirectNotifyGlobal.directNotify.newCategory('DistributedMatchmaker')

    def __init__(self, cr):
        super().__init__(cr)
        self.queue_panel: InQueuePanel | None = None
        self.text_update: DirectLabel | None = None
        self.startedQueueAt = 0

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
        self.__cleanupQueuePanel()

    def __updateText(self, text: str, color: tuple[float, float, float, float]):
        if self.text_update is not None:
            self.text_update['text'] = text
            self.text_update['text_fg'] = color

    def __update_queue_panel(self, _time: int = 0, queuePos: int = 0, totalQueueing: int = 0):
        if self.queue_panel is None:
            self.__renderQueuePanel()
        self.queue_panel.update_time(_time)
        if queuePos != 0 and totalQueueing != 0:
            self.queue_panel.update_queue_status(queuePos, totalQueueing)

    def __renderQueuePanel(self):
        self.__cleanupQueuePanel()
        self.queue_panel = InQueuePanel(parent=base.a2dTopRight, pos=(-.85, 0, -.15))
        self.queue_panel.set_default_options()
        self.queue_panel.bind_cancel(self.__handle_cancel_queue)
        self.startedQueueAt = time.time()
        taskMgr.add(self.__update_time_only, 'queue-timer-update-task')

    def __cleanupQueuePanel(self):
        if self.queue_panel is None:
            return
        taskMgr.remove('queue-timer-update-task')
        self.queue_panel.destroy()
        self.queue_panel = None

    def __handle_cancel_queue(self):
        self.d_requestQueueState(False)

    def __update_time_only(self, task: Task.Task):
        task.delayTime = 1
        self.__update_queue_panel(_time=int(time.time() - self.startedQueueAt))
        return task.again

    """
    Astron methods
    """

    def d_requestQueueState(self, flag: bool):
        """
        Alerts the server that we want a specific queue state. If flag is true, we want to start queueing. If flag
        is False, we want to stop queueing.
        """
        self.sendUpdate('requestQueueState', [flag])

    def setMatchmakingStatus(self, position: int, total: int):
        """
        Called from the matchmaker on the AI. Tells us information about our spot in queue.
        """
        # If we send 0s for everything, this is the server telling us we are no longer in queue.
        if sum([position, total]) == 0:
            self.__cleanupQueuePanel()
            self.startedQueueAt = 0
            return

        # Otherwise, we are in queue. We should render the panel.
        self.__update_queue_panel(_time=int(time.time()-self.startedQueueAt), queuePos=position, totalQueueing=total)

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