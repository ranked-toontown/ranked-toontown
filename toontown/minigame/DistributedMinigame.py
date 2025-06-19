import random

from direct.directnotify import DirectNotifyGlobal
from direct.distributed import DistributedObject
from direct.distributed.ClockDelta import *
from direct.fsm import ClassicFSM
from direct.fsm import State
from direct.gui.DirectGui import *
from direct.showbase import RandomNumGen
from direct.task.Task import Task
from panda3d.core import *

from otp.avatar import Emote
from otp.distributed.TelemetryLimiter import RotationLimitToH, TLGatherAllAvs
from toontown.toon import Toon
from toontown.toonbase import TTLocalizer
from . import MinigameGlobals
from . import MinigameRulesPanel
from ..archipelago.definitions import color_profile
from ..archipelago.util.global_text_properties import get_raw_formatted_string, MinimalJsonMessagePart
from ..matchmaking.rank import Rank
from ..toon.DistributedToon import DistributedToon


class DistributedMinigame(DistributedObject.DistributedObject):
    notify = DirectNotifyGlobal.directNotify.newCategory('DistributedMinigame')

    def __init__(self, cr):
        DistributedObject.DistributedObject.__init__(self, cr)
        self.waitingStartLabel = DirectLabel(text=TTLocalizer.MinigameWaitingForOtherPlayers, text_fg=VBase4(1, 1, 1, 1), relief=None, pos=(-0.6, 0, -0.75), scale=0.075)
        self.waitingStartLabel.hide()
        self.host: int | None = None  # The host of this minigame. If 0/None, there is no host.
        self.avIdList = []
        self._spectators = []
        self.remoteAvIdList = []
        self.localAvId = base.localAvatar.doId
        self.frameworkFSM = ClassicFSM.ClassicFSM(
            'DistributedMinigame',
            [
                State.State('frameworkInit', self.enterFrameworkInit, self.exitFrameworkInit, ['frameworkRules', 'frameworkCleanup', 'frameworkAvatarExited']),
                State.State('frameworkRules', self.enterFrameworkRules, self.exitFrameworkRules, ['frameworkWaitServerStart', 'frameworkCleanup', 'frameworkAvatarExited']),
                State.State('frameworkWaitServerStart', self.enterFrameworkWaitServerStart, self.exitFrameworkWaitServerStart, ['frameworkGame', 'frameworkCleanup', 'frameworkAvatarExited']),
                State.State('frameworkGame', self.enterFrameworkGame, self.exitFrameworkGame, ['frameworkWaitServerFinish', 'frameworkCleanup', 'frameworkAvatarExited']),
                State.State('frameworkWaitServerFinish', self.enterFrameworkWaitServerFinish, self.exitFrameworkWaitServerFinish, ['frameworkCleanup']),
                State.State('frameworkAvatarExited', self.enterFrameworkAvatarExited, self.exitFrameworkAvatarExited, ['frameworkCleanup']),
                State.State('frameworkCleanup', self.enterFrameworkCleanup, self.exitFrameworkCleanup, [])
            ],
            'frameworkInit',
            'frameworkCleanup'
        )
        hoodMinigameState = self.cr.playGame.hood.fsm.getStateNamed('minigame')
        hoodMinigameState.addChild(self.frameworkFSM)
        self.rulesDoneEvent = 'rulesDone'
        self.acceptOnce('minigameAbort', self.d_requestExit)
        base.curMinigame = self
        self.modelCount = 500
        self.cleanupActions = []
        self.usesSmoothing = 0
        self.usesLookAround = 0
        self.difficultyOverride = None
        self.trolleyZoneOverride = None
        self.hasLocalToon = 0
        self.frameworkFSM.enterInitialState()
        self.skillProfileKey = ''
        self._telemLimiter = None
        
        # Ready timeout timer
        self.readyTimeoutTimer = None
        self.readyTimeoutDuration = 0
        return

    def addChildGameFSM(self, gameFSM):
        self.frameworkFSM.getStateNamed('frameworkGame').addChild(gameFSM)

    def removeChildGameFSM(self, gameFSM):
        self.frameworkFSM.getStateNamed('frameworkGame').removeChild(gameFSM)

    def setUsesSmoothing(self):
        self.usesSmoothing = 1

    def setUsesLookAround(self):
        self.usesLookAround = 1

    def getTitle(self):
        return TTLocalizer.DefaultMinigameTitle

    def getInstructions(self):
        return TTLocalizer.DefaultMinigameInstructions

    def getMaxDuration(self):
        raise Exception('Minigame implementer: you must override getMaxDuration()')

    def __createRandomNumGen(self):
        self.notify.debug('BASE: self.doId=0x%08X' % self.doId)
        self.randomNumGen = RandomNumGen.RandomNumGen(self.doId)

        def destroy(self = self):
            self.notify.debug('BASE: destroying random num gen')
            del self.randomNumGen

        self.cleanupActions.append(destroy)

    def generate(self):
        self.notify.debug('BASE: generate, %s' % self.getTitle())
        DistributedObject.DistributedObject.generate(self)
        self.__createRandomNumGen()

    def announceGenerate(self):
        DistributedObject.DistributedObject.announceGenerate(self)
        if not self.hasLocalToon:
            return
        self.notify.debug('BASE: handleAnnounceGenerate: send setAvatarJoined')
        if base.randomMinigameNetworkPlugPull and random.random() < 1.0 / 25:
            print('*** DOING RANDOM MINIGAME NETWORK-PLUG-PULL BEFORE SENDING setAvatarJoined ***')
            base.cr.pullNetworkPlug()
        self.sendUpdate('setAvatarJoined', [])
        self.normalExit = 1
        count = self.modelCount
        loader.beginBulkLoad('minigame', TTLocalizer.HeadingToMinigameTitle % self.getTitle(), count, 1, TTLocalizer.TIP_MINIGAME)
        self.load()
        loader.endBulkLoad('minigame')
        globalClock.syncFrameTime()
        self.onstage()

        def cleanup(self = self):
            self.notify.debug('BASE: cleanup: normalExit=%s' % self.normalExit)
            self.offstage()
            base.cr.renderFrame()
            if self.normalExit:
                self.sendUpdate('setAvatarExited', [])

        self.cleanupActions.append(cleanup)
        self._telemLimiter = self.getTelemetryLimiter()
        self.frameworkFSM.request('frameworkRules')

    def disable(self):
        self.notify.debug('BASE: disable')
        if self._telemLimiter:
            self._telemLimiter.destroy()
            self._telemLimiter = None
        self.frameworkFSM.request('frameworkCleanup')
        taskMgr.remove(self.uniqueName('random-abort'))
        taskMgr.remove(self.uniqueName('random-disconnect'))
        taskMgr.remove(self.uniqueName('random-netplugpull'))
        DistributedObject.DistributedObject.disable(self)
        return

    def delete(self):
        self.notify.debug('BASE: delete')
        if self.hasLocalToon:
            self.unload()
        self.ignoreAll()
        if self.cr.playGame.hood:
            hoodMinigameState = self.cr.playGame.hood.fsm.getStateNamed('minigame')
            hoodMinigameState.removeChild(self.frameworkFSM)
        self.waitingStartLabel.destroy()
        del self.waitingStartLabel
        del self.frameworkFSM
        DistributedObject.DistributedObject.delete(self)

    def getTelemetryLimiter(self):
        return TLGatherAllAvs('Minigame', RotationLimitToH)

    def load(self):
        self.notify.debug('BASE: load')
        Toon.loadMinigameAnims()

    def onstage(self):
        self.notify.debug('BASE: onstage')

        def calcMaxDuration(self = self):
            return (self.getMaxDuration() + MinigameGlobals.rulesDuration) * 1.1

        if not base.cr.networkPlugPulled():
            if base.randomMinigameAbort:
                maxDuration = calcMaxDuration()
                self.randomAbortDelay = random.random() * maxDuration
                taskMgr.doMethodLater(self.randomAbortDelay, self.doRandomAbort, self.uniqueName('random-abort'))
            if base.randomMinigameDisconnect:
                maxDuration = calcMaxDuration()
                self.randomDisconnectDelay = random.random() * maxDuration
                taskMgr.doMethodLater(self.randomDisconnectDelay, self.doRandomDisconnect, self.uniqueName('random-disconnect'))
            if base.randomMinigameNetworkPlugPull:
                maxDuration = calcMaxDuration()
                self.randomNetPlugPullDelay = random.random() * maxDuration
                taskMgr.doMethodLater(self.randomNetPlugPullDelay, self.doRandomNetworkPlugPull, self.uniqueName('random-netplugpull'))

    def doRandomAbort(self, task):
        print('*** DOING RANDOM MINIGAME ABORT AFTER %.2f SECONDS ***' % self.randomAbortDelay)
        self.d_requestExit()
        return Task.done

    def doRandomDisconnect(self, task):
        print('*** DOING RANDOM MINIGAME DISCONNECT AFTER %.2f SECONDS ***' % self.randomDisconnectDelay)
        self.sendUpdate('setGameReady')
        return Task.done

    def doRandomNetworkPlugPull(self, task):
        print('*** DOING RANDOM MINIGAME NETWORK-PLUG-PULL AFTER %.2f SECONDS ***' % self.randomNetPlugPullDelay)
        base.cr.pullNetworkPlug()
        return Task.done

    def offstage(self):
        self.notify.debug('BASE: offstage')
        for avId in self.avIdList:
            av = self.getAvatar(avId)
            if av:
                av.detachNode()

        messenger.send('minigameOffstage')

    def unload(self):
        self.notify.debug('BASE: unload')
        if hasattr(base, 'curMinigame'):
            del base.curMinigame
        Toon.unloadMinigameAnims()

    def hasHost(self) -> bool:
        return self.host is not None and self.host != 0

    def setHost(self, host: int):
        self.host = host
        if self.host == 0:
            self.host = None

    def getHost(self) -> int | None:
        return self.host

    def isLocalToonHost(self) -> bool:
        """
        Returns True if our local toon is the host of this game.
        """
        return self.getHost() == base.localAvatar.getDoId()

    def getHostToon(self) -> DistributedToon | None:
        """
        Gets the host as a DistributedToon object. If the result is none, there either isn't a host or the toon
        that is assigned as host is not present in our instance. Be mindful of race conditions as well.
        """
        if not self.hasHost():
            return None

        # Query the toon in our client repository. If it's a toon, return it.
        toon = base.cr.getDo(self.host)
        if isinstance(toon, DistributedToon):
            return toon

        return None

    def setParticipants(self, avIds):
        self.avIdList = avIds
        self.numPlayers = len(self.avIdList)
        self.hasLocalToon = self.localAvId in self.avIdList
        if not self.hasLocalToon:
            self.notify.warning('localToon (%s) not in list of minigame players: %s' % (self.localAvId, self.avIdList))
            return
        self.notify.info('BASE: setParticipants: %s' % self.avIdList)
        self.remoteAvIdList = []
        for avId in self.avIdList:
            if avId != self.localAvId:
                self.remoteAvIdList.append(avId)

    def getParticipantIds(self) -> list[int]:
        """
        Returns a list of toon IDs that are present in this minigame.
        """
        return list(self.avIdList)

    def getParticipants(self):
        """
        Returns a list of DistributedToon objects that are present in this minigame.
        """
        toons = []
        for avId in self.getParticipantIds():
            toon = self.cr.getDo(avId)
            if toon:
                toons.append(toon)
        return toons

    def setSpectators(self, avIds):
        """
        Implicitly called from astron to sync the AI managed list of toons that are flagged as spectators.
        """
        self._spectators = avIds
        self.updatePlayerNametags()

    def getSpectators(self) -> list[int]:
        """
        Returns a list of toon IDs that are flagged as spectators.
        """
        return list(self._spectators)

    def getSpectatingToons(self):
        """
        Gets a list of DistributedToon instances that are spectating.
        """
        toons = []
        for avId in self.getSpectators():
            toon = self.cr.getDo(avId)
            if toon:
                toons.append(toon)
        return toons

    def getParticipantIdsNotSpectating(self):
        """
        Gets a list of toon IDs that are not spectating.
        These are toons that should be considered to be active players in the minigame.
        We should always opt in to call this method instead of self.avIdList directly for game logic if possible.
        """
        toons = []
        for avId in self.avIdList:
            if avId not in self.getSpectators():
                toons.append(avId)
        return toons

    def getParticipantsNotSpectating(self):
        """
        Gets a list of DistributedToon instances that are not spectating.
        These are toons that should be considered to be active players in the minigame.
        We should always opt in to call this method instead of self.avIdList directly for game logic if possible.
        """
        toons = []
        for avId in self.getParticipantIdsNotSpectating():
            toon = self.cr.getDo(avId)
            if toon:
                toons.append(toon)
        return toons

    def isSpectating(self, avId) -> bool:
        """
        Returns True if the given toon id is flagged as a spectator.
        """
        return avId in self._spectators

    def localToonSpectating(self) -> bool:
        """
        Returns True if our local toon is spectating.
        """
        return self.isSpectating(self.localAvId)

    def setTrolleyZone(self, trolleyZone):
        if not self.hasLocalToon:
            return
        self.notify.debug('BASE: setTrolleyZone: %s' % trolleyZone)
        self.trolleyZone = trolleyZone

    def setDifficultyOverrides(self, difficultyOverride, trolleyZoneOverride):
        if not self.hasLocalToon:
            return
        if difficultyOverride != MinigameGlobals.NoDifficultyOverride:
            self.difficultyOverride = difficultyOverride / float(MinigameGlobals.DifficultyOverrideMult)
        if trolleyZoneOverride != MinigameGlobals.NoTrolleyZoneOverride:
            self.trolleyZoneOverride = trolleyZoneOverride

    def isRanked(self) -> bool:
        return self.skillProfileKey != ''

    def getSkillProfileKey(self) -> str:
        """
        What is the minigame going to store ELO/SR ratings under on the toons?
        This key CAN be dynamic, but it needs to be consistent with how you want to store skill.
        """
        return self.skillProfileKey

    def setSkillProfileKey(self, key: str) -> None:
        """
        Called from the AI. Informs us of what the skill profile is for this minigame.
        If an empty string was provided, this is an unranked game.
        """
        self.skillProfileKey = key
        self.updatePlayerNametags()

    def setReadyTimeout(self, timeout):
        """
        Receive the ready timeout duration from the server and start displaying a countdown timer.
        """
        self.readyTimeoutDuration = timeout
        self._createReadyTimeoutTimer()

    def _createReadyTimeoutTimer(self):
        """Create and display the ready timeout countdown timer"""
        from toontown.toonbase import ToontownTimer
        
        # Clean up any existing timer
        self._destroyReadyTimeoutTimer()
        
        self.readyTimeoutTimer = ToontownTimer.ToontownTimer()
        self.readyTimeoutTimer.reparentTo(aspect2d)
        self.readyTimeoutTimer.setScale(0.4)
        self.readyTimeoutTimer.setPos(1.5, 0, -0.8)  # Bottom right corner
        
        # Start the countdown - when it expires, the server will automatically abort the game
        self.readyTimeoutTimer.countdown(self.readyTimeoutDuration, self._handleReadyTimeoutExpired)

    def _handleReadyTimeoutExpired(self):
        """Called when the ready timeout timer expires (though server handles the actual timeout)"""
        # The server will handle the actual timeout and game abort
        # This is just for visual feedback
        pass

    def _destroyReadyTimeoutTimer(self):
        """Clean up the ready timeout timer"""
        if self.readyTimeoutTimer is not None:
            self.readyTimeoutTimer.stop()
            self.readyTimeoutTimer.removeNode()
            self.readyTimeoutTimer = None

    def updatePlayerNametags(self):
        """
        Updates every player's nametag in the instance.
        If this is a ranked game, we should also display their rank.
        """

        spectators = self.getSpectators()

        # Apply the changes to everyone.
        for toon in self.getParticipants():

            # First, resolve the color of the toon's names we want to show. Red for enemies, Blue for us. Default to gray.
            nameColor = 'gray'
            colorProfile = color_profile.GRAY

            # People who are playing should have their colors updated from gray.

            if toon.getDoId() not in spectators:
                nameColor = 'slateblue' if toon.getDoId() == base.localAvatar.getDoId() else 'red'
                colorProfile = color_profile.BLUE if toon.getDoId() == base.localAvatar.getDoId() else color_profile.RED

            name = get_raw_formatted_string([
                MinimalJsonMessagePart(toon.getName(), color=nameColor),
            ])

            # If this is a ranked game, append the rank component.
            if self.isRanked():
                profile = toon.getSkillProfile(self.getSkillProfileKey())
                rank = Rank.get_from_skill_rating(profile.skill_rating).colored() if profile else get_raw_formatted_string([MinimalJsonMessagePart("Unranked", color='gray')])
                name += f"\n{rank}"

            toon.setFancyNametag(name)
            toon.setColorProfile(colorProfile)

    def setGameReady(self):
        if not self.hasLocalToon:
            return
        self.notify.debug('BASE: setGameReady: Ready for game with avatars: %s' % self.avIdList)
        self.notify.debug('  safezone: %s' % self.getSafezoneId())
        self.notify.debug('difficulty: %s' % self.getDifficulty())
        self.__serverFinished = 0
        for avId in self.remoteAvIdList:
            if avId not in self.cr.doId2do:
                self.notify.warning('BASE: toon %s already left or has not yet arrived; waiting for server to abort the game' % avId)
                return 1

        self.updatePlayerNametags()
        for avId in self.remoteAvIdList:
            avatar = self.cr.doId2do[avId]
            event = avatar.uniqueName('disable')
            self.acceptOnce(event, self.handleDisabledAvatar, [avId])

            def ignoreToonDisable(self = self, event = event):
                self.ignore(event)

            self.cleanupActions.append(ignoreToonDisable)

        for avId in self.avIdList:
            avatar = self.getAvatar(avId)
            if avatar:
                if not self.usesSmoothing:
                    avatar.stopSmooth()
                if not self.usesLookAround:
                    avatar.stopLookAround()

        def cleanupAvatars(self = self):
            for avId in self.avIdList:
                avatar = self.getAvatar(avId)
                if avatar:
                    avatar.stopSmooth()
                    avatar.startLookAround()

        self.cleanupActions.append(cleanupAvatars)
        return 0

    def setGameStart(self, timestamp):
        if not self.hasLocalToon:
            return
        self.notify.debug('BASE: setGameStart: Starting game')
        self.gameStartTime = globalClockDelta.networkToLocalTime(timestamp)
        self.frameworkFSM.request('frameworkGame')

    def setGameAbort(self):
        if not self.hasLocalToon:
            return
        self.notify.warning('BASE: setGameAbort: Aborting game')
        self.normalExit = 0
        self.frameworkFSM.request('frameworkCleanup')

    def gameOver(self):
        if not self.hasLocalToon:
            return
        self.notify.debug('BASE: gameOver')
        self.frameworkFSM.request('frameworkWaitServerFinish')

    def getAvatar(self, avId):
        if avId in self.cr.doId2do:
            return self.cr.doId2do[avId]
        else:
            self.notify.warning('BASE: getAvatar: No avatar in doId2do with id: ' + str(avId))
            return None
        return None

    def getAvatarName(self, avId):
        avatar = self.getAvatar(avId)
        if avatar:
            return avatar.getName()
        else:
            return 'Unknown'

    def isSinglePlayer(self):
        if self.numPlayers == 1:
            return 1
        else:
            return 0

    def handleDisabledAvatar(self, avId):
        self.notify.warning('BASE: handleDisabledAvatar: disabled avId: ' + str(avId))
        self.frameworkFSM.request('frameworkAvatarExited')

    def d_requestExit(self):
        self.notify.debug('BASE: Sending requestExit')
        self.sendUpdate('requestExit', [])

    def enterFrameworkInit(self):
        self.notify.debug('BASE: enterFrameworkInit')
        self.setEmotes()
        self.cleanupActions.append(self.unsetEmotes)

    def exitFrameworkInit(self):
        pass

    def enterFrameworkRules(self):
        self.notify.debug('BASE: enterFrameworkRules')
        self.accept(self.rulesDoneEvent, self.handleRulesDone)
        self.rulesPanel = MinigameRulesPanel.MinigameRulesPanel('MinigameRulesPanel', self.getTitle(), self.getInstructions(), self.rulesDoneEvent)
        self.rulesPanel.load()
        self.rulesPanel.enter()
        self.updatePlayerNametags()

    def exitFrameworkRules(self):
        self.ignore(self.rulesDoneEvent)
        self.rulesPanel.exit()
        self.rulesPanel.unload()
        del self.rulesPanel
        # Clean up the ready timeout timer
        self._destroyReadyTimeoutTimer()

    def handleRulesDone(self):
        self.notify.debug('BASE: handleRulesDone')
        self.sendUpdate('setAvatarReady', [])
        self.frameworkFSM.request('frameworkWaitServerStart')

    def enterFrameworkWaitServerStart(self):
        self.notify.debug('BASE: enterFrameworkWaitServerStart')
        # Clean up the ready timeout timer since we're no longer waiting for ready
        self._destroyReadyTimeoutTimer()
        if self.numPlayers > 1:
            msg = TTLocalizer.MinigameWaitingForOtherPlayers
        else:
            msg = TTLocalizer.MinigamePleaseWait
        self.waitingStartLabel['text'] = msg
        self.waitingStartLabel.show()

    def exitFrameworkWaitServerStart(self):
        self.waitingStartLabel.hide()

    def enterFrameworkGame(self):
        self.notify.debug('BASE: enterFrameworkGame')

    def exitFrameworkGame(self):
        pass

    def enterFrameworkWaitServerFinish(self):
        self.notify.debug('BASE: enterFrameworkWaitServerFinish')
        if self.__serverFinished:
            self.frameworkFSM.request('frameworkCleanup')

    def setGameExit(self):
        if not self.hasLocalToon:
            return
        self.notify.debug('BASE: setGameExit: now safe to exit game')
        if self.frameworkFSM.getCurrentState().getName() != 'frameworkWaitServerFinish':
            self.__serverFinished = 1
        else:
            self.frameworkFSM.request('frameworkCleanup')

    def exitFrameworkWaitServerFinish(self):
        pass

    def enterFrameworkAvatarExited(self):
        self.notify.debug('BASE: enterFrameworkAvatarExited')

    def exitFrameworkAvatarExited(self):
        pass

    def enterFrameworkCleanup(self):
        self.notify.debug('BASE: enterFrameworkCleanup')
        # Clean up the ready timeout timer
        self._destroyReadyTimeoutTimer()
        for action in self.cleanupActions:
            action()

        self.cleanupActions = []
        self.ignoreAll()
        if self.hasLocalToon:
            messenger.send(self.cr.playGame.hood.minigameDoneEvent)

    def exitFrameworkCleanup(self):
        pass

    def local2GameTime(self, timestamp):
        return timestamp - self.gameStartTime

    def game2LocalTime(self, timestamp):
        return timestamp + self.gameStartTime

    def getCurrentGameTime(self):
        return self.local2GameTime(globalClock.getFrameTime())

    def getDifficulty(self):
        if self.difficultyOverride is not None:
            return self.difficultyOverride
        if hasattr(base, 'minigameDifficulty'):
            return float(base.minigameDifficulty)
        return MinigameGlobals.getDifficulty(self.getSafezoneId())

    def getSafezoneId(self):
        if self.trolleyZoneOverride is not None:
            return self.trolleyZoneOverride
        if hasattr(base, 'minigameSafezoneId'):
            return MinigameGlobals.getSafezoneId(base.minigameSafezoneId)
        return MinigameGlobals.getSafezoneId(self.trolleyZone)

    def setEmotes(self):
        Emote.globalEmote.disableAll(base.localAvatar)

    def unsetEmotes(self):
        Emote.globalEmote.releaseAll(base.localAvatar)
