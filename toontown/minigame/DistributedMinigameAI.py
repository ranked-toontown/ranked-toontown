from direct.directnotify.DirectNotifyGlobal import directNotify

from otp.ai.AIBase import *
from direct.distributed.ClockDelta import *
from toontown.ai.ToonBarrier import *
from direct.distributed import DistributedObjectAI
from direct.fsm import ClassicFSM, State
from direct.fsm import State
from toontown.shtiker import PurchaseManagerAI
from toontown.shtiker import NewbiePurchaseManagerAI
from . import MinigameCreatorAI
from direct.task import Task
import random
from . import MinigameGlobals
from direct.showbase import PythonUtil
from . import TravelGameGlobals
from toontown.toonbase import ToontownGlobals
from .utils.scoring_context import ScoringContext
from ..matchmaking.skill_profile_keys import SkillProfileKey
from ..matchmaking.skill_rating import OpenSkillMatch, OpenSkillMatchDeltaResults
from ..toon.DistributedToonAI import DistributedToonAI

EXITED = 0
EXPECTED = 1
JOINED = 2
READY = 3
DEFAULT_POINTS = 1
MAX_POINTS = 7
JOIN_TIMEOUT = 40.0 + MinigameGlobals.latencyTolerance
READY_TIMEOUT = MinigameGlobals.MaxLoadTime + MinigameGlobals.rulesDuration + MinigameGlobals.latencyTolerance
EXIT_TIMEOUT = 20.0 + MinigameGlobals.latencyTolerance


class DistributedMinigameAI(DistributedObjectAI.DistributedObjectAI):
    notify = directNotify.newCategory('DistributedMinigameAI')

    def __init__(self, air, minigameId):

        DistributedObjectAI.DistributedObjectAI.__init__(self, air)
        self.minigameId = minigameId
        self.frameworkFSM = ClassicFSM.ClassicFSM('DistributedMinigameAI', [
            State.State('frameworkOff', self.enterFrameworkOff, self.exitFrameworkOff, ['frameworkWaitClientsJoin']),
            State.State('frameworkWaitClientsJoin', self.enterFrameworkWaitClientsJoin, self.exitFrameworkWaitClientsJoin,['frameworkWaitClientsReady', 'frameworkWaitClientsExit', 'frameworkCleanup']),
            State.State('frameworkWaitClientsReady', self.enterFrameworkWaitClientsReady,self.exitFrameworkWaitClientsReady,['frameworkGame', 'frameworkWaitClientsExit', 'frameworkCleanup']),
            State.State('frameworkGame', self.enterFrameworkGame, self.exitFrameworkGame,['frameworkWaitClientsExit', 'frameworkCleanup']),
            State.State('frameworkWaitClientsExit', self.enterFrameworkWaitClientsExit,self.exitFrameworkWaitClientsExit, ['frameworkCleanup']),
            State.State('frameworkCleanup', self.enterFrameworkCleanup, self.exitFrameworkCleanup, ['frameworkOff'])
        ], 'frameworkOff', 'frameworkOff')

        self.frameworkFSM.enterInitialState()
        self.avIdList = []
        self._spectators = []
        self.toonsSkipped = []
        self.stateDict = {}
        self.difficultyOverride = None
        self.trolleyZoneOverride = None
        self.metagameRound = -1
        self.startingVotes = {}
        self.context = ScoringContext()

        # The SR context to use for this minigame. If none, we assume this is not a ranked game.
        self.skillProfileKey: SkillProfileKey | None = SkillProfileKey.MINIGAMES

    def isRanked(self) -> bool:
        """
        Is this minigame going to affect ELO/SR ratings upon completion?
        Override and set to True if you would like to automatically apply ranked calculations.
        """
        return self.skillProfileKey is not None

    def getSkillProfileKey(self) -> str:
        """
        What is the minigame going to store ELO/SR ratings under on the toons?
        This key CAN be dynamic, but it needs to be consistent with how you want to store skill.
        """
        return self.skillProfileKey.value if self.skillProfileKey is not None else ''

    def setProfileSkillKey(self, key: SkillProfileKey | None) -> None:
        self.skillProfileKey = key

    def b_setProfileSkillKey(self, key: SkillProfileKey):
        self.setProfileSkillKey(key)
        self.d_setSkillProfileKey(key)

    def d_setSkillProfileKey(self, key: SkillProfileKey) -> None:
        """
        Updates the client on what skill profile key we are using given the context of the minigame.
        Call at any time to sync the client. Sending an empty string will inform the client that the current
        minigame is not going to be ranked. If self.isRanked() is False, an empty string will be automatically provided
        assuming the game is unranked.
        """
        self.sendUpdate('setSkillProfileKey', [key.value if self.isRanked() else ''])

    def addChildGameFSM(self, gameFSM):
        self.frameworkFSM.getStateNamed('frameworkGame').addChild(gameFSM)

    def removeChildGameFSM(self, gameFSM):
        self.frameworkFSM.getStateNamed('frameworkGame').removeChild(gameFSM)

    def setExpectedAvatars(self, avIds):
        self.avIdList = avIds
        self.numPlayers = len(self.avIdList)
        self.notify.debug('BASE: setExpectedAvatars: expecting avatars: ' + str(self.avIdList))

    def setSpectators(self, avIds):
        self._spectators = avIds

    def getSpectators(self) -> list[int]:
        """
        Returns a list of toon IDs that are flagged as spectators.
        """
        return list(self._spectators)

    def b_setSpectators(self, avIds):
        self.setSpectators(avIds)
        self.d_setSpectators(avIds)

    def d_setSpectators(self, avIds):
        self.sendUpdate('setSpectators', [avIds])

    def isSpectating(self, avId) -> bool:
        """
        Returns True if the given toon id is flagged as a spectator.
        """
        return avId in self._spectators

    def setNewbieIds(self, newbieIds):
        self.newbieIdList = newbieIds
        if len(self.newbieIdList) > 0:
            self.notify.debug('BASE: setNewbieIds: %s' % self.newbieIdList)

    def setTrolleyZone(self, trolleyZone):
        self.trolleyZone = trolleyZone

    def setDifficultyOverrides(self, difficultyOverride, trolleyZoneOverride):
        self.difficultyOverride = difficultyOverride
        if self.difficultyOverride is not None:
            self.difficultyOverride = MinigameGlobals.QuantizeDifficultyOverride(difficultyOverride)
        self.trolleyZoneOverride = trolleyZoneOverride
        return

    def setMetagameRound(self, roundNum):
        self.metagameRound = roundNum

    def _playing(self):
        if not hasattr(self, 'gameFSM'):
            return False
        if self.gameFSM.getCurrentState() == None:
            return False
        return self.gameFSM.getCurrentState().getName() == 'play'

    def _inState(self, states):
        if not hasattr(self, 'gameFSM'):
            return False
        if self.gameFSM.getCurrentState() == None:
            return False
        return self.gameFSM.getCurrentState().getName() in makeList(states)

    def generate(self):
        DistributedObjectAI.DistributedObjectAI.generate(self)
        self.frameworkFSM.request('frameworkWaitClientsJoin')

    def delete(self):
        self.notify.debug('BASE: delete: deleting AI minigame object')
        
        # Clean up combo trackers
        if hasattr(self, 'comboTrackers'):
            self.cleanupComboTrackers()
        
        # Clean up status effect system
        if hasattr(self, 'statusEffectSystem') and self.statusEffectSystem:
            self.statusEffectSystem.requestDelete()
            self.statusEffectSystem = None
        
        # Ignore all events
        self.ignoreAll()
        
        # Clean up FSM
        if hasattr(self, 'frameworkFSM'):
            del self.frameworkFSM
        
        DistributedObjectAI.DistributedObjectAI.delete(self)

    def isSinglePlayer(self):
        if self.numPlayers == 1:
            return 1
        else:
            return 0

    def getScoringContext(self) -> ScoringContext:
        return self.context

    def getParticipants(self) -> list[int]:
        """
        Returns a list of toon IDs that are present in this minigame.
        """
        return self.avIdList

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
            toon = self.air.getDo(avId)
            if toon:
                toons.append(toon)
        return toons

    def getParticipatingToons(self):
        """
        Returns a list of DistributedToon objects that are present in this minigame.
        """
        toons = []
        for avId in self.getParticipants():
            toon = self.air.getDo(avId)
            if toon:
                toons.append(toon)
        return toons

    def getTrolleyZone(self):
        return self.trolleyZone

    def getDifficultyOverrides(self):
        response = [self.difficultyOverride, self.trolleyZoneOverride]
        if response[0] is None:
            response[0] = MinigameGlobals.NoDifficultyOverride
        else:
            response[0] *= MinigameGlobals.DifficultyOverrideMult
            response[0] = int(response[0])
        if response[1] is None:
            response[1] = MinigameGlobals.NoTrolleyZoneOverride
        return response

    def b_setGameReady(self):
        self.setGameReady()
        self.d_setGameReady()

    def d_setGameReady(self):
        self.notify.debug('BASE: Sending setGameReady')
        self.sendUpdate('setGameReady', [])

    def setGameReady(self):
        self.notify.debug('BASE: setGameReady: game ready with avatars: %s' % self.avIdList)
        self.normalExit = 1

    def b_setGameStart(self, timestamp):
        self.d_setGameStart(timestamp)
        self.setGameStart(timestamp)

    def d_setGameStart(self, timestamp):
        self.notify.debug('BASE: Sending setGameStart')
        self.sendUpdate('setGameStart', [timestamp])

    def setGameStart(self, timestamp):
        self.notify.debug('BASE: setGameStart')

    def b_setGameExit(self):
        self.d_setGameExit()
        self.setGameExit()

    def d_setGameExit(self):
        self.notify.debug('BASE: Sending setGameExit')
        self.sendUpdate('setGameExit', [])

    def setGameExit(self):
        self.notify.debug('BASE: setGameExit')

    def setGameAbort(self):
        self.notify.debug('BASE: setGameAbort')
        self.normalExit = 0
        self.sendUpdate('setGameAbort', [])
        self.frameworkFSM.request('frameworkCleanup')

    def handleExitedAvatar(self, avId):
        self.notify.warning('BASE: handleExitedAvatar: avatar id exited: ' + str(avId))
        self.stateDict[avId] = EXITED
        self.setGameAbort()

    def gameOver(self):
        self.notify.debug('BASE: gameOver')
        self.frameworkFSM.request('frameworkWaitClientsExit')

    def enterFrameworkOff(self):
        self.notify.debug('BASE: enterFrameworkOff')

    def exitFrameworkOff(self):
        pass

    def enterFrameworkWaitClientsJoin(self):
        self.notify.debug('BASE: enterFrameworkWaitClientsJoin')
        for avId in self.avIdList:
            self.stateDict[avId] = EXPECTED
            self.acceptOnce(self.air.getAvatarExitEvent(avId), self.handleExitedAvatar, extraArgs=[avId])

        def allAvatarsJoined(self = self):
            self.notify.debug('BASE: all avatars joined')
            self.b_setGameReady()
            self.frameworkFSM.request('frameworkWaitClientsReady')

        def handleTimeout(avIds, self = self):
            self.notify.debug('BASE: timed out waiting for clients %s to join' % avIds)
            self.setGameAbort()

        self.__barrier = ToonBarrier('waitClientsJoin', self.uniqueName('waitClientsJoin'), self.avIdList, JOIN_TIMEOUT, allAvatarsJoined, handleTimeout)

    def setAvatarJoined(self):
        if self.frameworkFSM.getCurrentState().getName() != 'frameworkWaitClientsJoin':
            self.notify.debug('BASE: Ignoring setAvatarJoined message')
            return
        avId = self.air.getAvatarIdFromSender()
        self.notify.debug('BASE: setAvatarJoined: avatar id joined: ' + str(avId))
        self.air.writeServerEvent('minigame_joined', avId, '%s|%s' % (self.minigameId, self.trolleyZone))
        self.stateDict[avId] = JOINED
        self.notify.debug('BASE: setAvatarJoined: new states: ' + str(self.stateDict))
        self.__barrier.clear(avId)

    def exitFrameworkWaitClientsJoin(self):
        self.__barrier.cleanup()
        del self.__barrier

    def enterFrameworkWaitClientsReady(self):
        self.notify.debug('BASE: enterFrameworkWaitClientsReady')

        def allAvatarsReady(self = self):
            self.notify.debug('BASE: all avatars ready')
            self.frameworkFSM.request('frameworkGame')

        def handleTimeout(avIds, self = self):
            self.notify.debug("BASE: timed out waiting for clients %s to report 'ready'" % avIds)
            self.setGameAbort()

        self.__barrier = ToonBarrier('waitClientsReady', self.uniqueName('waitClientsReady'), self.avIdList, READY_TIMEOUT, allAvatarsReady, handleTimeout)
        for avId in list(self.stateDict.keys()):
            if self.stateDict[avId] == READY:
                self.__barrier.clear(avId)

        self.notify.debug('  safezone: %s' % self.getSafezoneId())
        self.notify.debug('difficulty: %s' % self.getDifficulty())

    def setAvatarReady(self):
        if self.frameworkFSM.getCurrentState().getName() not in ['frameworkWaitClientsReady', 'frameworkWaitClientsJoin']:
            self.notify.debug('BASE: Ignoring setAvatarReady message')
            return
        avId = self.air.getAvatarIdFromSender()
        self.notify.debug('BASE: setAvatarReady: avatar id ready: ' + str(avId))
        self.stateDict[avId] = READY
        self.notify.debug('BASE: setAvatarReady: new avId states: ' + str(self.stateDict))
        if self.frameworkFSM.getCurrentState().getName() == 'frameworkWaitClientsReady':
            self.__barrier.clear(avId)

    def exitFrameworkWaitClientsReady(self):
        self.__barrier.cleanup()
        del self.__barrier

    def enterFrameworkGame(self):
        self.notify.debug('BASE: enterFrameworkGame')
        self.gameStartTime = globalClock.getRealTime()
        self.b_setGameStart(globalClockDelta.localToNetworkTime(self.gameStartTime))

    def exitFrameworkGame(self):
        pass

    def enterFrameworkWaitClientsExit(self):
        self.notify.debug('BASE: enterFrameworkWaitClientsExit')
        self.b_setGameExit()

        def allAvatarsExited(self = self):
            self.notify.debug('BASE: all avatars exited')
            self.frameworkFSM.request('frameworkCleanup')

        def handleTimeout(avIds, self = self):
            self.notify.debug('BASE: timed out waiting for clients %s to exit' % avIds)
            self.frameworkFSM.request('frameworkCleanup')

        self.__barrier = ToonBarrier('waitClientsExit', self.uniqueName('waitClientsExit'), self.avIdList, EXIT_TIMEOUT, allAvatarsExited, handleTimeout)
        for avId in list(self.stateDict.keys()):
            if self.stateDict[avId] == EXITED:
                self.__barrier.clear(avId)

    def setAvatarExited(self):
        if self.frameworkFSM.getCurrentState().getName() != 'frameworkWaitClientsExit':
            self.notify.debug('BASE: Ignoring setAvatarExit message')
            return
        avId = self.air.getAvatarIdFromSender()
        self.notify.debug('BASE: setAvatarExited: avatar id exited: ' + str(avId))
        self.stateDict[avId] = EXITED
        self.notify.debug('BASE: setAvatarExited: new avId states: ' + str(self.stateDict))
        self.__barrier.clear(avId)

    def exitFrameworkWaitClientsExit(self):
        self.__barrier.cleanup()
        del self.__barrier

    def enterFrameworkCleanup(self):
        self.notify.debug('BASE: enterFrameworkCleanup: normalExit=%s' % self.normalExit)
        self.requestDelete()
        self.handleRegularPurchaseManager()
        self.frameworkFSM.request('frameworkOff')

    def adjustSkillRatings(self) -> OpenSkillMatchDeltaResults:

        # Query all profiles for this context.
        profiles = {}
        for av in self.getParticipantsNotSpectating():
            profiles[av.getDoId()] = av.getOrCreateSkillProfile(self.getSkillProfileKey())

        _model = self.skillProfileKey.get_model()

        # Create a match and add the players.
        match = OpenSkillMatch(_model)
        score_rankings = self.context.generate_score_rankings()

        # todo support teams. they are kind of hard to properly support until there is proper team support in trolley games.

        # Loop through all the profiles and add the player and their score.
        for player in profiles.values():
            match.add_player(player, score_rankings.get(player.identifier, 0))

        self.notify.warning(f"pre-openskill adjustment: {[p for p in profiles.values()]}")

        # Adjust!
        results = match.adjust_ratings()

        # Save all the data to the toons.
        updates = []
        for av in self.getParticipantsNotSpectating():
            profile_update = match.new_player_data.get(av.getDoId(), None)
            if profile_update is not None:
                av.addSkillProfile(profile_update)
                updates.append(profile_update)
            av.d_syncSkillProfiles()

        # Updates UD with SR rating cache for leaderboard tracking.
        self.air.leaderboardManager.reportMatchToUd(updates, [[toon.getDoId(), toon.getName()] for toon in self.getParticipantsNotSpectating()])

        return results

    def handleRegularPurchaseManager(self):

        # Adjust ratings if desired.
        deltas = None
        if self.isRanked():
            deltas = self.adjustSkillRatings()
            self.notify.warning(f"post-openskill adjustment deltas: {[p for p in deltas.get_player_results().values()]}")

        points = self.context.get_total_points()
        scoreList = [max(0, points.get(player, 0)) for player in self.avIdList]

        pm = PurchaseManagerAI.PurchaseManagerAI(self.air, self.avIdList, scoreList, self.minigameId, self.trolleyZone, self.newbieIdList, spectators=self.getSpectators(), profileDeltas=deltas.get_player_results().values() if deltas is not None else None)
        pm.generateWithRequired(self.zoneId)

    def exitFrameworkCleanup(self):
        pass

    def requestExit(self):
        self.notify.debug('BASE: requestExit: client has requested the game to end')
        self.setGameAbort()

    def checkSkip(self):
        self.notify.info("Checking skip")
        if len(self.toonsSkipped) >= 1:
            # exit minigame
            self.notify.info('Skipping minigame')
            self.requestExit()
        # else:
        #     # tell the client the amount of toons skipped
        #     self.notify.info('Sending client skip amount')
        #     self.sendUpdate('setSkipAmount', [len(self.toonsSkipped)])
        return
    
    def requestSkip(self):
        toon = self.air.getAvatarIdFromSender()
        if (toon not in self.avIdList) or (toon in self.toonsSkipped):
            self.notify.warning('Unable to request skip')
            return
        self.toonsSkipped.append(toon)
        self.notify.info('toons Skipped appended')
        self.checkSkip()

    def local2GameTime(self, timestamp):
        return timestamp - self.gameStartTime

    def game2LocalTime(self, timestamp):
        return timestamp + self.gameStartTime

    def getCurrentGameTime(self):
        return self.local2GameTime(globalClock.getFrameTime())

    def getDifficulty(self):
        if self.difficultyOverride is not None:
            return self.difficultyOverride
        if hasattr(self.air, 'minigameDifficulty'):
            return float(self.air.minigameDifficulty)
        return MinigameGlobals.getDifficulty(self.getSafezoneId())

    def getSafezoneId(self):
        if self.trolleyZoneOverride is not None:
            return self.trolleyZoneOverride
        if hasattr(self.air, 'minigameSafezoneId'):
            return MinigameGlobals.getSafezoneId(self.air.minigameSafezoneId)
        return MinigameGlobals.getSafezoneId(self.trolleyZone)

    def logPerfectGame(self, avId):
        self.air.writeServerEvent('perfectMinigame', avId, '%s|%s|%s' % (self.minigameId, self.trolleyZone, self.avIdList))

    def logAllPerfect(self):
        for avId in self.avIdList:
            self.logPerfectGame(avId)

    def getStartingVotes(self):
        retval = []
        for avId in self.avIdList:
            if avId in self.startingVotes:
                retval.append(self.startingVotes[avId])
            else:
                self.notify.warning('how did this happen? avId=%d not in startingVotes %s' % (avId, self.startingVotes))
                retval.append(0)

        return retval

    def setStartingVote(self, avId, startingVote):
        self.startingVotes[avId] = startingVote
        self.notify.debug('setting starting vote of avId=%d to %d' % (avId, startingVote))

    def getMetagameRound(self):
        return self.metagameRound
