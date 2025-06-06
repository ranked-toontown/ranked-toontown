import math
import random
import time

from direct.directnotify import DirectNotifyGlobal
from direct.fsm import FSM
from direct.task.TaskManagerGlobal import taskMgr

from toontown.coghq import CraneLeagueGlobals
from toontown.coghq import DistributedCashbotBossSideCraneAI
from toontown.coghq.CashbotBossComboTracker import CashbotBossComboTracker
from toontown.toonbase import ToontownGlobals
from .DistributedBossCogStrippedAI import DistributedBossCogStrippedAI
from toontown.minigame.statuseffects.StatusEffectGlobals import StatusEffect, STATUS_EFFECT_DURATIONS


class DistributedCashbotBossStrippedAI(DistributedBossCogStrippedAI, FSM.FSM):
    notify = DirectNotifyGlobal.directNotify.newCategory('DistributedCashbotBossAI')

    def __init__(self, air, game):
        DistributedBossCogStrippedAI.__init__(self, air, game, 'm')
        FSM.FSM.__init__(self, 'DistributedCashbotBossAI')

        self.game = game

        self.ruleset = CraneLeagueGlobals.CraneGameRuleset()
        self.rulesetFallback = self.ruleset  # A fallback ruleset for when we rcr, or change mods mid round
        self.oldMaxLaffs = {}
        self.heldObject = None
        self.waitingForHelmet = 0

        # Some overrides from commands
        self.doTimer = None  # If true, make timer run down instead of count up, modified from a command, if false, count up, if none, use the rule
        self.timerOverride = self.ruleset.TIMER_MODE_TIME_LIMIT  # Amount of time to override in seconds

        # Map of damage multipliers for toons
        self.toonDmgMultipliers = {}

        # The index order to spawn toons
        self.toonSpawnpointOrder = [i for i in range(16)]

        # The intentional safe helmet cooldowns. These are used to prevent safe helmet abuse.
        # Maps toon id -> next available safe helmet timestamp.
        self.safeHelmetCooldownsDict: dict[int, float] = {}
        
        # Status effect tracking - support multiple instances from different players
        self.activeStatusEffectTasks = {}  # Maps (statusEffect, avId) -> taskName for cleanup
        self.statusEffectCounters = {}  # Maps statusEffect -> counter for unique task naming
        
        # Damage vulnerability from SHATTERED status effect
        self.damageVulnerable = False
        
        # Burn damage tracking for explosion calculation
        self.burnDataTracking = {}  # Maps taskKey -> {appliedByAvId, ticksRemaining}
        
        # Captured DOT damage for synergy explosions
        self.capturedDotDamageForExplosion = None

    def allowedToSafeHelmet(self, toonId: int) -> bool:
        if toonId not in self.safeHelmetCooldownsDict:
            return True

        allowedToSafeHelmetTimestamp = self.safeHelmetCooldownsDict[toonId]
        if time.time() >= allowedToSafeHelmetTimestamp:
            return True

        return False

    def addSafeHelmetCooldown(self, toonId: int):
        self.safeHelmetCooldownsDict[toonId] = time.time() + self.ruleset.SAFE_HELMET_COOLDOWN

    def clearSafeHelmetCooldowns(self):
        self.safeHelmetCooldownsDict.clear()

    def getToonOutgoingMultiplier(self, avId):
        n = self.toonDmgMultipliers.get(avId)
        if not n:
            n = 100
            self.toonDmgMultipliers[avId] = n

        return n

    # Clears all current modifiers and restores the ruleset before modifiers were applied
    def resetModifiers(self):
        self.modifiers = []
        self.ruleset = self.rulesetFallback
        self.d_setRawRuleset()

    def getRawRuleset(self):
        return self.ruleset.asStruct()

    def getRuleset(self):
        return self.ruleset

    def setRuleset(self, ruleset):
        self.ruleset = ruleset

    def doNextAttack(self, task):
        # Choose an attack and do it.

        # Make sure we're waiting for a helmet.
        if self.heldObject is None and not self.waitingForHelmet:
            self.waitForNextHelmet()

        # Rare chance to do a jump attack if we want it
        if self.ruleset.WANT_CFO_JUMP_ATTACK:
            if random.randint(0, 99) < self.ruleset.CFO_JUMP_ATTACK_CHANCE:
                self.__doAreaAttack()
                return

        # Do a directed attack.
        self.__doDirectedAttack()

    def __findEligibleTargets(self):
        """
        Create a list of DistributedToonAI objects that are valid to be targeted for a gear throw.
        Returns an empty list if there are none.
        """

        if self.game is None:
            return []

        return self.game.getParticipantIdsNotSpectating()

    def __doDirectedAttack(self):

        # Choose the next toon in line to get the assault.
        targets = self.__findEligibleTargets()
        # Check if we ran out of targets, if so reset the list back to everyone involved
        if len(self.toonsToAttack) <= 0:
            self.toonsToAttack = list(targets)
            # Shuffle the toons if we want random gear throws
            if self.ruleset.RANDOM_GEAR_THROW_ORDER:
                random.shuffle(self.toonsToAttack)

            # remove people who are dead or gone
            for toonId in self.toonsToAttack[:]:
                toon = self.air.doId2do.get(toonId)
                if not toon or toon.getHp() <= 0:
                    self.toonsToAttack.remove(toonId)

        # are there no valid targets even after resetting? i.e. is everyone sad
        if len(self.toonsToAttack) <= 0:
            self.b_setAttackCode(ToontownGlobals.BossCogNoAttack)
            return

        # pop toon off list and set as target
        toonToAttack = self.toonsToAttack.pop(0)
        # is toon here and alive? if not skip over and try the next toon
        toon = self.air.doId2do.get(toonToAttack)
        if not toon or toon.getHp() <= 0:
            return self.__doDirectedAttack()  # next toon

        # we have a toon to attack
        self.b_setAttackCode(ToontownGlobals.BossCogSlowDirectedAttack, toonToAttack)

    def __doAreaAttack(self):
        self.b_setAttackCode(ToontownGlobals.BossCogAreaAttack)

    def setAttackCode(self, attackCode, avId=0):
        self.attackCode = attackCode
        self.attackAvId = avId

        if attackCode in (ToontownGlobals.BossCogDizzy, ToontownGlobals.BossCogDizzyNow):
            delayTime = self.game.progressValue(20, 5)
            if self.game.practiceCheatHandler.wantAlwaysStunned:
                delayTime = 3600
            self.hitCount = 0
        elif attackCode in (ToontownGlobals.BossCogSlowDirectedAttack,):
            delayTime = ToontownGlobals.BossCogAttackTimes.get(attackCode)
            delayTime += self.game.progressValue(10, 0)
        elif attackCode in (ToontownGlobals.BossCogAreaAttack,):
            delayTime = self.game.progressValue(20, 9)
        else:
            delayTime = ToontownGlobals.BossCogAttackTimes.get(attackCode, 5.0)

        self.waitForNextAttack(delayTime)
        return

    def d_setAttackCode(self, attackCode, avId=0, delayTime=0):
        self.sendUpdate('setAttackCode', [attackCode, avId, delayTime])

    def b_setAttackCode(self, attackCode, avId=0, delayTime=0):
        self.d_setAttackCode(attackCode, avId, delayTime=delayTime)
        self.setAttackCode(attackCode, avId)

    def getDamageMultiplier(self, allowFloat=False):
        mult = self.game.progressValue(1, self.ruleset.CFO_ATTACKS_MULTIPLIER + (0 if allowFloat else 1))
        if not allowFloat:
            mult = int(mult)
        return mult

    def zapToon(self, x, y, z, h, p, r, bpx, bpy, attackCode, timestamp):

        avId = self.air.getAvatarIdFromSender()
        if not self.validate(avId, avId in self.game.getParticipants(), 'zapToon from unknown avatar'):
            return

        if self.game.isSpectating(avId):
            return

        toon = simbase.air.doId2do.get(avId)
        if not toon:
            return

        # Is the cfo stunned?
        isStunned = self.attackCode == ToontownGlobals.BossCogDizzy
        # Are we setting to swat?
        if isStunned and attackCode == ToontownGlobals.BossCogElectricFence:
            self.game.addScore(avId, self.game.ruleset.POINTS_PENALTY_UNSTUN, reason=CraneLeagueGlobals.UNSTUN)

        self.d_showZapToon(avId, x, y, z, h, p, r, attackCode, timestamp)

        damage = self.ruleset.CFO_ATTACKS_BASE_DAMAGE.get(attackCode)
        if damage == None:
            self.notify.warning('No damage listed for attack code %s' % attackCode)
            damage = 5
            raise KeyError('No damage listed for attack code %s' % attackCode)  # temp

        damage *= self.getDamageMultiplier(allowFloat=self.ruleset.CFO_ATTACKS_MULTIPLIER_INTERPOLATE)
        # Clamp the damage to make sure it at least does 1
        damage = max(int(damage), 1)

        self.game.damageToon(toon, damage)

        if attackCode == ToontownGlobals.BossCogElectricFence:
            if bpy < 0 and abs(bpx / bpy) > 0.5:
                if self.ruleset.WANT_UNSTUNS:
                    if bpx < 0:
                        self.b_setAttackCode(ToontownGlobals.BossCogSwatRight)
                    else:
                        self.b_setAttackCode(ToontownGlobals.BossCogSwatLeft)

    def waitForNextHelmet(self):
        if self.ruleset.DISABLE_SAFE_HELMETS:
            return
        taskName = self.uniqueName('NextHelmet')
        taskMgr.remove(taskName)
        delayTime = self.game.progressValue(45, 15)
        taskMgr.doMethodLater(delayTime, self.donHelmet, taskName)
        self.waitingForHelmet = 1

    def donHelmet(self, task):

        if self.ruleset.DISABLE_SAFE_HELMETS:
            return

        self.waitingForHelmet = 0
        if self.heldObject == None:
            # Ok, the boss wants to put on a helmet now.  He can have
            # his special safe 0, which was created for just this
            # purpose.
            safe = self.game.safes[0]
            safe.request('Grabbed', self.doId, self.doId)
            self.heldObject = safe

    def stopHelmets(self):
        self.waitingForHelmet = 0
        taskName = self.uniqueName('NextHelmet')
        taskMgr.remove(taskName)

    # Given a crane, the damage dealt from the crane, and the impact of the hit, should we stun the CFO?
    def considerStun(self, crane, damage, impact):
        # If frozen, don't allow stunning (frozen acts like a stun state)
        if self.isFrozen():
            # Frozen boss can't be stunned further, just take damage
            return False

        damage_stuns = damage >= self.ruleset.CFO_STUN_THRESHOLD
        is_sidecrane = isinstance(crane, DistributedCashbotBossSideCraneAI.DistributedCashbotBossSideCraneAI)
        hard_hit = impact >= self.ruleset.SIDECRANE_IMPACT_STUN_THRESHOLD

        if self.game.practiceCheatHandler.wantStunning:
            return True

        if self.game.practiceCheatHandler.wantNoStunning:
            return False

        # Is the damage enough?
        if damage_stuns:
            return True

        # Was this a knarbuckle sidecrane hit?
        if is_sidecrane and hard_hit:
            return True

        return False

    def b_setBossDamage(self, bossDamage, avId=0, objId=0, isGoon=False, isDOT=False):
        self.d_setBossDamage(bossDamage, avId=avId, objId=objId, isGoon=isGoon, isDOT=isDOT)
        self.setBossDamage(bossDamage)

    def setBossDamage(self, bossDamage):
        self.reportToonHealth()
        self.bossDamage = bossDamage

    def d_setBossDamage(self, bossDamage, avId=0, objId=0, isGoon=False, isDOT=False):
        self.sendUpdate('setBossDamage', [bossDamage, avId, objId, isGoon, isDOT])

    def waitForNextAttack(self, delayTime):
        DistributedBossCogStrippedAI.waitForNextAttack(self, delayTime)

    def prepareBossForBattle(self):
        # Force unstun the CFO if he was stunned in a previous Battle Three round
        if self.attackCode == ToontownGlobals.BossCogDizzy or self.attackCode == ToontownGlobals.BossCogDizzyNow:
            self.b_setAttackCode(ToontownGlobals.BossCogNoAttack)

        # It's important to set our position correctly even on the AI,
        # so the goons can orient to the center of the room.
        self.setPosHpr(*ToontownGlobals.CashbotBossBattleThreePosHpr)

        # A list of toons to attack.  We start out with the list in
        # random order.
        self.toonsToAttack = []

        if self.ruleset.RANDOM_GEAR_THROW_ORDER:
            random.shuffle(self.toonsToAttack)

        self.b_setBossDamage(0)
        self.battleThreeStart = globalClock.getFrameTime()
        self.waitForNextAttack(15)
        self.waitForNextHelmet()

        self.oldMaxLaffs = {}
        self.toonDmgMultipliers = {}

        self.toonsWon = False

    def cleanupBossBattle(self):
        self.stopAttacks()
        self.stopHelmets()
        self.heldObject = None
        self.cleanupStatusEffectTasks()

    def __restartCraneRoundTask(self, task):
        self.exitIntroduction()
        self.b_setState('PrepareBattleThree')
        self.b_setState('BattleThree')

    def setObjectID(self, objId):
        self.objectId = objId
    
    def cleanupStatusEffectTasks(self):
        """Clean up all active status effect tasks"""
        for taskName in self.activeStatusEffectTasks.values():
            taskMgr.remove(taskName)
        self.activeStatusEffectTasks.clear()
        self.statusEffectCounters.clear()
        self.burnDataTracking.clear()
        self.capturedDotDamageForExplosion = None
        
        # If frozen, unfreeze before cleanup
        if self.isFrozen():
            self.d_setFrozenState(False)
        
        # If vulnerable to damage, remove vulnerability before cleanup
        if self.isVulnerableToDamage():
            self.removeDamageVulnerability()
    
    def onStatusEffectApplied(self, statusEffect, appliedByAvId):
        """Called when a status effect is applied to this boss"""
        
        if statusEffect == StatusEffect.BURNED:
            self.startBurnedEffect(appliedByAvId)
        elif statusEffect == StatusEffect.DRENCHED:
            self.startDrenchedEffect(appliedByAvId)
        elif statusEffect == StatusEffect.FROZEN:
            self.startFrozenEffect(appliedByAvId)
        elif statusEffect == StatusEffect.SHATTERED:
            self.startShatteredEffect(appliedByAvId)
        elif statusEffect == StatusEffect.EXPLODE:
            self.startExplodeEffect(appliedByAvId)
        # Add other status effects here as we implement them
    
    def onStatusEffectRemoved(self, statusEffect):
        """Called when a status effect is removed from this boss"""
        
        if statusEffect == StatusEffect.BURNED:
            self.stopOldestBurnedEffect()
        elif statusEffect == StatusEffect.DRENCHED:
            self.stopOldestDrenchedEffect()
        elif statusEffect == StatusEffect.FROZEN:
            self.stopOldestFrozenEffect()
        elif statusEffect == StatusEffect.SHATTERED:
            self.stopOldestShatteredEffect()
        elif statusEffect == StatusEffect.EXPLODE:
            self.stopOldestExplodeEffect()
        # Add other status effects here as we implement them
    
    def startBurnedEffect(self, appliedByAvId):
        """Start the BURNED status effect DOT"""
        
        # Create a unique task for this player's burn effect
        # Get a counter for unique naming
        counter = self.statusEffectCounters.get(StatusEffect.BURNED, 0)
        self.statusEffectCounters[StatusEffect.BURNED] = counter + 1
        
        taskName = self.uniqueName(f'burnedDOT-{appliedByAvId}-{counter}')
        taskKey = (StatusEffect.BURNED, appliedByAvId, counter)
        self.activeStatusEffectTasks[taskKey] = taskName
        
        # Store burn data for explosion calculation
        self.burnDataTracking[taskKey] = {
            'appliedByAvId': appliedByAvId,
            'ticksRemaining': 10
        }
        
        # Start the DOT task with player-specific data stored in the task
        task = taskMgr.doMethodLater(0.5, self.doBurnTick, taskName)
        task.burnData = {
            'appliedByAvId': appliedByAvId,
            'ticksRemaining': 10,
            'taskKey': taskKey
        }
    
    def doBurnTick(self, task):
        """Apply one tick of burn damage"""
        burnData = task.burnData
        taskKey = burnData['taskKey']
        
        # Check if this burn effect has been removed/canceled
        if taskKey not in self.burnDataTracking:
            # This burn effect was removed, stop ticking
            return task.done
        
        if burnData['ticksRemaining'] <= 0:
            # Clean up this specific burn effect
            self.cleanupBurnTask(taskKey)
            return task.done
        
        # Apply 3 damage to the boss (marked as DOT to prevent flinching/combos)
        damage = 3
        appliedByAvId = burnData['appliedByAvId']
        
        # Use isDOT=True to prevent flinching and combo credit
        self.game.recordHit(damage, impact=0, craneId=0, objId=0, isGoon=False, isDOT=True)
        
        burnData['ticksRemaining'] -= 1
        
        # Update tracking data
        if taskKey in self.burnDataTracking:
            self.burnDataTracking[taskKey]['ticksRemaining'] = burnData['ticksRemaining']
        
        # Schedule next tick if we have more remaining
        if burnData['ticksRemaining'] > 0:
            return task.again
        else:
            # Clean up when done
            self.cleanupBurnTask(taskKey)
            return task.done
    
    def cleanupBurnTask(self, taskKey):
        """Clean up a specific burn task"""
        if taskKey in self.activeStatusEffectTasks:
            taskName = self.activeStatusEffectTasks[taskKey]
            taskMgr.remove(taskName)
            del self.activeStatusEffectTasks[taskKey]
        
        # Also clean up tracking data
        if taskKey in self.burnDataTracking:
            del self.burnDataTracking[taskKey]
    
    def stopOldestBurnedEffect(self):
        """Stop the oldest BURNED status effect DOT when one is removed from the system"""
        # Find the oldest burn task and stop it
        burnTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.BURNED]
        if burnTasks:
            # Sort by counter (the third element) to get the oldest
            oldestTask = min(burnTasks, key=lambda x: x[2])
            self.cleanupBurnTask(oldestTask)
    
    def startDrenchedEffect(self, appliedByAvId):
        """Start the DRENCHED status effect - slows boss animations"""
        # Create a unique task for this player's drench effect
        counter = self.statusEffectCounters.get(StatusEffect.DRENCHED, 0)
        self.statusEffectCounters[StatusEffect.DRENCHED] = counter + 1
        
        taskName = self.uniqueName(f'drenchedEffect-{appliedByAvId}-{counter}')
        taskKey = (StatusEffect.DRENCHED, appliedByAvId, counter)
        self.activeStatusEffectTasks[taskKey] = taskName
        
        # Apply animation slowdown immediately
        self.applyAnimationSlowdown()
        
        # Get duration from globals (8 seconds for DRENCHED)
        duration = STATUS_EFFECT_DURATIONS.get(StatusEffect.DRENCHED, 8.0)
        
        # Set up cleanup task
        drenchData = {
            'appliedByAvId': appliedByAvId,
            'taskKey': taskKey
        }
        
        task = taskMgr.doMethodLater(duration, self.endDrenchedEffect, taskName)
        task.drenchData = drenchData
    
    def endDrenchedEffect(self, task):
        """End a specific DRENCHED status effect"""
        # Get the drenchData from the task itself
        drenchData = task.drenchData
        
        self.cleanupDrenchTask(drenchData['taskKey'])
        
        # Check if this was the last drench effect - if so, restore animation speed
        drenchTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.DRENCHED]
        if len(drenchTasks) == 0:
            self.removeAnimationSlowdown()
        
        return task.done
    
    def cleanupDrenchTask(self, taskKey):
        """Clean up a specific drench task"""
        if taskKey in self.activeStatusEffectTasks:
            taskName = self.activeStatusEffectTasks[taskKey]
            taskMgr.remove(taskName)
            del self.activeStatusEffectTasks[taskKey]
    
    def stopOldestDrenchedEffect(self):
        """Stop the oldest DRENCHED status effect when one is removed from the system"""
        # Find the oldest drench task and stop it
        drenchTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.DRENCHED]
        if drenchTasks:
            # Sort by counter (the third element) to get the oldest
            oldestTask = min(drenchTasks, key=lambda x: x[2])
            self.cleanupDrenchTask(oldestTask)
            
            # Check if this was the last drench effect - if so, restore animation speed
            remainingDrenchTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.DRENCHED]
            if len(remainingDrenchTasks) == 0:
                self.removeAnimationSlowdown()
    
    def applyAnimationSlowdown(self):
        """Apply animation speed slowdown to the boss"""
        # Send to client to slow down animations
        self.d_setAnimationSpeed(0.5)  # 50% speed
    
    def removeAnimationSlowdown(self):
        """Remove animation speed slowdown from the boss"""
        # Send to client to restore normal animation speed
        self.d_setAnimationSpeed(1.0)  # Normal speed
    
    def d_setAnimationSpeed(self, speed):
        """Send animation speed change to clients"""
        self.sendUpdate('setAnimationSpeed', [speed])
    
    def startFrozenEffect(self, appliedByAvId):
        """Start the FROZEN status effect - completely immobilizes the boss"""
        # Create a unique task for this player's frozen effect
        counter = self.statusEffectCounters.get(StatusEffect.FROZEN, 0)
        self.statusEffectCounters[StatusEffect.FROZEN] = counter + 1
        
        taskName = self.uniqueName(f'frozenEffect-{appliedByAvId}-{counter}')
        taskKey = (StatusEffect.FROZEN, appliedByAvId, counter)
        self.activeStatusEffectTasks[taskKey] = taskName
        
        # End any existing stuns and transition to frozen state
        self.endExistingStuns()
        self.applyFrozenState()
        
        # Get duration from globals (10 seconds for FROZEN)
        duration = STATUS_EFFECT_DURATIONS.get(StatusEffect.FROZEN, 10.0)
        
        # Set up cleanup task
        frozenData = {
            'appliedByAvId': appliedByAvId,
            'taskKey': taskKey
        }
        
        task = taskMgr.doMethodLater(duration, self.endFrozenEffect, taskName)
        task.frozenData = frozenData
    
    def endFrozenEffect(self, task):
        """End a specific FROZEN status effect"""
        # Get the frozenData from the task itself
        frozenData = task.frozenData
        
        self.cleanupFrozenTask(frozenData['taskKey'])
        
        # Check if this was the last frozen effect - if so, unfreeze
        frozenTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.FROZEN]
        if len(frozenTasks) == 0:
            self.removeFrozenState()
        
        return task.done
    
    def cleanupFrozenTask(self, taskKey):
        """Clean up a specific frozen task"""
        if taskKey in self.activeStatusEffectTasks:
            taskName = self.activeStatusEffectTasks[taskKey]
            taskMgr.remove(taskName)
            del self.activeStatusEffectTasks[taskKey]
    
    def stopOldestFrozenEffect(self):
        """Stop the oldest FROZEN status effect when one is removed from the system"""
        # Find the oldest frozen task and stop it
        frozenTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.FROZEN]
        if frozenTasks:
            # Sort by counter (the third element) to get the oldest
            oldestTask = min(frozenTasks, key=lambda x: x[2])
            self.cleanupFrozenTask(oldestTask)
            
            # Check if this was the last frozen effect - if so, unfreeze
            remainingFrozenTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.FROZEN]
            if len(remainingFrozenTasks) == 0:
                self.removeFrozenState()
    
    def endExistingStuns(self):
        """End any existing stun effects when frozen is applied"""
        from toontown.toonbase import ToontownGlobals
        if self.attackCode == ToontownGlobals.BossCogDizzy or self.attackCode == ToontownGlobals.BossCogDizzyNow:
            # End the stun
            self.b_setAttackCode(ToontownGlobals.BossCogNoAttack)
    
    def applyFrozenState(self):
        """Apply the frozen state to the boss"""
        from toontown.toonbase import ToontownGlobals
        
        # Store the previous state for recovery
        if not hasattr(self, 'preFreezeBossState'):
            self.preFreezeBossState = {
                'attackCode': self.attackCode,
                'wasAttacking': hasattr(self, 'numAttacks') and self.numAttacks > 0
            }
        
        # Don't use dizzy state - just mark as frozen and stop actions
        # The frozen state itself will handle safe vulnerability
        
        # Stop attacks and goon spawning
        self.stopAttacks()
        self.stopHelmets()
        
        # Freeze animations on client
        self.d_setFrozenState(True)
    
    def removeFrozenState(self):
        """Remove the frozen state from the boss"""
        from toontown.toonbase import ToontownGlobals
        
        # Restore previous state
        if hasattr(self, 'preFreezeBossState'):
            # Unfreeze animations on client first
            self.d_setFrozenState(False)
            
            # If the boss was attacking before being frozen, resume attacks
            if self.preFreezeBossState.get('wasAttacking', False):
                self.b_setAttackCode(ToontownGlobals.BossCogNoAttack)
                self.waitForNextAttack(2.0)  # Brief delay before resuming
                self.waitForNextHelmet()
            else:
                self.b_setAttackCode(ToontownGlobals.BossCogNoAttack)
            
            del self.preFreezeBossState
    
    def d_setFrozenState(self, frozen):
        """Send frozen state change to clients"""
        self.sendUpdate('setFrozenState', [frozen])
    
    def isFrozen(self):
        """Check if the boss is currently frozen"""
        frozenTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.FROZEN]
        return len(frozenTasks) > 0
    
    def isVulnerableToSafes(self):
        """Check if the boss is vulnerable to safe damage (dizzy OR frozen)"""
        from toontown.toonbase import ToontownGlobals
        return (self.attackCode == ToontownGlobals.BossCogDizzy or 
                self.attackCode == ToontownGlobals.BossCogDizzyNow or 
                self.isFrozen())
    
    def startShatteredEffect(self, appliedByAvId):
        """Start the SHATTERED status effect - re-stuns boss and applies 25% damage vulnerability"""
        # Create a unique task for this player's shattered effect
        counter = self.statusEffectCounters.get(StatusEffect.SHATTERED, 0)
        self.statusEffectCounters[StatusEffect.SHATTERED] = counter + 1
        
        taskName = self.uniqueName(f'shatteredEffect-{appliedByAvId}-{counter}')
        taskKey = (StatusEffect.SHATTERED, appliedByAvId, counter)
        self.activeStatusEffectTasks[taskKey] = taskName
        
        # Re-stun the boss (back to Dizzy)
        from toontown.toonbase import ToontownGlobals
        self.b_setAttackCode(ToontownGlobals.BossCogDizzy)
        
        # Apply damage vulnerability immediately
        self.applyDamageVulnerability()
        
        # Get duration from globals (4 seconds for SHATTERED)
        duration = STATUS_EFFECT_DURATIONS.get(StatusEffect.SHATTERED, 4.0)
        
        # Set up cleanup task
        shatteredData = {
            'appliedByAvId': appliedByAvId,
            'taskKey': taskKey
        }
        
        task = taskMgr.doMethodLater(duration, self.endShatteredEffect, taskName)
        task.shatteredData = shatteredData
    
    def endShatteredEffect(self, task):
        """End a specific SHATTERED status effect"""
        # Get the shatteredData from the task itself
        shatteredData = task.shatteredData
        
        self.cleanupShatteredTask(shatteredData['taskKey'])
        
        # Check if this was the last shattered effect - if so, remove vulnerability
        shatteredTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.SHATTERED]
        if len(shatteredTasks) == 0:
            self.removeDamageVulnerability()
        
        return task.done
    
    def cleanupShatteredTask(self, taskKey):
        """Clean up a specific shattered task"""
        if taskKey in self.activeStatusEffectTasks:
            taskName = self.activeStatusEffectTasks[taskKey]
            taskMgr.remove(taskName)
            del self.activeStatusEffectTasks[taskKey]
    
    def stopOldestShatteredEffect(self):
        """Stop the oldest SHATTERED status effect when one is removed from the system"""
        # Find the oldest shattered task and stop it
        shatteredTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.SHATTERED]
        if shatteredTasks:
            # Sort by counter (the third element) to get the oldest
            oldestTask = min(shatteredTasks, key=lambda x: x[2])
            self.cleanupShatteredTask(oldestTask)
            
            # Check if this was the last shattered effect - if so, remove vulnerability
            remainingShatteredTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.SHATTERED]
            if len(remainingShatteredTasks) == 0:
                self.removeDamageVulnerability()
    
    def applyDamageVulnerability(self):
        """Apply 25% damage vulnerability to the boss"""
        # Set the damage vulnerability flag
        self.damageVulnerable = True
    
    def removeDamageVulnerability(self):
        """Remove damage vulnerability from the boss"""
        # Remove the damage vulnerability flag
        self.damageVulnerable = False
    
    def isVulnerableToDamage(self):
        """Return True if the boss takes increased damage (shattered)"""
        return getattr(self, 'damageVulnerable', False)
    
    def setCapturedDotDamageForExplosion(self, dotDamageByPlayer):
        """Store captured DOT damage for use by explosion synergy"""
        self.capturedDotDamageForExplosion = dotDamageByPlayer
    
    def startExplodeEffect(self, appliedByAvId):
        """Start the EXPLODE status effect - detonates after delay dealing damage"""
        # Create unique tasks for this player's explode effect
        counter = self.statusEffectCounters.get(StatusEffect.EXPLODE, 0)
        self.statusEffectCounters[StatusEffect.EXPLODE] = counter + 1
        
        # Use captured DOT damage if available (from synergy), otherwise capture it now
        dotDamageByPlayer = {}
        if self.capturedDotDamageForExplosion is not None:
            # Use the pre-captured DOT damage from synergy
            dotDamageByPlayer = self.capturedDotDamageForExplosion
            self.capturedDotDamageForExplosion = None  # Clear it after use
            self.notify.warning(f'Using pre-captured DOT damage from synergy: {dotDamageByPlayer}')
        else:
            self.notify.warning(f'No pre-captured DOT damage, capturing now. Active burns: {list(self.burnDataTracking.keys())}')
            # Capture remaining DOT damage immediately before DOTs are removed
            dotsToRemove = []  # List of (taskKey, appliedByAvId, remainingDamage) to remove
            
            # Check all active burn effects using our tracking data
            for taskKey, burnData in list(self.burnDataTracking.items()):
                statusEffect, dotAppliedByAvId, burnCounter = taskKey
                
                if statusEffect == StatusEffect.BURNED:
                    ticksRemaining = burnData['ticksRemaining']
                    remainingDamage = ticksRemaining * 3  # 3 damage per tick
                    
                    # Track damage by player
                    if dotAppliedByAvId not in dotDamageByPlayer:
                        dotDamageByPlayer[dotAppliedByAvId] = 0
                    dotDamageByPlayer[dotAppliedByAvId] += remainingDamage
                    
                    # Mark for removal
                    dotsToRemove.append((taskKey, dotAppliedByAvId, remainingDamage))
            
            # Remove all DOT effects (explosion will consume them)
            for taskKey, dotAppliedByAvId, remainingDamage in dotsToRemove:
                self.cleanupBurnTask(taskKey)
        
        # Task for DOT consumption at 0.75 seconds
        dotTaskName = self.uniqueName(f'explodeDOT-{appliedByAvId}-{counter}')
        dotTaskKey = (StatusEffect.EXPLODE, appliedByAvId, counter, 'DOT')
        self.activeStatusEffectTasks[dotTaskKey] = dotTaskName
        
        # Task for base explosion damage at 1.5 seconds
        explosionTaskName = self.uniqueName(f'explodeBase-{appliedByAvId}-{counter}')
        explosionTaskKey = (StatusEffect.EXPLODE, appliedByAvId, counter, 'BASE')
        self.activeStatusEffectTasks[explosionTaskKey] = explosionTaskName
        
        # Set up DOT consumption task (0.75 seconds)
        dotData = {
            'appliedByAvId': appliedByAvId,
            'taskKey': dotTaskKey,
            'capturedDotDamage': dotDamageByPlayer  # Store the captured DOT damage
        }
        
        dotTask = taskMgr.doMethodLater(0.75, self.explodeDOTConsumption, dotTaskName)
        dotTask.explodeData = dotData
        
        # Set up base explosion damage task (1.5 seconds)
        explosionData = {
            'appliedByAvId': appliedByAvId,
            'taskKey': explosionTaskKey
        }
        
        duration = STATUS_EFFECT_DURATIONS.get(StatusEffect.EXPLODE, 1.5)
        explosionTask = taskMgr.doMethodLater(duration, self.explodeBaseDamage, explosionTaskName)
        explosionTask.explodeData = explosionData
    
    def explodeDOTConsumption(self, task):
        """Apply DOT damage from the EXPLODE status effect"""
        explodeData = task.explodeData
        appliedByAvId = explodeData['appliedByAvId']
        
        # Use the captured DOT damage (calculated when explosion was created)
        dotDamageByPlayer = explodeData['capturedDotDamage']
        
        # Deal remaining DOT damage (attributed to respective DOT appliers)
        for dotAppliedByAvId, dotDamage in dotDamageByPlayer.items():
            if dotDamage > 0:
                self.game.recordHitWithAttribution(dotDamage, dotAppliedByAvId, impact=0, craneId=0, objId=0, isGoon=False, isDOT=True)
        
        # Clean up this DOT consumption task
        self.cleanupExplodeTask(explodeData['taskKey'])
        
        return task.done
    
    def explodeBaseDamage(self, task):
        """Deal base explosion damage from the EXPLODE status effect"""
        explodeData = task.explodeData
        appliedByAvId = explodeData['appliedByAvId']
        
        # Calculate total explosion damage
        explosionDamage = 40  # Base explosion damage
        
        # Deal explosion damage (attributed to the explode applier)
        if explosionDamage > 0:
            self.game.recordHitWithAttribution(explosionDamage, appliedByAvId, impact=0, craneId=0, objId=0, isGoon=False, isDOT=True)
        
        # Clean up this explosion task
        self.cleanupExplodeTask(explodeData['taskKey'])
        
        return task.done
    
    def cleanupExplodeTask(self, taskKey):
        """Clean up a specific explode task"""
        if taskKey in self.activeStatusEffectTasks:
            taskName = self.activeStatusEffectTasks[taskKey]
            taskMgr.remove(taskName)
            del self.activeStatusEffectTasks[taskKey]
    
    def stopOldestExplodeEffect(self):
        """Stop the oldest EXPLODE status effect when one is removed from the system"""
        # Find all explode tasks (both DOT and BASE) and stop them
        explodeTasks = [key for key in self.activeStatusEffectTasks.keys() if key[0] == StatusEffect.EXPLODE]
        if explodeTasks:
            # Group by counter to find matching DOT/BASE pairs
            explodeGroups = {}
            for taskKey in explodeTasks:
                statusEffect, avId, counter = taskKey[:3]  # Get first 3 elements
                if counter not in explodeGroups:
                    explodeGroups[counter] = []
                explodeGroups[counter].append(taskKey)
            
            # Get the oldest counter (smallest number)
            oldestCounter = min(explodeGroups.keys())
            
            # Clean up all tasks for the oldest explosion
            for taskKey in explodeGroups[oldestCounter]:
                self.cleanupExplodeTask(taskKey)

