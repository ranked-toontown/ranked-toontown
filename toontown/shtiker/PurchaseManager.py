from panda3d.core import *
from .PurchaseManagerConstants import *
from direct.distributed.ClockDelta import *
from direct.distributed import DistributedObject
from direct.directnotify import DirectNotifyGlobal
from toontown.minigame import TravelGameGlobals
from ..archipelago.definitions import color_profile
from ..matchmaking.player_skill_profile import PlayerSkillProfile


class PurchaseManager(DistributedObject.DistributedObject):
    notify = DirectNotifyGlobal.directNotify.newCategory('PurchaseManager')

    def __init__(self, cr):
        DistributedObject.DistributedObject.__init__(self, cr)
        self.playAgain = 0
        self.skillProfileDeltas: dict[int, PlayerSkillProfile] = {}

    def disable(self):
        DistributedObject.DistributedObject.disable(self)
        self.ignoreAll()

    def setPlayerIds(self, playerIds):
        self.notify.debug('setPlayerIds: %s' % (playerIds,))
        self.playerIds = playerIds

    def setNewbieIds(self, newbieIds):
        self.notify.debug('setNewbieIds: %s' % (newbieIds,))
        self.newbieIds = newbieIds

    def setMinigamePoints(self, mpArray):
        self.notify.debug('setMinigamePoints: %s' % (mpArray,))
        self.mpArray = mpArray

    def setPlayerMoney(self, moneyArray):
        self.notify.debug('setPlayerMoney: %s' % (moneyArray,))
        self.moneyArray = moneyArray

    def setPlayerStates(self, stateArray):
        self.notify.debug('setPlayerStates: %s' % (stateArray,))
        self.playerStates = stateArray
        if self.isGenerated() and self.hasLocalToon:
            self.announcePlayerStates()

    def setCountdown(self, timestamp):
        self.countdownTimestamp = timestamp

    def setSkillProfileDeltas(self, deltaArray):
        self.skillProfileDeltas.clear()
        for raw in deltaArray:
            profile = PlayerSkillProfile.from_astron(raw)
            self.skillProfileDeltas[profile.identifier] = profile

    def hasRankedResultData(self) -> bool:
        return len(self.skillProfileDeltas) > 0

    def announcePlayerStates(self):
        messenger.send('purchaseStateChange', [self.playerStates])

    def announceGenerate(self):
        DistributedObject.DistributedObject.announceGenerate(self)
        self.hasLocalToon = self.calcHasLocalToon()
        if self.hasLocalToon:
            self.announcePlayerStates()
            et = globalClockDelta.localElapsedTime(self.countdownTimestamp)
            remain = PURCHASE_COUNTDOWN_TIME - et
            self.acceptOnce('purchasePlayAgain', self.playAgainHandler)
            self.acceptOnce('purchaseBackToToontown', self.backToToontownHandler)
            self.acceptOnce('purchaseTimeout', self.setPurchaseExit)
            base.cr.playGame.hood.fsm.request('purchase', [self.mpArray,
             self.moneyArray,
             self.playerIds,
             self.playerStates,
             remain,
             self.skillProfileDeltas])

    def calcHasLocalToon(self):
        retval = base.localAvatar.doId in self.playerIds
        self.notify.debug('calcHasLocalToon returning %s' % retval)
        return retval

    def playAgainHandler(self):
        self.d_requestPlayAgain()

    def backToToontownHandler(self):
        self.notify.debug('requesting exit to toontown...')
        self.d_requestExit()
        self.playAgain = 0
        self.setPurchaseExit()

    def d_requestExit(self):
        self.sendUpdate('requestExit', [])

    def d_requestPlayAgain(self):
        self.notify.debug('requesting play again...')
        self.sendUpdate('requestPlayAgain', [])
        self.playAgain = 1

    def d_report(self):
        self.sendUpdate('report')

    def setPurchaseExit(self):
        base.localAvatar.setFancyNametag(base.localAvatar.getName())
        base.localAvatar.setColorProfile(color_profile.GRAY)
        if self.hasLocalToon:
            self.ignore('boughtGag')
            self.ignore('boughtGagFast')
            self.d_report()
            messenger.send('purchaseOver', [self.playAgain])
