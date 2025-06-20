from panda3d.core import *
from direct.interval.IntervalGlobal import *
from direct.task.TaskManagerGlobal import *
from direct.distributed.ClockDelta import *
from direct.directnotify import DirectNotifyGlobal
from . import GoonGlobals
from direct.task.Task import Task
from toontown.toonbase import ToontownGlobals
from otp.otpbase import OTPGlobals
from toontown.coghq import DistributedCashbotBossObject, CraneLeagueGlobals
from direct.showbase import PythonUtil
from . import DistributedGoon

class DistributedCashbotBossGoon(DistributedGoon.DistributedGoon, DistributedCashbotBossObject.DistributedCashbotBossObject):
    
    """ This is a goon that walks around in the Cashbot CFO final
    battle scene, tormenting Toons, and also providing ammo for
    defeating the boss. """
    
    notify = DirectNotifyGlobal.directNotify.newCategory('DistributedCashbotBossGoon')
    
    walkGrabZ = -3.6
    stunGrabZ = -2.2
    
    # How long does it take for a live goon to wiggle free of the magnet?
    wiggleFreeTime = 2
    
    # What happens to the crane and its cable when this object is picked up?
    craneFrictionCoef = 0.15
    craneSlideSpeed = 10
    craneRotateSpeed = 20

    def __init__(self, cr):
        DistributedCashbotBossObject.DistributedCashbotBossObject.__init__(self, cr)
        DistributedGoon.DistributedGoon.__init__(self, cr)
        
        self.target = None
        self.arrivalTime = None
        
        self.flyToMagnetSfx = loader.loadSfx('phase_5/audio/sfx/TL_rake_throw_only.ogg')
        self.hitMagnetSfx = loader.loadSfx('phase_4/audio/sfx/AA_drop_anvil_miss.ogg')
        self.toMagnetSoundInterval = Sequence(SoundInterval(self.flyToMagnetSfx, duration=ToontownGlobals.CashbotBossToMagnetTime, node=self), SoundInterval(self.hitMagnetSfx, node=self))
        self.hitFloorSfx = loader.loadSfx('phase_5/audio/sfx/AA_drop_flowerpot.ogg')
        self.hitFloorSoundInterval = SoundInterval(self.hitFloorSfx, duration=1.0, node=self)
        self.wiggleSfx = loader.loadSfx('phase_5/audio/sfx/SA_finger_wag.ogg')
        self.name = 'goon'
        return

    def generate(self):
        DistributedCashbotBossObject.DistributedCashbotBossObject.generate(self)
        DistributedGoon.DistributedGoon.generate(self)

    def announceGenerate(self):
        DistributedCashbotBossObject.DistributedCashbotBossObject.announceGenerate(self)

        # It is important to call setupPhysics() before we call
        # DistributedGoon.announceGenerate(), since setupPhysics()
        # will reassign our NodePath and thereby invalidate any
        # messenger hooks already added.  In fact, it is important
        # that we not have any outstanding messenger hooks at the time
        # we call setupPhysics().
        self.setupPhysics('goon')
        
        DistributedGoon.DistributedGoon.announceGenerate(self)
        
        self.name = 'goon-%s' % self.doId
        self.setName(self.name)
        
        self.setTag('doId', str(self.doId))
        self.collisionNode.setName('goon')
        cs = CollisionSphere(0, 0, 4, 4) #TTR Collisions
        #cs = CollisionCapsule(0, 0, 4, 0, 0, 4, 4) #TTCC Collisions
        self.collisionNode.addSolid(cs)
        self.collisionNode.setIntoCollideMask(ToontownGlobals.PieBitmask | ToontownGlobals.CashbotBossObjectBitmask)
        
        self.wiggleTaskName = self.uniqueName('wiggleTask')
        self.wiggleFreeName = self.uniqueName('wiggleFree')
        
        self.boss.goons.append(self)
        
        self.reparentTo(render)

    def disable(self):
        if self in self.boss.goons:
            i = self.boss.goons.index(self)
            del self.boss.goons[i]
        DistributedGoon.DistributedGoon.disable(self)
        DistributedCashbotBossObject.DistributedCashbotBossObject.disable(self)

    def delete(self):
        DistributedGoon.DistributedGoon.delete(self)
        DistributedCashbotBossObject.DistributedCashbotBossObject.delete(self)

    def hideShadows(self):
        self.dropShadow.hide()

    def showShadows(self):
        self.dropShadow.show()

    def getMinImpact(self):
        # This method returns the minimum impact, in feet per second,
        # with which the object should hit the boss before we bother
        # to tell the server.
        return self.boss.ruleset.MIN_GOON_IMPACT

    def doHitBoss(self, impact, craneId):
        self.d_hitBoss(impact, craneId)

        if impact >= self.getMinImpact():
            self.b_destroyGoon()

    def __startWalk(self):
        # Generate an interval to walk the goon to his target square
        # by the specified time.
        self.__stopWalk()
        
        if self.target:
            now = globalClock.getFrameTime()
            availableTime = self.arrivalTime - now
            if availableTime > 0:
                # How long will it take to rotate to position?
                origH = self.getH()
                h = PythonUtil.fitDestAngle2Src(origH, self.targetH)
                delta = abs(h - origH)
                turnTime = delta / (self.velocity * 5)
                
                # And how long will it take to walk to position?
                dist = Vec3(self.target - self.getPos()).length()
                walkTime = dist / self.velocity

                denom = turnTime + walkTime
                if denom != 0:
                    # Fit that within our available time.
                    timeCompress = availableTime / denom
                    self.walkTrack = Sequence(self.hprInterval(turnTime * timeCompress, VBase3(h, 0, 0)), self.posInterval(walkTime * timeCompress, self.target))
                    self.walkTrack.start()
            else:
                self.setPos(self.target)
                self.setH(self.targetH)

    def __stopWalk(self):
        # Stop the walk interval.
        if self.walkTrack:
            self.walkTrack.pause()
            self.walkTrack = None
        return

    def __wiggleTask(self, task):
        # If the unfortunate player picks up an active goon, the
        # magnet should wiggle erratically to indicate instability.
        elapsed = globalClock.getFrameTime() - self.wiggleStart
        h = math.sin(elapsed * 17) * 5
        p = math.sin(elapsed * 29) * 10
        if self.crane:
            self.crane.wiggleMagnet.setHpr(h, p, 0)
        return Task.cont

    def __wiggleFree(self, task):
        # We've successfully wiggled free after being picked up.
        if self.crane:
            self.crane.releaseObject()

        # And we can't be picked up again until we land.
        self.stashCollisions()
        return Task.done

    def fellOut(self):
        # The goon fell out of the world. Just destroy him and move on.
        self.b_destroyGoon()

    def handleToonDetect(self, collEntry = None):
        if self.boss.getBoss().localToonIsSafe:
            return
        DistributedGoon.DistributedGoon.handleToonDetect(self, collEntry)

    def prepareGrab(self):
        DistributedCashbotBossObject.DistributedCashbotBossObject.prepareGrab(self)
        if self.isStunned:
            self.pose('collapse', 48)
            self.grabPos = (0, 0, self.stunGrabZ * self.scale)
        else:
            # He's got a live one!
            self.setPlayRate(4, 'walk')
            self.loop('walk')
            self.grabPos = (0, 0, self.walkGrabZ * self.scale)
            self.wiggleStart = globalClock.getFrameTime()
            taskMgr.add(self.__wiggleTask, self.wiggleTaskName)
            base.sfxPlayer.playSfx(self.wiggleSfx, node=self)
            if self.avId == localAvatar.doId:
                taskMgr.doMethodLater(self.wiggleFreeTime, self.__wiggleFree, self.wiggleFreeName)
        self.radar.hide()

    def prepareRelease(self):
        DistributedCashbotBossObject.DistributedCashbotBossObject.prepareRelease(self)
        if self.crane:
            self.crane.wiggleMagnet.setHpr(0, 0, 0)
        taskMgr.remove(self.wiggleTaskName)
        taskMgr.remove(self.wiggleFreeName)
        self.setPlayRate(self.animMultiplier, 'walk')

    ##### Messages To/From The Server #####

    def setObjectState(self, state, avId, craneId):
        if state == 'W':
            if self.state not in ['Grabbed', 'LocalGrabbed']:
                self.demand('Walk')
        elif state == 'B':
            if self.state != 'Battle':
                self.demand('Battle')
        elif state == 'S':
            if self.state != 'Stunned':
                self.demand('Stunned')
        elif state == 'R':
            if self.state != 'Recovery' and self.state not in ['Grabbed', 'LocalGrabbed']:
                self.demand('Recovery')
        elif state == 'a':
            self.demand('EmergeA')
        elif state == 'b':
            self.demand('EmergeB')
        elif state == 'F':
            if self.state not in ['Grabbed', 'LocalGrabbed']:
                self.demand('Falling')
        else:
            DistributedCashbotBossObject.DistributedCashbotBossObject.setObjectState(self, state, avId, craneId)

    def setTarget(self, x, y, h, travelTime):
        self.target = Point3(x, y, 0)
        self.targetH = h
        now = globalClock.getFrameTime()
        self.arrivalTime = now + travelTime
        if self.state == 'Walk':
            self.__startWalk()

    def d_destroyGoon(self):
        self.sendUpdate('destroyGoon')

    def b_destroyGoon(self):
        self.resetSpeedCaching()
        self.d_destroyGoon()
        self.destroyGoon()

    def destroyGoon(self):
        self.playCrushMovie(None, None)
        self.demand('Off')
        if self in self.boss.goons:
            self.boss.goons.remove(self)
        return
        
    ### FSM States ###

    def enterOff(self):
        DistributedGoon.DistributedGoon.enterOff(self)
        DistributedCashbotBossObject.DistributedCashbotBossObject.enterOff(self)

    def exitOff(self):
        DistributedCashbotBossObject.DistributedCashbotBossObject.exitOff(self)
        DistributedGoon.DistributedGoon.exitOff(self)

    def enterWalk(self, avId = None, ts = 0):
        self.resetSpeedCaching()
        self.startToonDetect()
        self.radar.show()
        self.isStunned = 0
        self.__startWalk()
        self.loop('walk', 0)
        self.unstashCollisions()

    def exitWalk(self):
        self.__stopWalk()
        self.stopToonDetect()
        self.stop()

    def enterEmergeA(self):
        # The goon emerges from door a.
        self.reparentTo(render)
        self.stopToonDetect()
        self.boss.getBoss().doorA.request('open')
        self.radar.hide()
        self.__startWalk()
        self.loop('walk', 0)

    def exitEmergeA(self):
        if self.boss.getBoss().doorA:
            self.boss.getBoss().doorA.request('close')
        self.__stopWalk()

    def enterEmergeB(self):
        # The goon emerges from door b.
        self.reparentTo(render)
        self.stopToonDetect()
        self.boss.getBoss().doorB.request('open')
        self.radar.hide()
        self.__startWalk()
        self.loop('walk', 0)

    def exitEmergeB(self):
        if self.boss.getBoss().doorB:
            self.boss.getBoss().doorB.request('close')
        self.radar.show()
        self.__stopWalk()

    def enterBattle(self, avId = None, ts = 0):
        DistributedGoon.DistributedGoon.enterBattle(self, avId, ts)
        avatar = base.cr.doId2do.get(avId)
        if avatar:
            # Make the toon flash, and knock him off the crane.
            messenger.send('exitCrane')
            avatar.stunToon()
        self.unstashCollisions()

    def enterStunned(self, ts = 0):
        DistributedGoon.DistributedGoon.enterStunned(self, ts)
        self.unstashCollisions()

    def enterRecovery(self, ts = 0, pauseTime = 0):
        DistributedGoon.DistributedGoon.enterRecovery(self, ts, pauseTime)
        self.unstashCollisions()

    def d_requestWalk(self):
        self.sendUpdate('requestWalk')

    def enterFalling(self):
        self.stopToonDetect()
        self.radar.hide()
        self.isStunned = 1

        # Activate physics to handle collisions and bouncing
        self.activatePhysics()

        # Set physics properties for bouncy behavior
        self.handler.setStaticFrictionCoef(0)  # Make it slide
        self.handler.setDynamicFrictionCoef(0.3)
        
        # Add some initial downward velocity
        self.physicsObject.setVelocity(0, 0, -5)  # Start falling at 5 units/sec

    def exitFalling(self):
        self.deactivatePhysics()

    def __playHitFloorAnimation(self):
        if self.animTrack is not None:
            self.animTrack.finish()
            self.animTrack = None

        self.demand('Stunned')

    def doHitFloor(self):
        super().doHitFloor()
        self.__playHitFloorAnimation()

    def doHitGoon(self, goon):
        super().doHitGoon(goon)
        if self.state == 'Falling':
            self.__playHitFloorAnimation()
