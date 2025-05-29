from panda3d.core import *
from direct.task.TaskManagerGlobal import taskMgr

from toontown.coghq import CraneLeagueGlobals
from toontown.coghq.DistributedCashbotBossHeavyCraneAI import DistributedCashbotBossHeavyCraneAI
from toontown.coghq.DistributedCashbotBossSideCraneAI import DistributedCashbotBossSideCraneAI
from toontown.toonbase import ToontownGlobals
from otp.otpbase import OTPGlobals
from . import DistributedCashbotBossObjectAI
import math

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

    def hitBoss(self, impact, craneId):
        avId = self.air.getAvatarIdFromSender()
        
        self.validate(avId, 1.0 >= impact >= 0, 'invalid hitBoss impact %s' % impact)
        
        if avId not in self.boss.avIdList:
            return
            
        if self.state != 'Dropped' and self.state != 'Grabbed':
            return
            
        if self.avoidHelmet or self == self.boss.getBoss().heldObject:
            # Ignore the helmet we just knocked off.
            return

        if impact <= self.getMinImpact():
            self.boss.addScore(avId, self.boss.ruleset.POINTS_PENALTY_SANDBAG, reason=CraneLeagueGlobals.ScoreReason.LOW_IMPACT)
            return

        # Check if this safe has elemental status before processing the hit
        elementType = self.boss.getSafeElementType(self.doId)
        hadElementalStatus = elementType != 0  # ElementType.NONE = 0
        
        # The client reports successfully striking the boss in the
        # head with this object.
        if self.boss.getBoss().heldObject == None:
            if self.boss.getBoss().attackCode == ToontownGlobals.BossCogDizzy:
                # While the boss is dizzy, a safe hitting him in the
                # head does lots of damage.
                damage = int(impact * 50)
                crane = simbase.air.doId2do.get(craneId)
                
                # Apply a multiplier if needed (heavy cranes)
                damage *= crane.getDamageMultiplier()
                damage *= self.boss.ruleset.SAFE_CFO_DAMAGE_MULTIPLIER
                
                # Apply elemental effects if this safe has any elemental status
                if elementType != 0:  # ElementType.NONE = 0
                    # Check for VOLT re-stun ability
                    if elementType == 2:  # ElementType.VOLT = 2
                        # VOLT safes can re-stun (extend stun time) even when CFO is already stunned
                        self.__performVoltReStun(impact, craneId, avId, damage)
                        # Remove elemental status after VOLT re-stun is applied
                        if hadElementalStatus:
                            self.__removeElementalStatus()
                        return  # Exit early, re-stun handles everything
                    elif elementType != 2:  # Only apply DoT for non-VOLT elements
                        # Apply elemental DoT effect based on element type
                        self.boss.applyElementalDoT(avId, elementType, damage)
                        
                        elementName = {1: 'Fire', 2: 'Volt'}.get(elementType, f'Element{elementType}')
                        self.boss.notify.info(f"{elementName} elemental safe {self.doId} applied DoT effect!")
                
                damage = math.ceil(damage)
                
                self.boss.recordHit(max(damage, 2), impact, craneId, objId=self.doId)
            else:
                # Check if this is a VOLT elemental safe
                isVoltSafe = (elementType == 2)  # ElementType.VOLT = 2
                
                if isVoltSafe:
                    # VOLT safes stun the CFO instead of creating helmets
                    self.__performVoltStun(impact, craneId, avId)
                else:
                    # Regular safe behavior: Create helmet if allowed
                    # If he's not dizzy, he grabs the safe and makes a
                    # helmet out of it only if he is allowed to safe helmet.
                    if self.boss.ruleset.DISABLE_SAFE_HELMETS:
                        # Remove elemental status even if helmets are disabled
                        if hadElementalStatus:
                            self.__removeElementalStatus()
                        return

                    # Is there a cooldown for this toon on intentionally giving the boss a safe helmet?
                    if not self.boss.getBoss().allowedToSafeHelmet(avId):
                        # Remove elemental status even if cooldown prevents helmet
                        if hadElementalStatus:
                            self.__removeElementalStatus()
                        return

                    self.demand('Grabbed', self.boss.getBoss().doId, self.boss.getBoss().doId)
                    self.boss.getBoss().heldObject = self

                    self.boss.addScore(avId, self.boss.ruleset.POINTS_PENALTY_SAFEHEAD, reason=CraneLeagueGlobals.ScoreReason.APPLIED_HELMET)

                    # Don't allow this toon to safe helmet again for some period of time.
                    self.boss.getBoss().addSafeHelmetCooldown(avId)
                
        elif impact >= ToontownGlobals.CashbotBossSafeKnockImpact:
            # Check if this is a VOLT elemental safe
            isVoltSafe = (elementType == 2)  # ElementType.VOLT = 2
            
            self.boss.addScore(avId, self.boss.ruleset.POINTS_DESAFE, reason=CraneLeagueGlobals.ScoreReason.REMOVE_HELMET)
            boss = self.boss.getBoss()
            boss.heldObject.demand('Dropped', avId, self.boss.doId)
            boss.heldObject.avoidHelmet = 1
            boss.heldObject = None
            self.avoidHelmet = 1
            boss.waitForNextHelmet()
            
            if isVoltSafe:
                # VOLT safes also stun the CFO after knocking off helmet
                self.__performVoltStun(impact, craneId, avId, afterHelmetKnockoff=True)
        
        # Remove elemental status after any successful hit on the CFO
        # This ensures the elemental effect is "consumed" when used
        if hadElementalStatus:
            self.__removeElementalStatus()
            
        return

    def __performVoltStun(self, impact, craneId, avId, afterHelmetKnockoff=False):
        """Perform VOLT elemental stunning effect on the CFO"""
        crane = simbase.air.doId2do.get(craneId)
        if not crane:
            return
            
        # Calculate damage for VOLT stun - make it competitive with regular safe damage
        # Regular safes do impact * 50 when CFO is stunned
        # VOLT safes should do similar or better damage since they provide stunning utility
        damage = int(impact * 50 * 0.75)  # Slightly less than regular safe but still substantial
        damage *= crane.getDamageMultiplier()
        damage *= self.boss.ruleset.SAFE_CFO_DAMAGE_MULTIPLIER
        damage = math.ceil(max(damage, 2))
        
        # Force the CFO to be stunnable by VOLT regardless of normal stun requirements
        boss = self.boss.getBoss()
        
        if afterHelmetKnockoff:
            self.boss.notify.info(f"VOLT safe {self.doId} stunned CFO after helmet knockoff!")
            # Give bonus points for the extra stun after helmet knockoff
            self.boss.addScore(avId, self.boss.ruleset.POINTS_STUN, reason=CraneLeagueGlobals.ScoreReason.STUN)
        else:
            self.boss.notify.info(f"VOLT safe {self.doId} stunned CFO instead of creating helmet!")
            # Give stun points instead of helmet penalty
            self.boss.addScore(avId, self.boss.ruleset.POINTS_STUN, reason=CraneLeagueGlobals.ScoreReason.STUN)
        
        # Apply the stun effect - force boss to be dizzy
        delayTime = self.boss.progressValue(6, 3)  # Same delay as normal stuns
        
        # Reset helmet cooldowns like goons do when they stun the CFO
        boss.stopHelmets()
        
        boss.b_setAttackCode(ToontownGlobals.BossCogDizzy, delayTime=delayTime)
        
        # Trigger CFO VOLT visual effect for the duration of the VOLT contribution (not entire stun)
        voltEffectDuration = self.boss.progressValue(6, 3)  # VOLT effect lasts for VOLT contribution time
        self.boss.d_setCFOElementalStatus(2, True)  # ElementType.VOLT = 2, enabled = True
        
        # Schedule removal of VOLT effect when VOLT contribution ends (not when stun ends)
        taskMgr.doMethodLater(voltEffectDuration, self.__removeVoltEffectFromCFO, 
                             self.boss.getBoss().uniqueName('removeVoltEffect'))
        
        # Apply the damage from the VOLT stun
        self.boss.recordHit(damage, impact, craneId, objId=self.doId)
        
        # Remove elemental status after VOLT stun is applied
        self.__removeElementalStatus()

    def __removeVoltEffectFromCFO(self, task=None):
        """Remove VOLT visual effect from CFO when stun expires"""
        self.boss.d_setCFOElementalStatus(2, False)  # ElementType.VOLT = 2, enabled = False
        return task.done

    def __performVoltReStun(self, impact, craneId, avId, damage):
        """Perform VOLT re-stun effect on the CFO when already stunned"""
        crane = simbase.air.doId2do.get(craneId)
        if not crane:
            return
            
        boss = self.boss.getBoss()
        
        # Calculate the extension time: half of normal stun duration, minimum 3 seconds
        extensionTime = self.boss.progressValue(6, 3)  # Half duration, minimum 3 seconds
        
        # Get the remaining time on the current stun
        remainingStunTime = 0
        taskName = boss.uniqueName('NextAttack')
        existingTasks = taskMgr.getTasksNamed(taskName)
        if existingTasks:
            currentTime = globalClock.getFrameTime()
            existingTask = existingTasks[0]
            remainingStunTime = max(0, existingTask.wakeTime - currentTime)
        
        # Calculate total stun time: remaining time + extension time
        totalStunTime = remainingStunTime + extensionTime
        
        # Apply the extended stun with the total duration
        boss.b_setAttackCode(ToontownGlobals.BossCogDizzy, delayTime=totalStunTime)
        
        # Reset helmet cooldowns like goons do when they stun the CFO
        boss.stopHelmets()
        
        # If CFO doesn't already have VOLT effect, apply it
        # (This handles edge cases where VOLT re-stun happens right as effect was about to expire)
        self.boss.d_setCFOElementalStatus(2, True)  # ElementType.VOLT = 2, enabled = True
        
        # Cancel any existing VOLT effect removal task
        taskMgr.remove(boss.uniqueName('removeVoltEffect'))
        
        # Schedule new removal of VOLT effect when VOLT extension contribution ends (not total stun)
        voltEffectDuration = extensionTime  # VOLT effect lasts for VOLT extension contribution time
        taskMgr.doMethodLater(voltEffectDuration, self.__removeVoltEffectFromCFO, 
                             boss.uniqueName('removeVoltEffect'))
        
        # Give points for the re-stun
        self.boss.addScore(avId, self.boss.ruleset.POINTS_STUN, reason=CraneLeagueGlobals.ScoreReason.STUN)
        
        # Apply the damage from the VOLT re-stun (use original damage calculation)
        self.boss.recordHit(max(damage, 2), impact, craneId, objId=self.doId)
        
        self.boss.notify.info(f"VOLT safe {self.doId} re-stunned CFO! Remaining: {remainingStunTime:.1f}s + Extension: {extensionTime:.1f}s = Total: {totalStunTime:.1f}s")
        
        # Remove elemental status after VOLT re-stun is applied
        self.__removeElementalStatus()

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

    def __removeElementalStatus(self):
        """Remove elemental status from this safe after it hits the CFO"""
        # Only remove if this safe actually has elemental status
        if self.boss.isSafeElemental(self.doId):
            elementType = self.boss.getSafeElementType(self.doId)
            elementName = {1: 'Fire', 2: 'Volt'}.get(elementType, f'Element{elementType}')
            
            # Remove from the elemental system immediately (don't wait for the normal 10-second timer)
            self.boss._DistributedCraneGameAI__removeElemental(self.doId)
            
            self.boss.notify.info(f"Safe {self.doId} lost {elementName} elemental status after hitting CFO")
