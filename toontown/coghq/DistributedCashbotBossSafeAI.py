from panda3d.core import *

from ..minigame.craning import CraneLeagueGlobals
from toontown.coghq.DistributedCashbotBossSideCraneAI import DistributedCashbotBossSideCraneAI
from toontown.toonbase import ToontownGlobals
from . import DistributedCashbotBossObjectAI
from toontown.minigame.statuseffects.StatusEffectGlobals import StatusEffect, SYNERGY_EFFECTS, STATUS_EFFECT_DURATIONS
import math
import time

class DistributedCashbotBossSafeAI(DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI):

    """ This is a safe sitting around in the Cashbot CFO final battle
    room.  It's used as a prop for toons to pick up and throw at the
    CFO's head.  Also, the special safe with self.index == 0
    represents the safe that the CFO uses to put on his own head as a
    safety helmet from time to time. """

    # A safe remains under physical control of whichever client
    # last dropped it, even after it stops moving.  This allows
    # goons to push safes out of the way.
    wantsWatchDrift = 0

    def __init__(self, air, boss, index):
        DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI.__init__(self, air, boss)
        self.index = index
        
        self.avoidHelmet = 0
        
        # A sphere so goons will see and avoid us.
        self.collisionNode = CollisionNode('safe')
        self.collisionNode.addSolid(CollisionSphere(0, 0, 0, 6))
        self.collisionNode.setIntoCollideMask(ToontownGlobals.CashbotBossObjectBitmask)
        self.collisionNodePath = self.attachNewNode(self.collisionNode)
        
        # A sphere so safes will see and push us when needed.
        self.safeToSafeNode = CollisionNode('safe-to-safe')
        self.safeToSafeNode.addSolid(CollisionSphere(0, 0, 0, 8))
        self.safeToSafeNode.setIntoCollideMask(ToontownGlobals.CashbotBossObjectBitmask)
        self.safeToSafeNodePath = self.attachNewNode(self.safeToSafeNode)
  
        self.cTrav = CollisionTraverser('safe')
        self.cQueue = CollisionHandlerQueue()
        self.cTrav.addCollider(self.safeToSafeNodePath, self.cQueue)

        self._statusEffectTasks = []

    def announceGenerate(self):
        DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI.announceGenerate(self)

        # Set the doId tag here
        self.collisionNode.setTag('doId', str(self.doId))
        self.safeToSafeNode.setTag('doId', str(self.doId))

    def resetToInitialPosition(self):
        posHpr = CraneLeagueGlobals.SAFE_POSHPR[self.index]
        self.setPosHpr(*posHpr)
        
        
    ### Messages ###

    def getIndex(self):
        return self.index

    def getMinImpact(self):
        if self.boss.getBoss().heldObject:
            return self.boss.ruleset.MIN_DEHELMET_IMPACT
        else:
            return self.boss.ruleset.MIN_SAFE_IMPACT
        
    def __handleStatusEffectTimeout(self, doId, effect):
        # Check if boss still exists before trying to access it
        if not hasattr(self, 'boss') or self.boss is None:
            return
        if not hasattr(self.boss, 'statusEffectSystem') or self.boss.statusEffectSystem is None:
            return
        
        self.notify.warning(f'Removing status effect {effect} from boss {doId} at time {time.time()}')
        self.boss.statusEffectSystem.b_removeStatusEffect(doId, effect)

    def checkForSynergy(self, targetId, triggeringAvId) -> bool:
        # Get current effects on the target
        currentEffects = self.boss.statusEffectSystem.getStatusEffects(targetId)
        if len(currentEffects) < 2:
            return False
        
        for pair, synergy in SYNERGY_EFFECTS.items():
            eff1, eff2 = pair
            if eff1 in currentEffects and eff2 in currentEffects:
                # Capture DOT damage before removing effects (for explosion synergy)
                capturedDotDamage = None
                if synergy == StatusEffect.EXPLODE:
                    # Get the boss object to access its burn data
                    boss = self.air.getDo(targetId)
                    if boss and hasattr(boss, 'burnDataTracking'):
                        capturedDotDamage = {}
                        # Check ALL active burn effects (not just synergy components)
                        for taskKey, burnData in list(boss.burnDataTracking.items()):
                            statusEffect, dotAppliedByAvId, burnCounter = taskKey
                            if statusEffect == StatusEffect.BURNED:
                                ticksRemaining = burnData['ticksRemaining']
                                remainingDamage = ticksRemaining * 3  # 3 damage per tick
                                
                                # Track damage by player
                                if dotAppliedByAvId not in capturedDotDamage:
                                    capturedDotDamage[dotAppliedByAvId] = 0
                                capturedDotDamage[dotAppliedByAvId] += remainingDamage
                        
                        # Remove ALL BURNED effects (explosion consumes all DOTs)
                        burnsToRemove = [key for key in boss.burnDataTracking.keys() if key[0] == StatusEffect.BURNED]
                        for taskKey in burnsToRemove:
                            boss.cleanupBurnTask(taskKey)
                            # Also remove from status effect system
                            self.boss.statusEffectSystem.b_removeStatusEffect(targetId, StatusEffect.BURNED)
                
                # Remove the synergy component effects (but BURNED effects already removed above if explosion)
                for effect in pair:
                    if not (synergy == StatusEffect.EXPLODE and effect == StatusEffect.BURNED):
                        # Don't remove BURNED again if we're doing explosion (already removed above)
                        self.boss.statusEffectSystem.b_removeStatusEffect(targetId, effect)
                if synergy is None:
                    return True
                
                # If this is an explosion and we captured DOT damage, pass it to the boss BEFORE applying the effect
                if synergy == StatusEffect.EXPLODE and capturedDotDamage:
                    boss = self.air.getDo(targetId)
                    if boss and hasattr(boss, 'setCapturedDotDamageForExplosion'):
                        boss.setCapturedDotDamageForExplosion(capturedDotDamage)
                
                # Apply synergy effect with the triggering player as applier
                self.boss.statusEffectSystem.b_applyStatusEffect(targetId, synergy, triggeringAvId)
                
                duration = STATUS_EFFECT_DURATIONS.get(synergy, 5.0)
                taskName = self.uniqueName(f'remove-effect-{targetId}-{synergy.value}-{self.doId}-{int(time.time() * 1000)}')
                taskMgr.doMethodLater(duration, self.__handleStatusEffectTimeout, taskName, extraArgs=[targetId, synergy])
                return True
        return False
        

    def handleStatusEffect(self, effect, appliedByAvId):
        # Check if boss still exists
        if not hasattr(self, 'boss') or self.boss is None:
            return
        if not hasattr(self.boss, 'getBoss') or self.boss.getBoss() is None:
            return
        
        bossId = self.boss.getBoss().doId
        self.boss.statusEffectSystem.b_applyStatusEffect(bossId, effect, appliedByAvId)
        taskName = self.uniqueName(f'remove-effect-{bossId}-{effect.value}-{self.doId}-{int(time.time() * 1000)}')

        if self.checkForSynergy(bossId, appliedByAvId):
            return

        # Get duration from globals instead of hardcoded 5.0
        from toontown.minigame.statuseffects.StatusEffectGlobals import STATUS_EFFECT_DURATIONS
        duration = STATUS_EFFECT_DURATIONS.get(effect, 5.0)
        
        # Create and track the task
        task = taskMgr.doMethodLater(duration, self.__handleStatusEffectTimeout, taskName, extraArgs=[bossId, effect])
        self._statusEffectTasks.append(taskName)

    def hitBoss(self, impact, craneId):
        avId = self.air.getAvatarIdFromSender()
        
        self.validate(avId, 1.0 >= impact >= 0, 'invalid hitBoss impact %s' % impact)
        
        if avId not in self.boss.avIdList:
            return
            
        if self.state != 'Dropped' and self.state != 'Grabbed':
            return
        
        damageMultiplier = 0.0
        effects = self.boss.statusEffectSystem.getStatusEffects(self.doId)
        if effects:
            if StatusEffect.GROUNDED in effects:
                damageMultiplier = 0.25
            for effect in effects:
                self.handleStatusEffect(effect, avId)
                self.boss.statusEffectSystem.b_removeStatusEffect(self.doId, effect)
            
        if self.avoidHelmet or self == self.boss.getBoss().heldObject:
            # Ignore the helmet we just knocked off.
            return

        if impact <= self.getMinImpact():
            self.boss.addScore(avId, self.boss.ruleset.POINTS_PENALTY_SANDBAG, reason=CraneLeagueGlobals.ScoreReason.LOW_IMPACT)
            return

        # The client reports successfully striking the boss in the
        # head with this object.
        if self.boss.getBoss().heldObject == None:
            # Check if boss is vulnerable to safes (dizzy OR frozen)
            if hasattr(self.boss.getBoss(), 'isVulnerableToSafes') and self.boss.getBoss().isVulnerableToSafes():
                # While the boss is dizzy or frozen, a safe hitting him in the
                # head does lots of damage.
                damage = int(impact * 50)
                damage += int(damage * damageMultiplier)

                crane = simbase.air.doId2do.get(craneId)
                
                # Apply a multiplier if needed (heavy cranes)
                damage *= crane.getDamageMultiplier()
                damage *= self.boss.ruleset.SAFE_CFO_DAMAGE_MULTIPLIER
                damage = math.ceil(damage)
                
                self.boss.recordHit(max(damage, 2), impact, craneId, objId=self.doId)
            else:
                # If he's not dizzy, he grabs the safe and makes a
                # helmet out of it only if he is allowed to safe helmet.
                if self.boss.ruleset.DISABLE_SAFE_HELMETS:
                    return

                # Is there a cooldown for this toon on intentionally giving the boss a safe helmet?
                if not self.boss.getBoss().allowedToSafeHelmet(avId):
                    return

                self.demand('Grabbed', self.boss.getBoss().doId, self.boss.getBoss().doId)
                self.boss.getBoss().heldObject = self

                self.boss.addScore(avId, self.boss.ruleset.POINTS_PENALTY_SAFEHEAD, reason=CraneLeagueGlobals.ScoreReason.APPLIED_HELMET)

                # Don't allow this toon to safe helmet again for some period of time.
                self.boss.getBoss().addSafeHelmetCooldown(avId)
                
        elif impact >= ToontownGlobals.CashbotBossSafeKnockImpact:
            self.boss.addScore(avId, self.boss.ruleset.POINTS_DESAFE, reason=CraneLeagueGlobals.ScoreReason.REMOVE_HELMET)
            boss = self.boss.getBoss()
            boss.heldObject.demand('Dropped', avId, self.boss.doId)
            boss.heldObject.avoidHelmet = 1
            boss.heldObject = None
            self.avoidHelmet = 1
            boss.waitForNextHelmet()
        return

    def requestInitial(self):
        # The client controlling the safe dropped it through the
        # world; reset it to its initial state.
        
        avId = self.air.getAvatarIdFromSender()
        
        if avId == self.avId:
            self.demand('Initial')

    def requestGrab(self):
        avId = self.air.getAvatarIdFromSender()
        craneId, objectId = self.getCraneAndObject(avId)
        crane = simbase.air.doId2do.get(craneId)
        if crane:
            if craneId != 0 and objectId == 0:
                # If it is a sidecrane, dont pick up the safe
                if isinstance(crane, DistributedCashbotBossSideCraneAI):
                    self.sendUpdateToAvatarId(avId, 'rejectGrab', [])
                    self.demand('Dropped', avId, craneId)
                    return
                elif self.state != 'Grabbed' and self.state != 'Off':
                    self.demand('Grabbed', avId, craneId)
                    return
            self.sendUpdateToAvatarId(avId, 'rejectGrab', [])
            
    def getCraneAndObject(self, avId):
        if self.boss and self.boss.cranes != None:
            for crane in self.boss.cranes:
                if crane.avId == avId:
                    return (crane.doId, crane.objectId)
        return (0, 0)

    def _pushSafe(self, safe, goon, pushed_safes=None):
        if pushed_safes is None:
            pushed_safes = set()
            
        # Prevent pushing the same safe multiple times
        if safe.doId in pushed_safes:
            return
        pushed_safes.add(safe.doId)
        
        thisSafePos = self.getPos()
        otherSafePos = safe.getPos()

        direction = otherSafePos - thisSafePos
        direction[2] = 0 #prevents pushing safes up/down
        direction.normalize()

        pushDistance = goon.velocity * globalClock.getDt()
        newSafePos = otherSafePos + direction * pushDistance
        safe.push(newSafePos[0], newSafePos[1], newSafePos[2], safe.getH(), self)
    
    def __checkSafeCollisions(self, goon, pushed_safes=None):
        if pushed_safes is None:
            pushed_safes = set()
            
        self.cTrav.traverse(self.boss.scene)
        
        for i in range(self.cQueue.getNumEntries()):
            entry = self.cQueue.getEntry(i)
            intoNodePath = entry.getIntoNodePath()
            intoNode = intoNodePath.node()
            fromNode = entry.getFromNode()

            if 'safe-to-safe' in intoNode.getName() and 'safe-to-safe' in fromNode.getName():
                safeDoIdTag = intoNodePath.getNetTag('doId')
                if safeDoIdTag:
                    safeDoId = int(safeDoIdTag)
                    safe = self.air.doId2do.get(safeDoId)
                    if safe and safe.state in ['Sliding Floor', 'Free']:
                        self._pushSafe(safe, goon, pushed_safes)

    ### FSM States ###

    def enterGrabbed(self, avId, craneId):
        DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI.enterGrabbed(self, avId, craneId)
        self.avoidHelmet = 0
        
        # Move collision node far away when grabbed
        # We can move it very far below the battle area
        # This prevents goons from self destructing
        for collNode in self.findAllMatches('**/safe'):
            collNode.setPos(0, 0, -1000)  # Move collision 1000 units down
        for collNode in self.findAllMatches('**/safe-to-safe'):
            collNode.setPos(0, 0, -1000)  # Move collision 1000 units down

    def exitGrabbed(self):
        DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI.exitGrabbed(self)
        # Reset collision node position
        for collNode in self.findAllMatches('**/safe'):
            collNode.setPos(0, 0, 0)  # Reset to original position
        for collNode in self.findAllMatches('**/safe-to-safe'):
            collNode.setPos(0, 0, 0)  # Reset to original position

    def enterInitial(self):
        # The safe is in its initial, resting position.
        self.avoidHelmet = 0
        self.resetToInitialPosition()
        
        if self.index == 0:
            # The special "helmet-only" safe goes away completely when
            # it's in Initial mode.
            self.stash()
            
        self.d_setObjectState('I', 0, 0)

    def exitInitial(self):
        if self.index == 0:
            self.unstash()

    def enterFree(self):
        # The safe is somewhere on the floor, but not under anyone's
        # control. This can only happen to a safe when the player who
        # was controlling it disconnects during battle
        
        DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI.enterFree(self)
        self.avoidHelmet = 0
        
    def enterDropped(self, avId, craneId):
        super().enterDropped(avId, craneId)
        if self.index != 0:  # Only trigger for non-helmet safes during aim mode
            self.boss.practiceCheatHandler.handleSafeDropped(self)

    def move(self, x, y, z, rotation):
        # Update the safe's position and heading
        self.setPosHpr(x, y, z, rotation, 0, 0)  # Smoothly update position and heading
        self.sendUpdate('move', [x, y, z, rotation])  # Inform the client about the move
        
    def push(self, x, y, z, rotation, pusher):
        # Update the safe's position and heading
        self.setSmPosHpr(x, y, z, rotation, 0, 0)
        self.sendUpdate('move', [x, y, z, rotation])
        
        # Only check for secondary collisions if being pushed by a goon
        # This prevents safe-to-safe pushes from triggering more collisions
        if pusher.__class__.__name__ == 'DistributedCashbotBossGoonAI':
            self.__checkSafeCollisions(pusher)

    # Called from client when a safe destroys a goon
    def destroyedGoon(self):
        avId = self.air.getAvatarIdFromSender()
        self.boss.addScore(avId, self.boss.ruleset.POINTS_GOON_KILLED_BY_SAFE, reason=CraneLeagueGlobals.ScoreReason.GOON_KILL)

    def cleanup(self):
        """Clean up collision system and node paths to prevent memory leaks"""
        # Clean up status effect timeout tasks
        for taskName in self._statusEffectTasks:
            try:
                taskMgr.remove(taskName)
            except:
                pass
        self._statusEffectTasks.clear()
        
        # Clean up collision system
        if hasattr(self, 'cTrav') and self.cTrav:
            self.cTrav.clearColliders()
            del self.cTrav
        if hasattr(self, 'cQueue') and self.cQueue:
            del self.cQueue
        
        # Clean up collision node paths - check both existence and not None
        if hasattr(self, 'collisionNodePath') and self.collisionNodePath is not None:
            self.collisionNodePath.removeNode()
            self.collisionNodePath = None
        if hasattr(self, 'safeToSafeNodePath') and self.safeToSafeNodePath is not None:
            self.safeToSafeNodePath.removeNode()
            self.safeToSafeNodePath = None
        
        # Clean up collision nodes
        if hasattr(self, 'collisionNode'):
            self.collisionNode = None
        if hasattr(self, 'safeToSafeNode'):
            self.safeToSafeNode = None
        
        # Call parent cleanup
        DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI.cleanup(self)

    def delete(self):
        # Clean up resources before deletion
        self.cleanup()
        DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI.delete(self)