from otp.ai.AIBaseGlobal import *
from panda3d.core import *
from direct.distributed.ClockDelta import *
from .PurchaseManagerConstants import *
import copy
from direct.task.Task import Task
from direct.distributed import DistributedObjectAI
from direct.directnotify import DirectNotifyGlobal
from toontown.minigame import TravelGameGlobals
from toontown.toonbase import ToontownGlobals
from toontown.minigame import MinigameGlobals

class PurchaseManagerAI(DistributedObjectAI.DistributedObjectAI):
    notify = DirectNotifyGlobal.directNotify.newCategory('PurchaseManagerAI')

    def __init__(self, air, playerArray, mpArray, previousMinigameId, trolleyZone, desiredNextGame = None, previousHost=None, spectators=None, profileDeltas=None):
        DistributedObjectAI.DistributedObjectAI.__init__(self, air)
        self.previousHost = previousHost
        self.playerIds = copy.deepcopy(playerArray)
        self.minigamePoints = copy.deepcopy(mpArray)
        self.previousMinigameId = previousMinigameId
        self.trolleyZone = trolleyZone
        if profileDeltas is not None:
            self.skillProfileDeltas = [profile.to_astron() for profile in profileDeltas]
        else:
            self.skillProfileDeltas = []
        self.isShutdown = 0
        self.desiredNextGame = desiredNextGame
        if spectators is None:
            spectators = []
        self.spectators = spectators
        for i in range(len(self.playerIds)):
            self.playerIds.append(0)

        for i in range(len(self.minigamePoints)):
            self.minigamePoints.append(0)

        self.playerStates = [PURCHASE_WAITING_STATE] * len(self.playerIds)
        self.playersReported = [PURCHASE_UNREPORTED_STATE] * len(self.playerIds)
        self.playerMoney = [0] * len(self.playerIds)
        for index, avId in enumerate(self.playerIds):

            # If this player does not exist, say they exited.
            if avId not in self.air.doId2do:
                self.playerStates[index] = PURCHASE_EXIT_STATE
                self.playersReported[index] = PURCHASE_REPORTED_STATE
                continue

            # Otherwise, wait for their response.
            self.playerStates[index] = PURCHASE_WAITING_STATE
            self.playersReported[index] = PURCHASE_UNREPORTED_STATE

        for avId in self.getInvolvedPlayerIds():
            if avId in self.air.doId2do:
                self.acceptOnce(self.air.getAvatarExitEvent(avId), self.__handleUnexpectedExit, extraArgs=[avId])
                av = self.air.doId2do[avId]
                avIndex = self.findAvIndex(avId)
                money = av.getMoney()
                if avIndex is None:
                    self.notify.warning('__init__ avIndex is none but avId=%s' % avId)
                    continue
                self.playerMoney[avIndex] = money
                if self.playerMoney[avIndex] < 0:
                    simbase.air.writeServerEvent('suspicious', avId, 'toon has invalid money %s, forcing to zero' % money)
                    self.playerMoney[avIndex] = 0
                av.addMoney(self.minigamePoints[avIndex])
                self.air.writeServerEvent('minigame', avId, '%s|%s|%s|%s' % (self.previousMinigameId,
                 self.trolleyZone,
                 self.playerIds,
                 self.minigamePoints[avIndex]))

        self.receivingInventory = 1
        self.receivingButtons = 1
        return

    def getInstantLeaveFlag(self):
        return self.previousHost is None or self.previousHost == 0

    def d_setInstantLeaveFlag(self):
        self.sendUpdate('setInstantLeaveFlag', [self.getInstantLeaveFlag()])

    def delete(self):
        taskMgr.remove(self.uniqueName('countdown-timer'))
        self.ignoreAll()
        DistributedObjectAI.DistributedObjectAI.delete(self)

    def getInvolvedPlayerIds(self):
        return self.playerIds

    def getMinigamePoints(self):
        return self.minigamePoints

    def getPlayerIds(self):
        return self.playerIds

    def getPlayerMoney(self):
        return self.playerMoney

    def d_setPlayerStates(self, stateArray):
        self.sendUpdate('setPlayerStates', [stateArray])
        return None

    def getPlayerStates(self):
        return self.playerStates

    def getSkillProfileDeltas(self):
        return self.skillProfileDeltas

    def getCountdown(self):
        self.startCountdown()
        return globalClockDelta.getRealNetworkTime()

    def startCountdown(self):
        if not config.GetBool('disable-purchase-timer', 0):
            taskMgr.doMethodLater(PURCHASE_COUNTDOWN_TIME, self.timeIsUpTask, self.uniqueName('countdown-timer'))

    def requestExit(self):
        avId = self.air.getAvatarIdFromSender()
        avIndex = self.findAvIndex(avId)
        if avIndex is None:
            self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestExit: unknown avatar: %s' % (avId,))
            return
        if self.receivingButtons:
            if avId in self.air.doId2do:
                av = self.air.doId2do[avId]
                if avIndex == None:
                    self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestExit not on list')
                    self.notify.warning('Avatar ' + str(avId) + ' requested Exit, but is not on the list!')
                else:
                    avState = self.playerStates[avIndex]
                    if avState == PURCHASE_PLAYAGAIN_STATE or avState == PURCHASE_WAITING_STATE:
                        self.playerStates[avIndex] = PURCHASE_EXIT_STATE
                        self.handlePlayerLeaving(avId)
                    else:
                        self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestExit invalid transition to exit')
                        self.notify.warning('Invalid transition to exit state.')
            else:
                self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestExit unknown avatar')
                self.notify.warning('Avatar ' + str(avId) + ' requested Exit, but is not in doId2do.' + ' Assuming disconnected.')
                self.playerStates[avIndex] = PURCHASE_DISCONNECTED_STATE
                self.playersReported[avIndex] = PURCHASE_CANTREPORT_STATE
                self.ignore(self.air.getAvatarExitEvent(avId))
            self.d_setPlayerStates(self.playerStates)
            if self.getNumUndecided() == 0:
                self.timeIsUp()
        else:
            self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestExit not receiving requests now')
            self.notify.warning('Avatar ' + str(avId) + ' requested Exit, but I am not receiving button requests now.')
        return

    def requestPlayAgain(self):
        avId = self.air.getAvatarIdFromSender()
        if self.findAvIndex(avId) == None:
            self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestPlayAgain: unknown avatar')
            return
        if self.receivingButtons:
            if avId in self.air.doId2do:
                av = self.air.doId2do[avId]
                avIndex = self.findAvIndex(avId)
                if avIndex == None:
                    self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestPlayAgain not on list')
                    self.notify.warning('Avatar ' + str(avId) + ' requested PlayAgain, but is not on the list!')
                else:
                    avState = self.playerStates[avIndex]
                    if avState == PURCHASE_WAITING_STATE:
                        self.notify.debug(str(avId) + ' wants to play again')
                        self.playerStates[avIndex] = PURCHASE_PLAYAGAIN_STATE
                    else:
                        self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestPlayAgain invalid transition to PlayAgain')
                        self.notify.warning('Invalid transition to PlayAgain state.')
            else:
                self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestPlayAgain unknown avatar')
                self.notify.warning('Avatar ' + str(avId) + ' requested PlayAgain, but is not in doId2do.' + ' Assuming disconnected.')
                avIndex = self.findAvIndex(avId)
                self.playerStates[avIndex] = PURCHASE_DISCONNECTED_STATE
                self.playersReported[avIndex] = PURCHASE_CANTREPORT_STATE
                self.ignore(self.air.getAvatarExitEvent(avId))
            self.d_setPlayerStates(self.playerStates)
            if self.getNumUndecided() == 0:
                self.timeIsUp()
        else:
            self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.requestPlayAgain not receiving requests now')
            self.notify.warning('Avatar ' + str(avId) + ' requested PlayAgain, but I am not receiving button ' + 'requests now.')
        return

    def report(self):
        """
        Called from the client when they are considered "done" with the purchase manager.
        """
        avId = self.air.getAvatarIdFromSender()
        avIndex = self.findAvIndex(avId)
        if avIndex is None:
            self.air.writeServerEvent('suspicious', avId, 'PurchaseManager.setInventory not on list')
            self.notify.warning('Avatar ' + str(avId) + ' requested purchase, but is not on the list!')
            return

        self.playersReported[avIndex] = PURCHASE_REPORTED_STATE
        if self.getNumUnreported() == 0:
            self.shutDown()

    def d_setPurchaseExit(self):
        self.sendUpdate('setPurchaseExit', [])
        return None

    def timeIsUpTask(self, task):
        self.timeIsUp()
        return Task.done

    def timeIsUp(self):
        self.d_setPurchaseExit()
        taskMgr.remove(self.uniqueName('countdown-timer'))
        self.receivingButtons = 0
        self.receivingInventory = 1
        return None

    def shutDown(self):
        if self.isShutdown:
            self.notify.warning('Got shutDown twice')
            return
        self.isShutdown = 1
        playAgainNum = self.getNumPlayAgain()
        if playAgainNum > 0:
            playAgainList = self.getPlayAgainList()
            newSpecList = []
            for oldSpec in self.spectators:
                if oldSpec in playAgainList:
                    newSpecList.append(oldSpec)
            self.air.minigameMgr.createMinigame(playAgainList, self.trolleyZone, minigameZone=self.zoneId, hostId=self.previousHost, previousGameId=self.previousMinigameId, desiredNextGame=self.desiredNextGame, spectatorIds=newSpecList)
        else:
            self.air.minigameMgr.releaseMinigameZone(self.zoneId)
        self.requestDelete()
        self.ignoreAll()
        return None

    def findAvIndex(self, avId):
        for i in range(len(self.playerIds)):
            if avId == self.playerIds[i]:
                return i

        return None

    def getNumUndecided(self):
        undecidedCounter = 0
        for playerState in self.playerStates:
            if playerState == PURCHASE_WAITING_STATE:
                undecidedCounter += 1

        return undecidedCounter

    def getPlayAgainList(self):
        playAgainList = []
        for i in range(len(self.playerStates)):
            if self.playerStates[i] == PURCHASE_PLAYAGAIN_STATE:
                playAgainList.append(self.playerIds[i])

        return playAgainList

    def getNumPlayAgain(self):
        playAgainCounter = 0
        for playerState in self.playerStates:
            if playerState == PURCHASE_PLAYAGAIN_STATE:
                playAgainCounter += 1

        return playAgainCounter

    def getNumUnreported(self):
        unreportedCounter = 0
        for playerState in self.playersReported:
            if playerState == PURCHASE_UNREPORTED_STATE:
                unreportedCounter += 1
            elif playerState == PURCHASE_REPORTED_STATE:
                pass
            elif playerState == PURCHASE_CANTREPORT_STATE:
                pass
            else:
                self.notify.warning('Weird report state: ' + str(playerState))

        return unreportedCounter

    def __handleUnexpectedExit(self, avId):
        self.notify.warning('Avatar: ' + str(avId) + ' has exited unexpectedly')
        index = self.findAvIndex(avId)
        if index == None:
            self.notify.warning('Something is seriously screwed up...' + 'An avatar exited unexpectedly, and they' + ' are not on my list!')
        else:
            self.playerStates[index] = PURCHASE_DISCONNECTED_STATE
            self.playersReported[index] = PURCHASE_CANTREPORT_STATE
            self.d_setPlayerStates(self.playerStates)
            if self.receivingButtons:
                if self.getNumUndecided() == 0:
                    self.timeIsUp()
            if self.receivingInventory:
                if self.getNumUnreported() == 0:
                    self.shutDown()
        return

    def handlePlayerLeaving(self, avId):
        pass
