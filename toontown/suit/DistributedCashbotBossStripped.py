from direct.directnotify import DirectNotifyGlobal
from direct.interval.IntervalGlobal import *
from panda3d.core import *
from panda3d.direct import *

from libotp import *
from toontown.coghq import CraneLeagueGlobals
from toontown.toonbase import TTLocalizer
from toontown.toonbase import ToontownGlobals
from . import SuitDNA
from .DistributedBossCogStripped import DistributedBossCogStripped

TTL = TTLocalizer
from toontown.coghq import BossHealthBar


class DistributedCashbotBossStripped(DistributedBossCogStripped):
    notify = DirectNotifyGlobal.directNotify.newCategory('DistributedCashbotBoss')

    def __init__(self, cr):
        super().__init__(cr)
        self.ruleset = CraneLeagueGlobals.CraneGameRuleset()  # Setup a default ruleset as a fallback
        self.modifiers = []
        self.warningSfx = None
        # By "heldObject", we mean the safe he's currently wearing as
        # a helmet, if any.  It's called a heldObject because this is
        # the way the cranes refer to the same thing, and we use the
        # same interface to manage this.
        self.heldObject = None

        self.latency = 0.5  # default latency for updating object posHpr
        self.stunEndTime = 0
        self.myHits = []
        self.tempHp = self.ruleset.CFO_MAX_HP
        self.processingHp = False
        return

    def announceGenerate(self):
        super().announceGenerate()

        # at this point all our attribs have been filled in.
        self.setName(TTLocalizer.CashbotBossName)
        nameInfo = TTLocalizer.BossCogNameWithDept % {'name': self._name,
                                                      'dept': SuitDNA.getDeptFullname(self.style.dept)}
        self.setDisplayName(nameInfo)

        # Our goal in this battle is to drop stuff on the CFO's head.
        # For this, we need a target.
        target = CollisionSphere(2, 0, 0, 3)
        targetNode = CollisionNode('headTarget')
        targetNode.addSolid(target)
        targetNode.setCollideMask(ToontownGlobals.PieBitmask)
        self.headTarget = self.neck.attachNewNode(targetNode)
        # self.headTarget.show()

        # And he gets a big bubble around his torso, just to keep
        # things from falling through him.  It's a big sphere so
        # things will tend to roll off him instead of landing on him.
        shield = CollisionSphere(0, 0, 0.8, 7)
        shieldNode = CollisionNode('shield')
        shieldNode.addSolid(shield)
        shieldNode.setCollideMask(ToontownGlobals.PieBitmask)
        self.pelvis.attachNewNode(shieldNode)

        self.eyes = loader.loadModel('phase_10/models/cogHQ/CashBotBossEyes.bam')

        # Get the eyes ready for putting outside the helmet.
        self.eyes.setPosHprScale(4.5, 0, -2.5, 90, 90, 0, 0.4, 0.4, 0.4)
        self.eyes.reparentTo(self.neck)
        self.eyes.hide()

    def delete(self):
        super().delete()
        self.ruleset = None

    def getBossMaxDamage(self):
        return self.ruleset.CFO_MAX_HP

    def setModifiers(self, mods):
        modsToSet = []  # A list of CFORulesetModifierBase subclass instances
        for modStruct in mods:
            modsToSet.append(CraneLeagueGlobals.CFORulesetModifierBase.fromStruct(modStruct))

        self.modifiers = modsToSet
        self.modifiers.sort(key=lambda m: m.MODIFIER_TYPE)

    def setBossDamage(self, bossDamage, avId=0, objId=0, isGoon=False, isDOT=False):

        if avId != base.localAvatar.doId or isGoon or (objId not in self.myHits):
            if bossDamage > self.bossDamage:
                delta = bossDamage - self.bossDamage
                
                if not isDOT:
                    self.flashRed()

                # Animate the hit if the CFO should flinch
                if self.ruleset.CFO_FLINCHES_ON_HIT and not isDOT:
                    self.doAnimate('hit', now=1)

                self.showHpText(-delta, scale=5)

        if objId in self.myHits:
            self.myHits.remove(objId)

        self.bossDamage = bossDamage
        self.updateHealthBar()
        self.bossHealthBar.update(self.ruleset.CFO_MAX_HP - bossDamage, self.ruleset.CFO_MAX_HP)
        self.processingHp = False
        self.tempHp = self.ruleset.CFO_MAX_HP - self.bossDamage

    def prepareBossForBattle(self):
        if self.bossHealthBar:
            self.bossHealthBar.cleanup()
            self.bossHealthBar = BossHealthBar.BossHealthBar(self.style.dept)

        self.cleanupIntervals()

        self.clearChat()
        self.reparentTo(render)

        self.setPosHpr(*ToontownGlobals.CashbotBossBattleThreePosHpr)

        self.happy = 1
        self.raised = 1
        self.forward = 1
        self.doAnimate()

        self.generateHealthBar()
        self.updateHealthBar()

        # Display Health Bar
        self.bossHealthBar.initialize(self.ruleset.CFO_MAX_HP - self.bossDamage, self.ruleset.CFO_MAX_HP)
        if self.ruleset.CFO_MAX_HP > 999_999 and self.ruleset.TIMER_MODE:
            self.bossHealthBar.hide()

    def cleanupBossBattle(self):
        self.cleanupIntervals()
        self.stopAnimate()
        self.cleanupAttacks()
        self.setDizzy(0)
        self.removeHealthBar()

    def saySomething(self, chatString):
        intervalName = 'CFOTaunt'
        seq = Sequence(name=intervalName)
        seq.append(Func(self.setChatAbsolute, chatString, CFSpeech))
        seq.append(Wait(4.0))
        seq.append(Func(self.clearChat))
        oldSeq = self.activeIntervals.get(intervalName)
        if oldSeq:
            oldSeq.finish()
        seq.start()
        self.storeInterval(seq, intervalName)

    def setAttackCode(self, attackCode, avId=0, delayTime=0):
        super().setAttackCode(attackCode, avId)

        if attackCode == ToontownGlobals.BossCogAreaAttack:
            self.saySomething(TTLocalizer.CashbotBossAreaAttackTaunt)
            base.playSfx(self.warningSfx)

        if attackCode in (ToontownGlobals.BossCogDizzy, ToontownGlobals.BossCogDizzyNow):
            self.stunEndTime = globalClock.getFrameTime() + delayTime
        else:
            self.stunEndTime = 0

    def localToonDied(self):
        super().localToonDied()
        self.localToonIsSafe = 1

    def grabObject(self, obj):
        # Grab a safe and put it on as a helmet.  This method mirrors
        # a similar method on DistributedCashbotBossCrane.py; it goes
        # through the same API as a crane picking up a safe.

        # This is only called by DistributedCashbotBossObject.enterGrabbed().
        obj.wrtReparentTo(self.neck)
        obj.hideShadows()
        obj.stashCollisions()
        if obj.lerpInterval:
            obj.lerpInterval.finish()
        obj.lerpInterval = Parallel(obj.posInterval(ToontownGlobals.CashbotBossToMagnetTime, Point3(-1, 0, 0.2)),
                                    obj.quatInterval(ToontownGlobals.CashbotBossToMagnetTime, VBase3(0, -90, 90)),
                                    Sequence(Wait(ToontownGlobals.CashbotBossToMagnetTime), ShowInterval(self.eyes)),
                                    obj.toMagnetSoundInterval)
        obj.lerpInterval.start()
        self.heldObject = obj

    def dropObject(self, obj):
        # Drop a helmet on the ground.

        # This is only called by DistributedCashbotBossObject.exitGrabbed().
        assert self.heldObject == obj

        if obj.lerpInterval:
            obj.lerpInterval.finish()
            obj.lerpInterval = None

        obj = self.heldObject
        obj.wrtReparentTo(render)
        obj.setHpr(obj.getH(), 0, 0)
        self.eyes.hide()

        # Actually, we shouldn't reveal the shadows until it
        # reaches the ground again.  This will do for now.
        obj.showShadows()
        obj.unstashCollisions()

        self.heldObject = None

    def setRuleset(self, ruleset):
        self.ruleset = ruleset
        self.bossHealthBar.update(self.ruleset.CFO_MAX_HP - self.bossDamage, self.ruleset.CFO_MAX_HP)
    
    def setAnimationSpeed(self, speed):
        """Set the animation playback speed for all boss animations"""
        # Store the speed for future animations
        if not hasattr(self, 'animationSpeed'):
            self.animationSpeed = 1.0
        self.animationSpeed = speed
        
        # Apply speed to current animation if one is playing
        if hasattr(self, 'currentAnimIval') and self.currentAnimIval:
            # Modify the playback rate of the current animation interval
            self.currentAnimIval.setPlayRate(speed)
    
    def getAnim(self, anim):
        """Override to apply animation speed to all animations"""
        # Get the normal animation interval
        ival = super().getAnim(anim)
        
        # Apply current animation speed if we have one
        if hasattr(self, 'animationSpeed') and self.animationSpeed != 1.0:
            self._applySpeedToInterval(ival)
        
        return ival
    
    def getAngryActorInterval(self, animName, **kw):
        """Override to apply animation speed to angry animations"""
        # Apply current animation speed to the keyword arguments
        if hasattr(self, 'animationSpeed') and self.animationSpeed != 1.0:
            kw['playRate'] = kw.get('playRate', 1.0) * self.animationSpeed
        
        # Call the parent method with modified kwargs
        return super().getAngryActorInterval(animName, **kw)
    
    def _applySpeedToInterval(self, ival):
        """Recursively apply animation speed to all ActorIntervals in a complex interval"""
        from direct.interval.ActorInterval import ActorInterval
        from direct.interval.MetaInterval import Sequence, Parallel
        
        if isinstance(ival, ActorInterval):
            # Apply speed directly to ActorInterval
            ival.setPlayRate(self.animationSpeed)
        elif isinstance(ival, (Sequence, Parallel)):
            # Access child intervals using the ivals attribute
            if hasattr(ival, 'ivals') and ival.ivals:
                for child in ival.ivals:
                    self._applySpeedToInterval(child)