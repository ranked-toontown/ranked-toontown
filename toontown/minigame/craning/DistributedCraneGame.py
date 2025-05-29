import functools
import json
import os
import random
import math
import time

from direct.actor.Actor import Actor
from direct.distributed import DistributedSmoothNode
from direct.fsm import ClassicFSM
from direct.fsm import State
from direct.gui.OnscreenText import OnscreenText
from direct.interval.FunctionInterval import Func, Wait
from direct.interval.LerpInterval import LerpPosHprInterval
from direct.interval.MetaInterval import Parallel, Sequence
from direct.showbase.MessengerGlobal import messenger
from direct.showbase.PythonUtil import reduceAngle
from direct.task.TaskManagerGlobal import taskMgr
from panda3d.core import CollisionPlane, Plane, Vec3, Point3, CollisionNode, NodePath, CollisionPolygon, BitMask32, \
    VBase3, VBase4, CardMaker, ColorBlendAttrib, GeomVertexData, GeomVertexWriter, Geom, GeomTrifans, GeomNode, GeomVertexFormat, CollisionRay, CollisionSphere, CollisionHandlerQueue, CollisionTube, TextNode, Vec4
from panda3d.physics import LinearVectorForce, ForceNode, LinearEulerIntegrator, PhysicsManager

from libotp import CFSpeech
from libotp.nametag import NametagGlobals
from otp.otpbase import OTPGlobals
from tools.match_recording import match_serializer
from tools.match_recording.match_event import PointEvent, RoundEndEvent, RoundBeginEvent, ComboChangeEvent
from toontown.coghq import CraneLeagueGlobals
from toontown.coghq.BossSpeedrunTimer import BossSpeedrunTimedTimer, BossSpeedrunTimer
from toontown.coghq.CashbotBossScoreboard import CashbotBossScoreboard
from toontown.coghq.CraneLeagueHeatDisplay import CraneLeagueHeatDisplay
from toontown.minigame.DistributedMinigame import DistributedMinigame
from toontown.minigame.craning import CraneGameGlobals
from toontown.minigame.craning.CraneGameGlobals import RED_COUNTDOWN_COLOR, ORANGE_COUNTDOWN_COLOR, \
    YELLOW_COUNTDOWN_COLOR
from toontown.minigame.craning.CraneWalk import CraneWalk
from toontown.toonbase import TTLocalizer, ToontownGlobals
from toontown.minigame.craning.CraneGameSettingsPanel import CraneGameSettingsPanel
from direct.gui.DirectGui import DGG, DirectFrame
from direct.gui.DirectScrolledList import DirectScrolledList
from direct.gui.DirectLabel import DirectLabel
from direct.gui.DirectButton import DirectButton
from direct.showbase.ShowBaseGlobal import aspect2d
from direct.task import Task
from direct.interval.IntervalGlobal import Sequence, Parallel, LerpColorScaleInterval, LerpScaleInterval, Func
from direct.gui.DirectButton import DirectButton
from toontown.toonbase import TTLocalizer
from toontown.battle import BattleParticles
from direct.interval.IntervalGlobal import Sequence, Parallel, LerpColorScaleInterval, LerpScaleInterval, Func

# Element type constants for expandable elemental system (client-side)
class ElementType:
    NONE = 0
    FIRE = 1
    VOLT = 2
    # Future elements can be added here:
    # ICE = 3
    # POISON = 4

from tools.match_recording.match_replay import MatchReplay

class DistributedCraneGame(DistributedMinigame):

    # define constants that you won't want to tweak here
    BASE_HEAT = 500

    def __init__(self, cr):
        DistributedMinigame.__init__(self, cr)

        self.cranes = {}
        self.safes = {}
        self.goons = []

        # Setup collision detection for clicking
        self.clickRay = CollisionRay()
        self.clickRayNode = CollisionNode('mouseRay')
        self.clickRayNode.addSolid(self.clickRay)
        self.clickRayNodePath = camera.attachNewNode(self.clickRayNode)
        # Create a special bitmask for our spotlight clicks
        self.spotlightBitMask = BitMask32.bit(3)  # Using bit 3 for our spotlight clicks
        self.clickRayNode.setFromCollideMask(self.spotlightBitMask)
        self.clickRayNode.setIntoCollideMask(BitMask32.allOff())
        self.clickRayQueue = CollisionHandlerQueue()
        base.cTrav.addCollider(self.clickRayNodePath, self.clickRayQueue)

        self.overlayText = OnscreenText('', shadow=(0, 0, 0, 1), font=ToontownGlobals.getCompetitionFont(), pos=(0, 0), scale=0.35, mayChange=1)
        self.overlayText.hide()
        self.rulesPanel = None
        self.rulesPanelToggleButton = None
        self.playButton = None
        self.participantsButton = None
        self.bestOfButton = None
        self.participantsPanel = None
        self.participantsList = None
        self.participantsPanelVisible = False
        self.bestOfValue = 1  # Default to Best of 1
        self.elementalMode = False  # Default to vanilla mode
        self.currentRound = 1
        self.roundWins = {}  # Maps avId -> number of rounds won
        self.fireElementalIndicators = {}  # Maps safeDoId -> text indicator NodePath
        self.cfoElementalEffects = {}  # Maps elementType -> effect NodePath for CFO effects
        self.boss = None
        self.bossRequest = None
        self.wantCustomCraneSpawns = False
        self.customSpawnPositions = {}
        self.ruleset = CraneLeagueGlobals.CraneGameRuleset()  # Setup a default ruleset as a fallback
        self.modifiers = []
        self.heatDisplay = CraneLeagueHeatDisplay()
        self.heatDisplay.hide()
        self.endVault = None
        self.statusIndicators = {}  # Dictionary to store status indicators for each toon

        self.warningSfx = None

        self.timerTickSfx = None
        self.goSfx = None

        self.latency = 0.5  # default latency for updating object posHpr

        self.toonSpawnpointOrder = [i for i in range(16)]
        self.stunEndTime = 0
        self.myHits = []
        self.tempHp = self.ruleset.CFO_MAX_HP
        self.processingHp = False

        self.bossSpeedrunTimer = BossSpeedrunTimer()
        self.bossSpeedrunTimer.hide()
        self.bossSpeedrunTimer.stop_updating()

        # The crane round scoreboard
        self.scoreboard = CashbotBossScoreboard(ruleset=self.ruleset)
        self.scoreboard.hide()

        self.walkStateData = CraneWalk('walkDone')

        self.gameFSM = ClassicFSM.ClassicFSM('DistributedMinigameTemplate',
                               [
                                State.State('off',
                                            self.enterOff,
                                            self.exitOff,
                                            ['prepare']),
                                State.State('prepare',
                                            self.enterPrepare,
                                            self.exitPrepare,
                                            ['play', 'cleanup']),
                                State.State('play',
                                            self.enterPlay,
                                            self.exitPlay,
                                            ['victory', 'cleanup', 'prepare']),
                                State.State('victory',
                                            self.enterVictory,
                                            self.exitVictory,
                                            ['cleanup', 'prepare']),
                                State.State('cleanup',
                                            self.enterCleanup,
                                            self.exitCleanup,
                                            []),
                                ],
                               # Initial State
                               'off',
                               # Final State
                               'cleanup',
                               )

        # it's important for the final state to do cleanup;
        # on disconnect, the ClassicFSM will be forced into the
        # final state. All states (except 'off') should
        # be prepared to transition to 'cleanup' at any time.

        # Add our game ClassicFSM to the framework ClassicFSM
        self.addChildGameFSM(self.gameFSM)

        self.overtimeActive = False

        # Additive color effect system for proper blending of multiple effects
        self.cfoColorEffects = {}  # Maps effectName -> color contribution (r, g, b, a)
        self.cfoBaseColor = (1.0, 1.0, 1.0, 1.0)  # Base normal color
        self.cfoColorLerpTask = None  # Current color lerp task

        # Event recording for game data/replays.
        self.eventRecorder = MatchReplay(timestamp=int(time.time()))

    def getTitle(self):
        return TTLocalizer.CraneGameTitle

    def getInstructions(self):
        return TTLocalizer.CraneGameInstructions

    def getMaxDuration(self):
        # how many seconds can this minigame possibly last (within reason)?
        # this is for debugging only
        return 0

    def setSpectators(self, spectatorIds):
        """
        Called by the server to update the list of spectators.
        This is the distributed method that gets called on all clients.
        """
        super().setSpectators(spectatorIds)

        if self.gameFSM.getCurrentState() is not None:
            if self.gameFSM.getCurrentState().getName() == 'play':
                return

        # Update all toon indicators based on their spectator status
        for i, avId in enumerate(self.avIdList):
            toon = self.cr.getDo(avId)
            if toon:
                isPlayer = avId not in spectatorIds
                if avId in self.statusIndicators:
                    self.updateStatusIndicator(toon, isPlayer)
                else:
                    self.createStatusIndicator(toon, isPlayer)

    def __checkSpectatorState(self, spectate=True):
        # If we're in the rules state, don't apply any visibility changes
        if hasattr(self, 'rulesPanel') and self.rulesPanel is not None:
            return

        for toon in self.getSpectatingToons():
            if self.gameFSM.getCurrentState().getName() == 'play':
                toon.setGhostMode(True)
                toon.setPos(100, 100, 1000)

        # Loop through every non-spectator and make sure we can see them
        for toon in self.getParticipantsNotSpectating():
            toon.setGhostMode(False)
            toon.clearColorScale()
            toon.clearTransparency()
            toon.show()

        # If we are spectating, make sure the boss cannot touch us
        if self.boss is not None:
            if self.localToonSpectating():
                self.boss.makeLocalToonSafe()
            else:
                self.boss.makeLocalToonUnsafe()

        if spectate and self.scoreboard is not None:
            if self.localToonSpectating():
                self.scoreboard.enableSpectating()
            else:
                self.scoreboard.disableSpectating()

    def load(self):
        self.notify.debug("load")
        DistributedMinigame.load(self)
        # load resources and create objects here

        self.music = base.loader.loadMusic('phase_7/audio/bgm/encntr_suit_winning_indoor.ogg')
        self.winSting = base.loader.loadSfx("phase_4/audio/sfx/MG_win.ogg")
        self.loseSting = base.loader.loadSfx("phase_4/audio/sfx/MG_lose.ogg")

        self.timerTickSfx = base.loader.loadSfx("phase_14/audio/sfx/tick.ogg")
        self.timerTickSfx.setPlayRate(.8)
        self.timerTickSfx.setVolume(.1)
        self.goSfx = base.loader.loadSfx('phase_14/audio/sfx/tick.ogg')
        self.goSfx.setVolume(.1)

        base.cr.forbidCheesyEffects(1)

        self.loadEnvironment()

        # Set up a physics manager for the cables and the objects
        # falling around in the room.
        self.physicsMgr = PhysicsManager()
        integrator = LinearEulerIntegrator()
        self.physicsMgr.attachLinearIntegrator(integrator)
        fn = ForceNode('gravity')
        self.fnp = self.geom.attachNewNode(fn)
        gravity = LinearVectorForce(0, 0, -32)
        fn.addForce(gravity)
        self.physicsMgr.addLinearForce(gravity)

        self.warningSfx = loader.loadSfx('phase_9/audio/sfx/CHQ_GOON_tractor_beam_alarmed.ogg')

    def loadEnvironment(self):
        self.endVault = loader.loadModel('phase_10/models/cogHQ/EndVault.bam')
        self.lightning = loader.loadModel('phase_10/models/cogHQ/CBLightning.bam')
        self.magnet = loader.loadModel('phase_10/models/cogHQ/CBMagnetBlue.bam')
        self.sideMagnet = loader.loadModel('phase_10/models/cogHQ/CBMagnetRed.bam')
        if base.config.GetBool('want-legacy-heads'):
            self.magnet = loader.loadModel('phase_10/models/cogHQ/CBMagnet.bam')
            self.sideMagnet = loader.loadModel('phase_10/models/cogHQ/CBMagnetRed.bam')
        self.craneArm = loader.loadModel('phase_10/models/cogHQ/CBCraneArm.bam')
        self.controls = loader.loadModel('phase_10/models/cogHQ/CBCraneControls.bam')
        self.stick = loader.loadModel('phase_10/models/cogHQ/CBCraneStick.bam')
        self.safe = loader.loadModel('phase_10/models/cogHQ/CBSafe.bam')
        self.cableTex = self.craneArm.findTexture('MagnetControl')

        # Position the two rooms relative to each other, and so that
        # the floor is at z == 0
        self.geom = NodePath('geom')
        self.endVault.setPos(84, -201, -6)
        self.endVault.reparentTo(self.geom)

        # Clear out unneeded backstage models from the EndVault, if
        # they're in the file.
        self.endVault.findAllMatches('**/MagnetArms').detach()
        self.endVault.findAllMatches('**/Safes').detach()
        self.endVault.findAllMatches('**/MagnetControlsAll').detach()

        # Flag the collisions in the end vault so safes and magnets
        # don't try to go through the wall.
        self.disableBackWall()

        # Get the rolling doors.

        # This is the door from the end vault back to the mid vault.
        # The boss makes his "escape" through this door.
        self.door3 = self.endVault.find('**/SlidingDoor/')

        # Find all the wall polygons and replace them with planes,
        # which are solid, so there will be zero chance of safes or
        # toons slipping through a wall.
        walls = self.endVault.find('**/RollUpFrameCillison')
        walls.detachNode()
        self.evWalls = self.replaceCollisionPolysWithPlanes(walls)
        self.evWalls.reparentTo(self.endVault)

        # Initially, these new planar walls are stashed, so they don't
        # cause us trouble in the intro movie or in battle one.  We
        # will unstash them when we move to battle three.
        self.evWalls.stash()

        # Also replace the floor polygon with a plane, and rename it
        # so we can detect a collision with it.
        floor = self.endVault.find('**/EndVaultFloorCollision')
        floor.detachNode()
        self.evFloor = self.replaceCollisionPolysWithPlanes(floor)
        self.evFloor.reparentTo(self.endVault)
        self.evFloor.setName('floor')

        # Also, put a big plane across the universe a few feet below
        # the floor, to catch things that fall out of the world.
        plane = CollisionPlane(Plane(Vec3(0, 0, 1), Point3(0, 0, -50)))
        planeNode = CollisionNode('dropPlane')
        planeNode.addSolid(plane)
        planeNode.setCollideMask(ToontownGlobals.PieBitmask)
        self.geom.attachNewNode(planeNode)
        self.geom.reparentTo(render)

    def replaceCollisionPolysWithPlanes(self, model):
        newCollisionNode = CollisionNode('collisions')
        newCollideMask = BitMask32(0)
        planes = []
        collList = model.findAllMatches('**/+CollisionNode')
        if not collList:
            collList = [model]
        for cnp in collList:
            cn = cnp.node()
            if not isinstance(cn, CollisionNode):
                self.notify.warning('Not a collision node: %s' % repr(cnp))
                break
            newCollideMask = newCollideMask | cn.getIntoCollideMask()
            for i in range(cn.getNumSolids()):
                solid = cn.getSolid(i)
                if isinstance(solid, CollisionPolygon):
                    # Save the plane defined by this polygon
                    plane = Plane(solid.getPlane())
                    planes.append(plane)
                else:
                    self.notify.warning('Unexpected collision solid: %s' % repr(solid))
                    newCollisionNode.addSolid(plane)

        newCollisionNode.setIntoCollideMask(newCollideMask)

        # Now sort all of the planes and remove the nonunique ones.
        # We can't use traditional dictionary-based tricks, because we
        # want to use Plane.compareTo(), not Plane.__hash__(), to make
        # the comparison.
        threshold = 0.1
        planes.sort(key=functools.cmp_to_key(lambda p1, p2: p1.compareTo(p2, threshold)))
        lastPlane = None
        for plane in planes:
            if lastPlane is None or plane.compareTo(lastPlane, threshold) != 0:
                cp = CollisionPlane(plane)
                newCollisionNode.addSolid(cp)
                lastPlane = plane

        return NodePath(newCollisionNode)

    def disableBackWall(self):
        if self.endVault is None:
            return

        try:
            cn = self.endVault.find('**/wallsCollision').node()
            cn.setIntoCollideMask(OTPGlobals.WallBitmask | ToontownGlobals.PieBitmask)  # TTCC No Back Wall
        except:
            print('[Crane League] Failed to disable back wall.')

    def enableBackWall(self):
        if self.endVault is None:
            return

        try:
            cn = self.endVault.find('**/wallsCollision').node()
            cn.setIntoCollideMask(OTPGlobals.WallBitmask | ToontownGlobals.PieBitmask | BitMask32.lowerOn(3) << 21) #TTR Back Wall
        except:
            print('[Crane League] Failed to enable back wall.')

    def setToonsToBattleThreePos(self):
        """
        Places each toon at the desired position and orientation without creating
        or returning any animation tracks. The position and orientation are
        applied immediately.
        """

        # If we want custom crane spawns, completely override the spawn logic.
        if self.wantCustomCraneSpawns:
            for toon in self.getParticipantIdsNotSpectating():
                if toon in self.customSpawnPositions:
                    # Use the stored custom position for this toon
                    toonWantedPosition = self.customSpawnPositions[toon]
                else:
                    # Or pick a random spot if it doesn't exist
                    stop = 7 if len(self.getParticipantIdsNotSpectating()) <= 8 else 15
                    toonWantedPosition = random.randrange(0, stop)

                # Retrieve the position/HPR from the global constants
                posHpr = CraneLeagueGlobals.TOON_SPAWN_POSITIONS[toonWantedPosition]
                pos = Point3(*posHpr[0:3])
                hpr = VBase3(*posHpr[3:6])

                # Instantly set the toon's position/orientation
                toon.setPosHpr(pos, hpr)
            return

        # Otherwise, use the pre-defined spawn-point order as normal
        for i, toon in enumerate(self.getParticipantsNotSpectating()):
            spawn_index = self.toonSpawnpointOrder[i]
            posHpr = CraneLeagueGlobals.TOON_SPAWN_POSITIONS[spawn_index]
            pos = Point3(*posHpr[0:3])
            hpr = VBase3(*posHpr[3:6])
            toon.setPosHpr(pos, hpr)

        for toon in self.getSpectatingToons():
            toon.setPos(self.getBoss().getPos())

    def __displayOverlayText(self, text, color=(1, 1, 1, 1)):
        self.overlayText['text'] = text
        self.overlayText['fg'] = color
        self.overlayText.show()

    def __hideOverlayText(self):
        self.overlayText.hide()

    def __generatePrepareInterval(self):
        """
        Generates a cute little sequence where we pan the camera to our toon before we start a round.
        """

        players = self.getParticipantsNotSpectating()
        # This is just an edge case to prevent the client from crashing if somehow everyone is spectating.
        if len(players) <= 0:
            return Sequence(
                Wait(CraneGameGlobals.PREPARE_DELAY + CraneGameGlobals.PREPARE_LATENCY_FACTOR),
                Func(self.gameFSM.request, 'play'),
            )

        # If this is a solo crane round, we are not going to play a cutscene. Get right into the action.
        if len(players) == 1:
            return Sequence(
                Wait(CraneGameGlobals.PREPARE_LATENCY_FACTOR),
                Func(self.gameFSM.request, 'play'),
            )

        # Generate a camera track so that the camera slowly pans on to the toon.
        toon = base.localAvatar if not self.localToonSpectating() else self.getParticipantsNotSpectating()[0]
        targetCameraPos = render.getRelativePoint(toon, Vec3(0, -10, toon.getHeight()))
        startCameraHpr = Point3(reduceAngle(camera.getH()), camera.getP(), camera.getR())
        cameraTrack = LerpPosHprInterval(camera, CraneGameGlobals.PREPARE_DELAY / 2.5, Point3(*targetCameraPos), Point3(reduceAngle(toon.getH()), 0, 0), startPos=camera.getPos(), startHpr=startCameraHpr, blendType='easeInOut')

        # Setup a countdown track to display when the round will start. Also at the end, start the game.
        countdownTrack = Sequence()
        for secondsLeft in range(5, 0, -1):
            color = RED_COUNTDOWN_COLOR if secondsLeft > 2 else (ORANGE_COUNTDOWN_COLOR if secondsLeft > 1 else YELLOW_COUNTDOWN_COLOR)
            countdownTrack.append(Func(self.__displayOverlayText, f"{secondsLeft}", color))
            countdownTrack.append(Func(base.playSfx, self.timerTickSfx))
            countdownTrack.append(Wait(1))
        countdownTrack.append(Func(self.__displayOverlayText, 'GO!', CraneGameGlobals.GREEN_COUNTDOWN_COLOR))
        countdownTrack.append(Func(base.playSfx, self.goSfx))
        countdownTrack.append(Wait(CraneGameGlobals.PREPARE_LATENCY_FACTOR))
        countdownTrack.append(Func(self.gameFSM.request, 'play'))

        return Parallel(cameraTrack, countdownTrack)

    def unload(self):
        self.notify.debug("unload")
        DistributedMinigame.unload(self)

        self.geom.removeNode()
        del self.geom

        self.fnp.removeNode()
        self.physicsMgr.clearLinearForces()
        self.music.stop()
        base.cr.forbidCheesyEffects(0)
        localAvatar.setCameraFov(ToontownGlobals.CogHQCameraFov)
        self.music.stop()
        taskMgr.remove(self.uniqueName('physics'))

        # unload resources and delete objects from load() here
        # remove our game ClassicFSM from the framework ClassicFSM
        self.removeChildGameFSM(self.gameFSM)
        del self.gameFSM

    def onstage(self):
        self.notify.debug("onstage")
        DistributedMinigame.onstage(self)
        # start up the minigame; parent things to render, start playing
        # music...
        # at this point we cannot yet show the remote players' toons
        base.localAvatar.reparentTo(render)
        base.localAvatar.loop('neutral')
        base.camLens.setFar(450.0)
        base.transitions.irisIn(0.4)
        NametagGlobals.setMasterArrowsOn(1)
        camera.reparentTo(render)
        camera.setPosHpr(119.541, -260.886, 20, 180, -20, 0)

        #self.setToonsToBattleThreePos()

        # All trolley games call this function, but I am commenting it oukkl12t because I have a suspicion that
        # global smooth node predictions are fighting with physics calculations with CFO objects.
        # I could be wrong, but this seems to be unnecessary since CFO objects appear just fine without this set.
        # DistributedSmoothNode.activateSmoothing(1, 1)

    def offstage(self):
        self.notify.debug("offstage")
        # stop the minigame; parent things to hidden, stop the
        # music...
        DistributedSmoothNode.activateSmoothing(1, 0)
        NametagGlobals.setMasterArrowsOn(0)
        base.camLens.setFar(ToontownGlobals.DefaultCameraFar)

        # the base class parents the toons to hidden, so consider
        # calling it last
        DistributedMinigame.offstage(self)

    def handleDisabledAvatar(self, avId):
        """This will be called if an avatar exits unexpectedly"""
        self.notify.debug("handleDisabledAvatar")
        self.notify.debug("avatar " + str(avId) + " disabled")
        # clean up any references to the disabled avatar before he disappears

        # then call the base class
        DistributedMinigame.handleDisabledAvatar(self, avId)

    def setGameReady(self):
        if not self.hasLocalToon: return
        self.notify.debug("setGameReady")
        if DistributedMinigame.setGameReady(self):
            return
        # all of the remote toons have joined the game;
        # it's safe to show them now.

        self.setToonsToRulesPositions()

        for toon in self.getParticipants():
            toon.startSmooth()

        base.localAvatar.d_clearSmoothing()
        base.localAvatar.sendCurrentPosition()
        base.localAvatar.b_setAnimState('neutral', 1)
        base.localAvatar.b_setParent(ToontownGlobals.SPRender)

    def __generateRulesPanel(self):
        panel = CraneGameSettingsPanel(self.getTitle(), self.rulesDoneEvent)
        # Create toggle button
        btnGeom = loader.loadModel('phase_3/models/gui/quit_button')
        

        # Create play button next to settings
        self.playButton = DirectButton(
            relief=None,
            text='Play',
            text_scale=0.055,
            text_pos=(0, -0.02),
            geom=(btnGeom.find('**/QuitBtn_UP'),
                  btnGeom.find('**/QuitBtn_DN'),
                  btnGeom.find('**/QuitBtn_RLVR')),
            geom_scale=(0.7, 1, 1),
            pos=(-1.15, 0, 0.85),
            command=self.__handlePlayButton
        )
        self.playButton.hide()  # Play button starts hidden
        
        # Create participants button next to play button
        self.participantsButton = DirectButton(
            relief=None,
            text='Participants',
            text_scale=0.055,
            text_pos=(0, -0.02),
            geom=(btnGeom.find('**/QuitBtn_UP'),
                  btnGeom.find('**/QuitBtn_DN'),
                  btnGeom.find('**/QuitBtn_RLVR')),
            geom_scale=(0.7, 1, 1),
            pos=(-0.75, 0, 0.85),
            command=self.__handleParticipantsButton
        )
        self.participantsButton.hide()  # Participants button starts hidden
        
        # Create best of button next to participants button
        self.bestOfButton = DirectButton(
            relief=None,
            text=f'Best of {self.bestOfValue}',
            text_scale=0.055,
            text_pos=(0, -0.02),
            geom=(btnGeom.find('**/QuitBtn_UP'),
                  btnGeom.find('**/QuitBtn_DN'),
                  btnGeom.find('**/QuitBtn_RLVR')),
            geom_scale=(0.7, 1, 1),
            pos=(-0.35, 0, 0.85),
            command=self.__handleBestOfButton
        )
        self.bestOfButton.hide()  # Best of button starts hidden
        
        btnGeom.removeNode()
        
        # Initialize participants panel variables
        self.participantsPanel = None
        self.participantsPanelVisible = False
        
        return panel

    def __handlePlayButton(self):
        messenger.send(self.rulesDoneEvent)

    def __handleParticipantsButton(self):
        """Toggle the participants panel visibility"""
        if self.participantsPanelVisible:
            self.__hideParticipantsPanel()
        else:
            self.__showParticipantsPanel()
    
    def __showParticipantsPanel(self):
        """Create and show the participants panel"""
        if self.participantsPanel is None:
            self.__createParticipantsPanel()
        
        self.participantsPanel.show()
        self.participantsPanelVisible = True
    
    def __hideParticipantsPanel(self):
        """Hide the participants panel"""
        if self.participantsPanel is not None:
            self.participantsPanel.hide()
        self.participantsPanelVisible = False
    
    def __createParticipantsPanel(self):
        """Create the participants management panel using proper game UI conventions"""
        
        # Create the main panel frame using proper dialog styling
        self.participantsPanel = DirectFrame(
            relief=None,
            image=DGG.getDefaultDialogGeom(),
            image_color=ToontownGlobals.GlobalDialogColor,
            image_scale=(1.4, 1, 1.2),
            pos=(0.8, 0, 0),
            parent=aspect2d,
            sortOrder=DGG.NO_FADE_SORT_INDEX
        )
        
        # Title label
        titleLabel = DirectLabel(
            parent=self.participantsPanel,
            relief=None,
            text="Manage Spawn Order",
            text_scale=0.08,
            text_pos=(0, 0.45),
            text_fg=(0.1, 0.1, 0.4, 1),
            text_font=ToontownGlobals.getInterfaceFont()
        )
        
        # Instructions label
        instructionsLabel = DirectLabel(
            parent=self.participantsPanel,
            relief=None,
            text="Use arrows to change spawn positions",
            text_scale=0.05,
            text_pos=(0, 0.35),
            text_fg=(0.3, 0.3, 0.3, 1),
            text_font=ToontownGlobals.getInterfaceFont()
        )
        
        # Load GUI assets for scroll list
        gui = loader.loadModel('phase_3.5/models/gui/friendslist_gui')
        
        # Create scrolled list for participants using proper game styling
        self.participantsList = DirectScrolledList(
            parent=self.participantsPanel,
            relief=None,
            pos=(0, 0, 0.05),
            numItemsVisible=6,
            forceHeight=0.08,
            itemFrame_frameSize=(-0.6, 0.6, -0.04, 0.04),
            itemFrame_pos=(0, 0, 0),
            itemFrame_relief=DGG.SUNKEN,
            itemFrame_frameColor=(0.85, 0.95, 1, 1),
            itemFrame_borderWidth=(0.01, 0.01),
            # Scroll buttons using proper assets
            incButton_image=(gui.find('**/FndsLst_ScrollUp'),
                           gui.find('**/FndsLst_ScrollDN'),
                           gui.find('**/FndsLst_ScrollUp_Rllvr'),
                           gui.find('**/FndsLst_ScrollUp')),
            incButton_relief=None,
            incButton_scale=(1.0, 1.0, -1.0),
            incButton_pos=(0.5, 0, -0.35),
            incButton_image3_color=Vec4(0.6, 0.6, 0.6, 0.6),
            decButton_image=(gui.find('**/FndsLst_ScrollUp'),
                           gui.find('**/FndsLst_ScrollDN'),
                           gui.find('**/FndsLst_ScrollUp_Rllvr'),
                           gui.find('**/FndsLst_ScrollUp')),
            decButton_relief=None,
            decButton_scale=(1.0, 1.0, 1.0),
            decButton_pos=(0.5, 0, 0.25),
            decButton_image3_color=Vec4(0.6, 0.6, 0.6, 0.6)
        )
        
        # Load button assets
        buttons = loader.loadModel('phase_3/models/gui/dialog_box_buttons_gui')
        closeButtonImage = (buttons.find('**/CloseBtn_UP'), 
                          buttons.find('**/CloseBtn_DN'), 
                          buttons.find('**/CloseBtn_Rllvr'))
        
        # Close button using proper styling
        closeButton = DirectButton(
            parent=self.participantsPanel,
            relief=None,
            image=closeButtonImage,
            text="Close",
            text_scale=0.05,
            text_pos=(0, -0.1),
            pos=(0, 0, -0.45),
            command=self.__hideParticipantsPanel
        )
        
        # Clean up loaded models
        gui.removeNode()
        buttons.removeNode()
        
        # Populate the list with current participants
        self.__updateParticipantsList()
        
        # Initially hide the panel
        self.participantsPanel.hide()
    
    def __updateParticipantsList(self):
        """Update the participants list display with proper styling"""
        if self.participantsList is None:
            return
            
        # Clear existing items
        self.participantsList.removeAllItems()
        
        # Load button assets for up/down arrows
        gui = loader.loadModel('phase_3.5/models/gui/friendslist_gui')
        arrowUpImage = (gui.find('**/FndsLst_ScrollUp'),
                       gui.find('**/FndsLst_ScrollDN'),
                       gui.find('**/FndsLst_ScrollUp_Rllvr'),
                       gui.find('**/FndsLst_ScrollUp'))
        arrowDownImage = (gui.find('**/FndsLst_ScrollUp'),
                         gui.find('**/FndsLst_ScrollDN'),
                         gui.find('**/FndsLst_ScrollUp_Rllvr'),
                         gui.find('**/FndsLst_ScrollUp'))
        
        # Get participating toons (not spectating)
        participatingToons = self.getParticipantsNotSpectating()
        
        # Create items for each participating toon in spawn order
        for i, toon in enumerate(participatingToons):
            if i >= len(self.toonSpawnpointOrder):
                break  # Safety check
                
            spawnIndex = self.toonSpawnpointOrder[i]
            toonName = toon.getName() if toon else f"Player {i+1}"
            
            # Create item frame
            itemFrame = DirectFrame(
                relief=None,
                frameSize=(-0.6, 0.6, -0.04, 0.04),
                frameColor=(0.9, 0.9, 0.9, 0.8) if i % 2 == 0 else (0.8, 0.8, 0.8, 0.8)
            )
            
            # Position number label (spawn order)
            posLabel = DirectLabel(
                parent=itemFrame,
                relief=None,
                text=f"{i+1}.",
                text_scale=0.035,
                text_pos=(-0.5, 0, 0),
                text_fg=(0.2, 0.2, 0.6, 1),
                text_font=ToontownGlobals.getInterfaceFont(),
                text_align=TextNode.ALeft
            )
            
            # Toon name label
            nameLabel = DirectLabel(
                parent=itemFrame,
                relief=None,
                text=toonName,
                text_scale=0.035,
                text_pos=(-0.2, 0, 0),
                text_fg=(0.1, 0.1, 0.1, 1),
                text_font=ToontownGlobals.getInterfaceFont(),
                text_align=TextNode.ALeft
            )
            
            # Spawn point label
            spawnLabel = DirectLabel(
                parent=itemFrame,
                relief=None,
                text=f"Spot {spawnIndex + 1}",
                text_scale=0.03,
                text_pos=(0.15, 0, 0),
                text_fg=(0.4, 0.4, 0.4, 1),
                text_font=ToontownGlobals.getInterfaceFont(),
                text_align=TextNode.ALeft
            )
            
            # Up arrow button (only if not first)
            if i > 0:
                upButton = DirectButton(
                    parent=itemFrame,
                    relief=None,
                    image=arrowUpImage,
                    image_scale=(0.4, 1, 0.4),
                    pos=(0.35, 0, 0),
                    command=self.__moveParticipantUp,
                    extraArgs=[i]
                )
            
            # Down arrow button (only if not last)
            if i < len(participatingToons) - 1:
                downButton = DirectButton(
                    parent=itemFrame,
                    relief=None,
                    image=arrowDownImage,
                    image_scale=(0.4, 1, -0.4),  # Negative scale to flip arrow
                    pos=(0.5, 0, 0),
                    command=self.__moveParticipantDown,
                    extraArgs=[i]
                )
            
            # Add to scrolled list
            self.participantsList.addItem(itemFrame)
        
        # Clean up loaded model
        gui.removeNode()

    def __moveParticipantUp(self, participantIndex):
        """Move a participant up in the spawn order"""
        if participantIndex > 0 and participantIndex < len(self.toonSpawnpointOrder):
            # Swap spawn point indices
            self.toonSpawnpointOrder[participantIndex], self.toonSpawnpointOrder[participantIndex - 1] = \
                self.toonSpawnpointOrder[participantIndex - 1], self.toonSpawnpointOrder[participantIndex]
            
            # Update the display
            self.__updateParticipantsList()
            
            # Send update to server if we're the leader
            self.__sendSpawnOrderUpdate()
    
    def __moveParticipantDown(self, participantIndex):
        """Move a participant down in the spawn order"""
        if participantIndex >= 0 and participantIndex < len(self.toonSpawnpointOrder) - 1:
            # Swap spawn point indices
            self.toonSpawnpointOrder[participantIndex], self.toonSpawnpointOrder[participantIndex + 1] = \
                self.toonSpawnpointOrder[participantIndex + 1], self.toonSpawnpointOrder[participantIndex]
            
            # Update the display
            self.__updateParticipantsList()
            
            # Send update to server if we're the leader
            self.__sendSpawnOrderUpdate()
    
    def __sendSpawnOrderUpdate(self):
        """Send the updated spawn order to the server"""
        # Only the leader can send spawn order updates
        if self.avIdList[0] == base.localAvatar.doId:
            # Send the updated spawn order to the AI
            self.sendUpdate('updateSpawnOrder', [self.toonSpawnpointOrder])

    def __cleanupRulesPanel(self):
        self.ignore(self.rulesDoneEvent)
        self.ignore('spotStatusChanged')
        if self.playButton is not None:
            self.playButton.destroy()
            self.playButton = None
        if self.participantsButton is not None:
            self.participantsButton.destroy()
            self.participantsButton = None
        if self.bestOfButton is not None:
            self.bestOfButton.destroy()
            self.bestOfButton = None
        if self.participantsPanel is not None:
            self.participantsPanel.destroy()
            self.participantsPanel = None
            self.participantsList = None
        self.participantsPanelVisible = False
        if self.rulesPanel is not None:
            self.rulesPanel.cleanup()
            self.rulesPanel = None

    def updateRequiredElements(self):
        self.bossSpeedrunTimer.cleanup()
        self.bossSpeedrunTimer = BossSpeedrunTimedTimer(
            time_limit=self.ruleset.TIMER_MODE_TIME_LIMIT) if self.ruleset.TIMER_MODE else BossSpeedrunTimer()
        self.bossSpeedrunTimer.hide()
        self.updateRulesetDependencies()

    def updateRulesetDependencies(self):
        # If the scoreboard was made then update the ruleset
        if self.scoreboard:
            self.scoreboard.set_ruleset(self.ruleset)

        self.heatDisplay.update(self.modifiers)

        if self.boss is not None:
            self.boss.setRuleset(self.ruleset)

    def setRawRuleset(self, attrs):
        self.ruleset = CraneLeagueGlobals.CraneGameRuleset.fromStruct(attrs)
        self.updateRulesetDependencies()

    def getRawRuleset(self):
        return self.ruleset.asStruct()

    def getRuleset(self):
        return self.ruleset

    def __doPhysics(self, task):
        dt = globalClock.getDt()
        self.physicsMgr.doPhysics(dt)
        return task.cont

    def setGameStart(self, timestamp):
        if not self.hasLocalToon: return
        self.notify.debug("setGameStart")
        # base class will cause gameFSM to enter initial state
        DistributedMinigame.setGameStart(self, timestamp)
        # all players have finished reading the rules,
        # and are ready to start playing.
        # transition to the appropriate state
        self.gameFSM.request("prepare")

    # these are enter and exit functions for the game's
    # fsm (finite state machine)

    def enterOff(self):
        self.notify.debug("enterOff")
        self.__checkSpectatorState(spectate=False)
        self.__cleanupRulesPanel()

    def exitOff(self):
        pass

    def enterPrepare(self):

        # Make all laff meters blink when in uber mode
        messenger.send('uberThreshold', [self.ruleset.LOW_LAFF_BONUS_THRESHOLD])

        camera.wrtReparentTo(render)
        self.setToonsToBattleThreePos()
        base.localAvatar.d_clearSmoothing()
        base.localAvatar.sendCurrentPosition()
        base.localAvatar.b_setAnimState('neutral', 1)
        base.localAvatar.b_setParent(ToontownGlobals.SPRender)

        # Display Modifiers Heat
        self.updateRequiredElements()

        # Setup the scoreboard
        self.scoreboard.clearToons()
        for avId in self.getParticipantIdsNotSpectating():
            self.scoreboard.addToon(avId)

        self.introductionMovie = self.__generatePrepareInterval()
        self.introductionMovie.start()
        self.boss.prepareBossForBattle()

        # Make absolutely sure all indicators are cleaned up
        self.removeStatusIndicators()

    def exitPrepare(self):
        self.introductionMovie.pause()
        self.introductionMovie = None
        self.__hideOverlayText()

    def enterPlay(self):
        self.__cleanupRulesPanel()
        taskMgr.remove(self.uniqueName("craneGameVictory"))
        self.notify.debug("enterPlay")
        self.evWalls.unstash()
        base.playMusic(self.music, looping=1, volume=0.9)

        # Make absolutely sure all indicators are cleaned up
        self.removeStatusIndicators()

        # It is important to make sure this task runs immediately
        # before the collisionLoop of ShowBase.  That will fix up the
        # z value of the safes, etc., before their position is
        # distributed.
        taskMgr.remove(self.uniqueName("physics"))
        taskMgr.add(self.__doPhysics, self.uniqueName('physics'), priority=25)

        # Allow us to play the game.
        self.walkStateData.enter()
        localAvatar.orbitalCamera.start()
        localAvatar.setCameraFov(ToontownGlobals.BossBattleCameraFov)
        self.toFinalBattleMode()

        # Display Boss Timer
        self.bossSpeedrunTimer.reset()
        self.bossSpeedrunTimer.start_updating()
        self.bossSpeedrunTimer.show()

        self.boss.prepareBossForBattle()

        self.accept("LocalSetFinalBattleMode", self.toFinalBattleMode)
        self.accept("LocalSetOuchMode", self.toOuchMode)
        self.accept("ChatMgr-enterMainMenu", self.chatClosed)

        if base.WANT_FOV_EFFECTS and base.localAvatar.isSprinting:
            base.localAvatar.lerpFov(base.localAvatar.fov, base.localAvatar.fallbackFov + base.localAvatar.currentMovementMode[base.localAvatar.FOV_INCREASE_ENUM])

        self.__checkSpectatorState()
        self.eventRecorder.add_event(RoundBeginEvent(time.time()))

    def exitPlay(self):
        if self.boss is not None:
            self.boss.cleanupBossBattle()
        
        self.scoreboard.disableSpectating()
        self.scoreboard.finish()

        self.walkStateData.exit()

        # Clean up any elemental indicators
        for safeDoId in list(self.fireElementalIndicators.keys()):
            self.__removeElementalIndicator(safeDoId)
        self.fireElementalIndicators.clear()
        
        # Clean up CFO elemental effects
        for elementType in list(self.cfoElementalEffects.keys()):
            self.__removeCFOElementalEffect(elementType)
        self.cfoElementalEffects.clear()
        
        # Clean up all CFO color effects
        self.clearAllCFOColorEffects()
        
        # Reset CFO color scale to normal if boss exists
        if self.boss:
            try:
                self.boss.setColorScale(1.0, 1.0, 1.0, 1.0)
            except:
                pass
        
        # We just need to clean up the victory state
        return Task.done

    def enterVictory(self):
        if self.victor == 0:
            return

        victor = base.cr.getDo(self.victor)
        if self.victor == self.localAvId:
            base.playSfx(self.winSting)
        else:
            base.playSfx(self.loseSting)
        camera.reparentTo(victor)
        camera.setPosHpr(0, 8, victor.getHeight() / 2.0, 180, 0, 0)

        victor.setAnimState("victory")

        # Check if this is a multi-round match
        if self.bestOfValue > 1:
            # Check round wins
            roundWins = self.roundWins.get(self.victor, 0)
            winsNeeded = (self.bestOfValue + 1) // 2
            if roundWins >= winsNeeded:
                # Match is over - use normal victory flow
                taskMgr.doMethodLater(5, self.gameOver, self.uniqueName("craneGameVictory"), extraArgs=[])
            else:
                # Round is over, but match continues - shorter victory time
                taskMgr.doMethodLater(5, self.__nextRound, self.uniqueName("craneGameNextRound"), extraArgs=[])
        else:
            # Single round match
            taskMgr.doMethodLater(5, self.gameOver, self.uniqueName("craneGameVictory"), extraArgs=[])
        
        for crane in self.cranes.values():
            crane.stopFlicker()

        player = self.eventRecorder.get_metadata().get_or_create_player(self.victor, victor.getName())
        self.eventRecorder.add_event(RoundEndEvent(time.time(), player.get_id()))

    def exitVictory(self):
        taskMgr.remove(self.uniqueName("craneGameVictory"))
        taskMgr.remove(self.uniqueName("craneGameNextRound"))
        camera.reparentTo(base.localAvatar)

    def enterCleanup(self):
        self.notify.debug("enterCleanup")
        self.__cleanupRulesPanel()
        
        # Clean up fire elemental indicators
        for safeDoId in list(self.fireElementalIndicators.keys()):
            self.__removeElementalIndicator(safeDoId)
        
        for toon in self.getParticipants():
            toon.setGhostMode(False)
            toon.show()
            toon.setZ(0) # Reset Z position
        self.overlayText.removeNode()
        self.bossSpeedrunTimer.cleanup()
        del self.bossSpeedrunTimer
        self.scoreboard.cleanup()
        self.scoreboard = None
        self.heatDisplay.cleanup()
        self.heatDisplay = None
        self.boss = None

        self.__saveMatch()

    def __saveMatch(self):
        match_serializer.save(self.eventRecorder)

    def exitCleanup(self):
        pass

    """
    Updates from server to client
    """

    def setBossCogId(self, bossCogId: int) -> None:
        self.boss = base.cr.getDo(bossCogId)
        self.boss.game = self
        self.boss.prepareBossForBattle()
        self.boss.setRuleset(self.ruleset)

    def addScore(self, avId: int, score: int, reason: str):

        # Convert the reason into a valid reason enum that our scoreboard accepts.
        convertedReason = CraneLeagueGlobals.ScoreReason.from_astron(reason)
        if convertedReason is None:
            convertedReason = CraneLeagueGlobals.ScoreReason.DEFAULT
        self.scoreboard.addScore(avId, score, convertedReason)

        av = base.cr.getDo(avId)
        if av:
            player = self.eventRecorder.get_metadata().get_or_create_player(av.getDoId(), name=av.getName())
            self.eventRecorder.add_event(PointEvent(
                time.time(),
                player.get_id(),
                PointEvent.Reason.from_value(convertedReason.value),
                score
            ))

    def updateCombo(self, avId, comboLength):
        self.scoreboard.setCombo(avId, comboLength)

        av = base.cr.getDo(avId)
        if av is not None:
            player = self.eventRecorder.get_metadata().get_or_create_player(av.getDoId(), name=av.getName())
            self.eventRecorder.add_event(ComboChangeEvent(time.time(), player.get_id(), comboLength))

    def updateTimer(self, secs):
        self.bossSpeedrunTimer.override_time(secs)
        self.bossSpeedrunTimer.update_time()

    def declareVictor(self, avId: int) -> None:
        self.victor = avId
        self.gameFSM.request("victory")

    def setOvertime(self, flag):
        if flag == CraneLeagueGlobals.OVERTIME_FLAG_START:
            self.overtimeActive = True
            self.ruleset.REVIVE_TOONS_UPON_DEATH = False
        elif flag == CraneLeagueGlobals.OVERTIME_FLAG_ENABLE:
            self.bossSpeedrunTimer.show_overtime()
        else:
            self.overtimeActive = False
            self.bossSpeedrunTimer.hide_overtime()

    def setModifiers(self, mods):
        modsToSet = []  # A list of CFORulesetModifierBase subclass instances
        for modStruct in mods:
            modsToSet.append(CraneLeagueGlobals.CFORulesetModifierBase.fromStruct(modStruct))

        self.modifiers = modsToSet
        self.modifiers.sort(key=lambda m: m.MODIFIER_TYPE)
        self.heatDisplay.update(self.modifiers)

    def restart(self):
        """
        Called via astron update. Do any client side logic needed in order to restart the game.
        """
        self.gameFSM.request('prepare')

    """
    Everything else!!!!
    """

    def deactivateCranes(self):
        # This locally knocks all toons off cranes.
        for crane in self.cranes.values():
            crane.demand('Free')

    def hideBattleThreeObjects(self):
        # This turns off all the goons, safes, and cranes on the local
        # client. It's played only during the victory movie, to get
        # these guys out of the way.
        for goon in self.goons:
            goon.demand('Off')

        for safe in self.safes.values():
            safe.demand('Off')

        for crane in self.cranes.values():
            crane.demand('Off')

    def toonDied(self, avId):
        self.scoreboard.toonDied(avId)

    def revivedToon(self, avId):
        self.scoreboard.toonRevived(avId)
        if avId == base.localAvatar.doId:
            self.boss.localToonIsSafe = False
            base.localAvatar.stunToon()

    def getBoss(self):
        return self.boss

    def toCraneMode(self):
        self.walkStateData.fsm.request('crane')

    def toFinalBattleMode(self, checkForOuch: bool = False):
        if not checkForOuch or self.walkStateData.fsm.getCurrentState().getName() != 'ouch':
            self.walkStateData.fsm.request('walking')

    def toOuchMode(self):
        self.walkStateData.fsm.request('ouch')

    def chatClosed(self):
        if self.walkStateData.fsm.getCurrentState().getName() == "walking":
            base.localAvatar.enableAvatarControls()

    def setToonsToRulesPositions(self):
        """
        Places toons in front of the vault during the rules state.
        Creates a symmetric linear layout with multiple rows that expand from the center.
        """
        centerPoint = self.endVault.getPos()
        spacing = 5.5  # Horizontal space between toons
        rowSpacing = 5.5  # Space between rows
        
        # Get all participants, both playing and spectating
        allToons = self.getParticipants()
        numToons = len(allToons)
        
        # Calculate optimal row configuration
        if numToons <= 6:
            # Single row for 6 or fewer toons
            numRows = 1
            toonsPerRow = numToons
            baseY = centerPoint.getY() - 92  # Center position for single row
        elif numToons <= 12:
            # Two rows for 7-12 toons
            numRows = 2
            toonsPerRow = (numToons + 1) // 2
            baseY = centerPoint.getY() - 90  # Move first row forward from center
        else:
            # Three rows for 13-16 toons
            numRows = 3
            toonsPerRow = (numToons + 2) // 3
            baseY = centerPoint.getY() - 88  # Move first row even more forward
        
        # Position each toon
        toonIndex = 0
        for row in range(numRows):
            # Calculate how many toons go in this row
            toonsThisRow = min(toonsPerRow, numToons - (row * toonsPerRow))
            if toonsThisRow <= 0:
                break
                
            # Calculate row-specific adjustments
            rowWidth = (toonsThisRow - 1) * spacing
            rowStartX = centerPoint.getX() + 36 - (rowWidth / 2)
            rowY = baseY - (row * rowSpacing)  # Each back row moves back by rowSpacing
            
            # Position toons in this row
            for i in range(toonsThisRow):
                toon = allToons[toonIndex]
                if not toon:
                    continue
                
                # Calculate position
                x = rowStartX + (i * spacing)
                y = rowY
                z = 0
                h = 0
                
                # Position the toon
                if toon.doId == base.localAvatar.doId:
                    toon.setPos(x, y, z)
                    toon.setH(h)
                    toon.d_setXY(x, y)
                    toon.d_setH(h)
                    if hasattr(toon, 'd_clearSmoothing'):
                        toon.d_clearSmoothing()
                    if hasattr(toon, 'sendCurrentPosition'):
                        toon.sendCurrentPosition()
                else:
                    toon.setPos(x, y, z)
                    toon.setH(h)
                    if hasattr(toon, 'clearSmoothing'):
                        toon.clearSmoothing()
                    if hasattr(toon, 'startSmooth'):
                        toon.startSmooth()
                
                # Create or update status indicator
                isPlayer = toon.doId not in self.getSpectators()
                if toon.doId in self.statusIndicators:
                    self.updateStatusIndicator(toon, isPlayer)
                else:
                    self.createStatusIndicator(toon, isPlayer)
                
                toonIndex += 1

    def enterFrameworkRules(self):
        self.notify.debug('enterFrameworkRules')
        self.accept(self.rulesDoneEvent, self.handleRulesDone)
        
        # Create and show the rules panel
        self.rulesPanel = self.__generateRulesPanel()
        self.rulesPanel.load()
        # Hide the panel by default
        self.rulesPanel.hide()

        # Only show the play and participants buttons for the leader (first player in avIdList)
        if self.avIdList[0] == base.localAvatar.doId:
            self.playButton.show()
            self.participantsButton.show()
            self.bestOfButton.show()
        else:
            # Non-leader players automatically trigger ready
            messenger.send(self.rulesDoneEvent)

        # Position toons in the rules formation
        self.setToonsToRulesPositions()

        # Only setup click detection for the leader
        if self.avIdList[0] == base.localAvatar.doId:
            # Make sure the click ray is using our spotlight bitmask
            self.clickRayNode.setFromCollideMask(self.spotlightBitMask)
            self.accept('mouse1', self.handleMouseClick)

        # Hide all toon shadows
        for toon in self.getParticipants():
            if toon and hasattr(toon, 'dropShadow') and toon.dropShadow:
                toon.dropShadow.hide()

        # Accept spot status change messages
        self.accept('spotStatusChanged', self.handleSpotStatusChanged)

    def exitFrameworkRules(self):
        # Restore all toon shadows
        for toon in self.getParticipants():
            if toon and hasattr(toon, 'dropShadow') and toon.dropShadow:
                toon.dropShadow.show()
        
        # Clean up click detection
        self.ignore('mouse1')
            
        # Make sure to clean up all indicators
        self.removeStatusIndicators()
        self.__cleanupRulesPanel()

    def handleMouseClick(self):
        """Handle mouse clicks during the rules state to detect clicks on spotlights."""
        # Only the leader can click
        if self.avIdList[0] != base.localAvatar.doId:
            return
        
        # Get the mouse position
        if not base.mouseWatcherNode.hasMouse():
            return
        
        mpos = base.mouseWatcherNode.getMouse()
        
        # Set up the collision ray
        self.clickRay.setFromLens(base.camNode, mpos.getX(), mpos.getY())
        
        # Traverse and check for collisions
        base.cTrav.traverse(render)
        
        # Check the collision queue
        if self.clickRayQueue.getNumEntries() > 0:
            self.clickRayQueue.sortEntries()
            entry = self.clickRayQueue.getEntry(0)
            clickedNode = entry.getIntoNodePath()
            pickedObject = clickedNode.findNetTag('toonId')
            
            if not pickedObject.isEmpty():
                avId = int(pickedObject.getTag('toonId'))
                # Find the index of this toon in avIdList
                if avId in self.avIdList:
                    spotIndex = self.avIdList.index(avId)
                    # Toggle the status - if they're in spectators, make them a player and vice versa
                    currentlySpectating = avId in self.getSpectators()
                    # Send update to server to handle the status change
                    self.sendUpdate('handleSpotStatusChanged', [spotIndex, currentlySpectating])

    def handleRulesDone(self):
        self.notify.debug('BASE: handleRulesDone')
        self.sendUpdate('setAvatarReady', [])
        self.frameworkFSM.request('frameworkWaitServerStart')

    def handleSpotStatusChanged(self, spotIndex, isPlayer):
        """
        Called when a spot's status is changed between Player and Spectator.
        This is called on all clients when any client changes a spot's status.
        """
        if spotIndex >= len(self.avIdList):
            return
            
        changedAvId = self.avIdList[spotIndex]
        changedToon = self.cr.getDo(changedAvId)
        if changedToon:
                if changedAvId in self.statusIndicators:
                    self.updateStatusIndicator(changedToon, isPlayer)
                else:
                    self.createStatusIndicator(changedToon, isPlayer)

    def createStatusIndicator(self, toon, isPlayer):
        """Creates a spotlight indicator for a toon's status (player or spectator)"""
        # Create the camera model and spotlight effect
        indicator = NodePath('statusIndicator')
        indicator.reparentTo(render)
            
        # Position the camera above
        cameraHeight = 8
        projector = Point3(0, 0, cameraHeight)
        
        # Create the beam and floor nodes
        beamNode = indicator.attachNewNode('beamNode')
        floorNode = indicator.attachNewNode('floorNode')
        
        # Setup rendering attributes for both
        for node in (beamNode, floorNode):
            node.setTransparency(1)
            node.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha, ColorBlendAttrib.OOne))
            node.setTwoSided(False)
            node.setDepthWrite(False)
        
        # Create geometry for beam and floor
        beamVertexData = GeomVertexData('beam', GeomVertexFormat.getV3cp(), Geom.UHDynamic)
        floorVertexData = GeomVertexData('floor', GeomVertexFormat.getV3cp(), Geom.UHDynamic)
        
        beamVertexWriter = GeomVertexWriter(beamVertexData, 'vertex')
        beamColorWriter = GeomVertexWriter(beamVertexData, 'color')
        floorVertexWriter = GeomVertexWriter(floorVertexData, 'vertex')
        floorColorWriter = GeomVertexWriter(floorVertexData, 'color')
        
        # Default colors (will be updated in updateStatusIndicator)
        normalColor = VBase4(0.2, 0.2, 0.2, 0.3)
        
        # Create beam geometry (from projector to ground)
        radius = 1.8
        beamVertexWriter.addData3f(projector[0], projector[1], projector[2])
        beamColorWriter.addData4f(normalColor)
        
        # Create circle points for beam
        for angle in range(0, 360, 45):
            x = radius * math.cos(math.radians(angle))
            y = radius * math.sin(math.radians(angle))
            beamVertexWriter.addData3f(x, y, 0.025)
            beamColorWriter.addData4f(VBase4(0, 0, 0, 0))
            
        # Create floor geometry (circle on ground)
        floorVertexWriter.addData3f(0, 0, 0.025)
        floorColorWriter.addData4f(normalColor)
        
        # Create circle points for floor
        for angle in range(0, 360, 10):
            x = radius * math.cos(math.radians(angle))
            y = radius * math.sin(math.radians(angle))
            floorVertexWriter.addData3f(x, y, 0.025)
            floorColorWriter.addData4f(VBase4(0, 0, 0, 0))
            
        # Create beam triangles
        beamTris = GeomTrifans(Geom.UHStatic)
        beamTris.addVertex(0)
        for i in range(1, 9):
            beamTris.addVertex(i)
        beamTris.addVertex(1)
        beamTris.closePrimitive()
        
        # Create floor triangles
        floorTris = GeomTrifans(Geom.UHStatic)
        floorTris.addVertex(0)
        for i in range(1, 37):
            floorTris.addVertex(i)
        floorTris.addVertex(1)
        floorTris.closePrimitive()
        
        # Create and attach geometry nodes
        beamGeom = Geom(beamVertexData)
        beamGeom.addPrimitive(beamTris)
        beamGeomNode = GeomNode('beam')
        beamGeomNode.addGeom(beamGeom)
        beamNode.attachNewNode(beamGeomNode)
        
        floorGeom = Geom(floorVertexData)
        floorGeom.addPrimitive(floorTris)
        floorGeomNode = GeomNode('floor')
        floorGeomNode.addGeom(floorGeom)
        floorNode.attachNewNode(floorGeomNode)

        # Add collision cylinder for clicking
        if self.avIdList[0] == base.localAvatar.doId:  # Only leader gets collision
            radius = 1  # Same radius as the spotlight
            collTube = CollisionTube(0, 0, 4, 0, 0, 1.2, radius)  # point1_x, point1_y, point1_z, point2_x, point2_y, point2_z, radius
            collNode = CollisionNode(f'spotlightSphere-{toon.doId}')  # Keep the same node name for consistency
            collNode.addSolid(collTube)
            collNode.setIntoCollideMask(self.spotlightBitMask)
            collPath = indicator.attachNewNode(collNode)
            collPath.setTag('toonId', str(toon.doId))
        
        # Store the indicator
        self.statusIndicators[toon.doId] = indicator
        
        # Update position and appearance
        self.updateStatusIndicator(toon, isPlayer)

    def updateStatusIndicator(self, toon, isPlayer):
        """Updates an existing status indicator's position and appearance"""
        indicator = self.statusIndicators.get(toon.doId)
        if indicator:
            # Update position to follow toon
            pos = toon.getPos(render)
            indicator.setPos(pos[0], pos[1], 0)
            
            # Remaining vertices (bottom of beam) fade to transparent
            transparent = VBase4(0, 0, 0, 0)
            # Set color based on player status with reduced intensity
            if isPlayer:
                color = VBase4(0.1, 0.8, 0.1, 1)  # Softer green for players
                transparent = VBase4(0, 0.1, 0, 0.1)
            else:
                color = VBase4(0.8, 0.1, 0.1, 1)  # Softer red for spectators
                transparent = VBase4(0.1, 0, 0, 0.1)
            # Update the color for both beam and floor nodes
            beamNode = indicator.find('beamNode')
            floorNode = indicator.find('floorNode')
            
            # Get the GeomNode for each
            beamGeom = beamNode.find('beam').node()
            floorGeom = floorNode.find('floor').node()
            
            # Update vertex colors for beam
            beamVertexData = beamGeom.modifyGeom(0).modifyVertexData()
            beamColorWriter = GeomVertexWriter(beamVertexData, 'color')
            
            # First vertex (top of beam) gets full color
            beamColorWriter.setData4f(color)
            for _ in range(8):
                beamColorWriter.setData4f(transparent)
                
            # Update vertex colors for floor
            floorVertexData = floorGeom.modifyGeom(0).modifyVertexData()
            floorColorWriter = GeomVertexWriter(floorVertexData, 'color')
            
            # Center point gets full color
            floorColorWriter.setData4f(color)
            # Outer points fade to transparent
            for _ in range(36):
                floorColorWriter.setData4f(transparent)

    def removeStatusIndicators(self):
        """Removes all status indicators and cleans up their nodes."""
        for indicator in self.statusIndicators.values():
            if not indicator.isEmpty():
                indicator.removeNode()
        self.statusIndicators.clear()

    def enterFrameworkWaitServerStart(self):
        self.notify.debug('BASE: enterFrameworkWaitServerStart')
        if self.numPlayers > 1:
            msg = "Waiting for Group Leader to start..."
        else:
            msg = TTLocalizer.MinigamePleaseWait
        self.waitingStartLabel['text'] = msg
        self.waitingStartLabel.show()

    def setToonSpawnpointOrder(self, order):
        """Receive updated spawn order from server"""
        self.toonSpawnpointOrder = order[:]
        self.notify.info(f"Received spawn order update: {self.toonSpawnpointOrder}")
        
        # Update the participants panel if it's visible
        if self.participantsPanelVisible and self.participantsList is not None:
            self.__updateParticipantsList()

    def __handleBestOfButton(self):
        """Handle the "Best of" button click"""
        # Cycle through Best of 1, 3, 5, 7
        if self.bestOfValue == 1:
            self.bestOfValue = 3
        elif self.bestOfValue == 3:
            self.bestOfValue = 5
        elif self.bestOfValue == 5:
            self.bestOfValue = 7
        else:
            self.bestOfValue = 1
        
        # Update button text
        self.bestOfButton['text'] = f'Best of {self.bestOfValue}'
        
        # Send update to server if we're the leader
        if self.avIdList[0] == base.localAvatar.doId:
            self.sendUpdate('setBestOf', [self.bestOfValue])

    def setBestOf(self, value):
        """Receive best-of setting from server"""
        self.bestOfValue = value
        if self.bestOfButton:
            self.bestOfButton['text'] = f'Best of {self.bestOfValue}'
        self.notify.info(f"Best of value set to: {self.bestOfValue}")

    def setRoundInfo(self, currentRound, roundWins):
        """Receive round information from server"""
        self.currentRound = currentRound
        
        # Convert roundWins list back to dict using avIdList
        self.roundWins = {}
        for i, avId in enumerate(self.avIdList):
            if i < len(roundWins):
                self.roundWins[avId] = roundWins[i]
        
        # Update scoreboard with round information
        if self.scoreboard:
            self.scoreboard.setRoundInfo(currentRound, roundWins, self.bestOfValue)

    def setElementalMode(self, enabled):
        """Receive elemental mode setting from server"""
        self.elementalMode = enabled
        self.notify.info(f"Elemental mode set to: {'On' if self.elementalMode else 'Off'}")

    def setSafeElemental(self, safeDoId, elementType):
        """Handle elemental status updates from server - generic method for all element types"""
        if elementType == ElementType.NONE:
            self.__removeElementalIndicator(safeDoId)
        else:
            self.__createElementalIndicator(safeDoId, elementType)

    def __createFireElementalIndicator(self, safeDoId):
        """Create a 'Fire' text indicator above a safe - legacy method for compatibility"""
        self.__createElementalIndicator(safeDoId, ElementType.FIRE)

    def __removeFireElementalIndicator(self, safeDoId):
        """Remove the fire elemental indicator from a safe - legacy method for compatibility"""
        self.__removeElementalIndicator(safeDoId)

    def __createElementalIndicator(self, safeDoId, elementType):
        """Create an elemental text indicator above a safe based on element type"""
        # Define element-specific visual properties
        elementProperties = {
            ElementType.FIRE: {
                'useParticles': True,  # Use particle effects instead of text
                'text': 'FIRE',
                'color': (1.0, 0.4, 0.0, 1.0),  # Orange-red
                'scale': 1.5,
                'height': 10
            },
            ElementType.VOLT: {
                'useParticles': True,  # Use particle effects for VOLT too
                'text': 'VOLT',
                'color': (1.0, 0.98, 0.0, 1.0),  # Electric yellow
                'scale': 1.5,
                'height': 10
            },
            # Future elements can have different visual styles:
            # ElementType.ICE: {
            #     'text': 'Ice',
            #     'color': (0.3, 0.7, 1, 1),  # Light blue
            #     'scale': 1.4,
            #     'height': 18
            # },
            # ElementType.POISON: {
            #     'text': 'Poison',
            #     'color': (0.5, 1, 0.2, 1),  # Bright green
            #     'scale': 1.3,
            #     'height': 22
            # }
        }
        
        if elementType not in elementProperties:
            self.notify.warning(f"Unknown element type for indicator: {elementType}")
            return
            
        props = elementProperties[elementType]
        
        # Find the safe object
        safe = None
        if self.boss and hasattr(self.boss, 'safes'):
            for safeIndex, safeObj in self.boss.safes.items():
                if safeObj.doId == safeDoId:
                    safe = safeObj
                    break
        
        # Fallback: search through distributed objects by doId
        if not safe:
            safe = base.cr.doId2do.get(safeDoId)
        
        if not safe:
            self.notify.warning(f"Could not find safe {safeDoId} for elemental indicator")
            return
        
        # Remove existing indicator if present
        self.__removeElementalIndicator(safeDoId)
        
        if props.get('useParticles', False):
            # Create particle effects based on element type
            if elementType == ElementType.FIRE:
                elementalEffect = self.__createFireParticleEffect(safe, props)
            elif elementType == ElementType.VOLT:
                elementalEffect = self.__createVoltParticleEffect(safe, props)
            else:
                # Fallback to text for unknown particle types
                elementalEffect = self.__createTextIndicator(safe, props)
        else:
            # Create text indicator for other elements
            elementalEffect = self.__createTextIndicator(safe, props)
        
        # Store the indicator (using the old dict for compatibility)
        self.fireElementalIndicators[safeDoId] = elementalEffect
        
        elementName = props['text']
        self.notify.info(f"Created {elementName} elemental indicator for safe {safeDoId}")

    def __createFireParticleEffect(self, safe, props):
        """Create fire particle effects for Fire elemental safes"""
        
        # Load the battle particles system
        BattleParticles.loadParticles()
        
        # Create a container node for the fire effects - position at center of safe
        fireContainer = safe.attachNewNode('fireElementalEffect')
        fireContainer.setPos(0, 0, 5)  # Just above ground level
        fireContainer.setScale(0.01, 0.01, 0.01)  # Start very small instead of 0 to avoid transform issues
        
        # Create one large central fire effect that extends well beyond the safe
        baseFlameEffect = BattleParticles.createParticleEffect(file='firedBaseFlame')
        BattleParticles.setEffectTexture(baseFlameEffect, 'fire')
        baseFlameEffect.reparentTo(fireContainer)
        baseFlameEffect.setPos(0, 0, 0)
        baseFlameEffect.setScale(12.0, 12.0, 15.0)  # Very large central fire effect
        
        # Store reference to the effect for cleanup using PythonTag
        fireContainer.setPythonTag('baseFlameEffect', baseFlameEffect)
        
        # Start the fire effect first
        baseFlameEffect.start(fireContainer, fireContainer)
        
        # Make individual particles bigger and smooth the animation
        # Use the same method as BattleParticles.setEffectTexture()
        try:
            particles = baseFlameEffect.getParticlesNamed('particles-1')
            if particles:
                renderer = particles.getRenderer()
                
                # Particles grow from very small to final size for smooth appearance
                renderer.setInitialXScale(0.01)   # Start very small instead of 0
                renderer.setInitialYScale(0.01)   # Start very small instead of 0
                renderer.setFinalXScale(0.25)     # Grow to desired size
                renderer.setFinalYScale(0.75)     # Grow to desired size
                
                # Enable smooth scaling interpolation
                renderer.setXScaleFlag(1)  # Enable X scale interpolation
                renderer.setYScaleFlag(1)  # Enable Y scale interpolation
                
                # Smooth the animation by adjusting particle properties
                # Increase birth rate for smoother spawning
                particles.setBirthRate(0.01)  # More frequent spawning (was 0.02)
                
                # Increase lifespan for smoother transitions
                particles.factory.setLifespanBase(0.4)     # Longer life for growing animation
                particles.factory.setLifespanSpread(0.1)   # Add some randomness
                
                # Adjust litter size for more consistent spawning
                particles.setLitterSize(6)     # Fewer per spawn but more frequent
                particles.setLitterSpread(2)   # Add some variation
                
                # Improve alpha blending for smoother transitions
                renderer.setAlphaMode(BaseParticleRenderer.PRALPHAOUT)  # Smooth fade out
                renderer.setAlphaBlendMethod(BaseParticleRenderer.PPBLENDLINEAR)  # Linear blending
                
                self.notify.info("Successfully modified fire particle sizes and smoothed animation")
        except Exception as e:
            self.notify.warning(f"Could not modify particle properties: {e}")
        
        # Create smooth appearance animation with safety checks
        try:
            # Safe gets a fiery orange glow
            safeGlowInterval = LerpColorScaleInterval(
                safe, 1.0,  # 1 second duration
                colorScale=(1.3, 0.7, 0.4, 1.0),  # Fiery orange tint
                startColorScale=(1.0, 1.0, 1.0, 1.0)  # Start from normal
            )
            
            # Fire particles scale up smoothly from very small to normal
            particleScaleInterval = LerpScaleInterval(
                fireContainer, 1.0,  # 1 second duration
                scale=(1.0, 1.0, 1.0),  # Scale to normal size
                startScale=(0.01, 0.01, 0.01)  # Start very small
            )
            
            # Play both animations in parallel for smooth appearance
            appearanceInterval = Parallel(safeGlowInterval, particleScaleInterval)
            appearanceInterval.start()
            
            # Store the appearance interval for potential cleanup
            fireContainer.setPythonTag('appearanceInterval', appearanceInterval)
            
        except Exception as e:
            self.notify.warning(f"Could not create appearance animation: {e}")
            # Fallback: set to normal scale immediately
            fireContainer.setScale(1.0, 1.0, 1.0)
            safe.setColorScale(1.3, 0.7, 0.4, 1.0)
        
        return fireContainer

    def __createVoltParticleEffect(self, safe, props):
        """Create electric/lightning particle effects for VOLT elemental safes"""
        
        # Load the battle particles system
        BattleParticles.loadParticles()
        
        # Create a container node for the electric effects - position at center of safe
        voltContainer = safe.attachNewNode('voltElementalEffect')
        voltContainer.setPos(0, 0, 5)  # Just above ground level
        voltContainer.setScale(0.01, 0.01, 0.01)  # Start very small instead of 0 to avoid transform issues
        
        # Create the main electric spark effect using existing spark particles
        sparkEffect = BattleParticles.createParticleEffect(file='tnt')  # Use the TNT spark effect as base
        BattleParticles.setEffectTexture(sparkEffect, 'spark')  # Use spark texture
        sparkEffect.reparentTo(voltContainer)
        sparkEffect.setPos(0, 0, 0)
        sparkEffect.setScale(24.0, 24.0, 28.0)  # Large electric effect around the safe
        
        # Store reference to the effect for cleanup using PythonTag
        voltContainer.setPythonTag('sparkEffect', sparkEffect)
        
        # Start the electric effect first
        sparkEffect.start(voltContainer, voltContainer)
        
        # Customize the spark particles for electric effect
        try:
            particles = sparkEffect.getParticlesNamed('particles-1')
            if particles:
                renderer = particles.getRenderer()
                
                # Electric sparks should be quick and jagged
                renderer.setInitialXScale(0.1)   # Start medium size
                renderer.setInitialYScale(0.1)   
                renderer.setFinalXScale(0.5)     # Grow slightly  
                renderer.setFinalYScale(0.8)    # But become very thin (lightning-like)
                
                # Enable smooth scaling interpolation
                renderer.setXScaleFlag(1)  # Enable X scale interpolation
                renderer.setYScaleFlag(1)  # Enable Y scale interpolation
                
                # Set electric yellow color
                renderer.setColor(Vec4(1.0, 0.85, 0.6, 1.0))  # Darker electric yellow-white
                
                # Quick, crackling electric animation
                particles.setBirthRate(0.005)  # Very frequent spawning for electric crackle
                
                # Short, sharp electric bursts
                particles.factory.setLifespanBase(0.2)     # Very short life for quick zaps
                particles.factory.setLifespanSpread(0.1)   # Some randomness
                
                # More litter for electric crackling effect
                particles.setLitterSize(3)     # More sparks per spawn
                particles.setLitterSpread(1)   # Some variation
                
                # Electric alpha blending for bright sparks
                renderer.setAlphaMode(BaseParticleRenderer.PRALPHAOUT)  # Fade out
                renderer.setAlphaBlendMethod(BaseParticleRenderer.PPBLENDLINEAR)  # Linear blending
                
                self.notify.info("Successfully modified electric particle properties")
        except Exception as e:
            self.notify.warning(f"Could not modify electric particle properties: {e}")
        
        # Create smooth appearance animation with electric blue-white glow
        try:
            # Safe gets an electric yellow-white glow
            safeGlowInterval = LerpColorScaleInterval(
                safe, 0.8,  # 0.8 second duration for quick electric response
                colorScale=(1.15, 1.15, 0.5, 1.0),  # Darker electric yellow-white tint
                startColorScale=(1.0, 1.0, 1.0, 1.0)  # Start from normal
            )
            
            # Electric particles scale up quickly
            particleScaleInterval = LerpScaleInterval(
                voltContainer, 0.8,  # 0.8 second duration for quick response
                scale=(1.0, 1.0, 1.0),  # Scale to normal size
                startScale=(0.01, 0.01, 0.01)  # Start very small
            )
            
            # Play both animations in parallel for electric appearance
            appearanceInterval = Parallel(safeGlowInterval, particleScaleInterval)
            appearanceInterval.start()
            
            # Store the appearance interval for potential cleanup
            voltContainer.setPythonTag('appearanceInterval', appearanceInterval)
            
        except Exception as e:
            self.notify.warning(f"Could not create electric appearance animation: {e}")
            # Fallback: set to normal scale immediately
            voltContainer.setScale(1.0, 1.0, 1.0)
            safe.setColorScale(1.2, 1.2, 0.6, 1.0)
        
        return voltContainer

    def __createTextIndicator(self, safe, props):
        """Create text indicator for non-Fire elemental safes"""
        # Create elemental text indicator using TextNode for proper 3D positioning
        textNode = TextNode(f'{props["text"].lower()}ElementalText')
        textNode.setText(props['text'])
        textNode.setTextColor(*props['color'])
        textNode.setAlign(TextNode.ACenter)
        textNode.setShadow(0.05, 0.05)
        textNode.setShadowColor(0, 0, 0, 1)  # Black shadow
        
        # Create NodePath and set properties
        elementalText = safe.attachNewNode(textNode)
        elementalText.setScale(props['scale'])
        elementalText.setPos(0, 0, props['height'])  # Position above the safe
        elementalText.setBillboardPointEye()  # Always face the camera
        
        return elementalText

    def __removeElementalIndicator(self, safeDoId):
        """Remove any elemental indicator from a safe"""
        if safeDoId in self.fireElementalIndicators:
            indicator = self.fireElementalIndicators[safeDoId]
            
            # Check if this is a particle effect container by checking for PythonTags
            baseFlameEffect = indicator.getPythonTag('baseFlameEffect')
            sparkEffect = indicator.getPythonTag('sparkEffect')
            
            if baseFlameEffect is not None or sparkEffect is not None:
                # Find the safe object
                safe = None
                if self.boss and hasattr(self.boss, 'safes'):
                    for safeIndex, safeObj in self.boss.safes.items():
                        if safeObj.doId == safeDoId:
                            safe = safeObj
                            break
                
                # Fallback: search through distributed objects by doId
                if not safe:
                    safe = base.cr.doId2do.get(safeDoId)
                
                if safe:
                    # Create smooth disappearance animation
                    if baseFlameEffect is not None:
                        # Fire effect cleanup
                        safeGlowFadeInterval = LerpColorScaleInterval(
                            safe, 0.8,  # 0.8 second duration
                            colorScale=(1.0, 1.0, 1.0, 1.0),  # Back to normal
                            startColorScale=(1.3, 0.7, 0.4, 1.0)  # From fiery orange
                        )
                    elif sparkEffect is not None:
                        # VOLT effect cleanup
                        safeGlowFadeInterval = LerpColorScaleInterval(
                            safe, 0.6,  # 0.6 second duration for quick electric fade
                            colorScale=(1.0, 1.0, 1.0, 1.0),  # Back to normal
                            startColorScale=(1.2, 1.2, 0.6, 1.0)  # From electric yellow-white
                        )
                    
                    # Particles scale down to very small instead of 0
                    particleScaleDownInterval = LerpScaleInterval(
                        indicator, 0.6 if sparkEffect else 0.8,  # Faster fade for electric
                        scale=(0.01, 0.01, 0.01),  # Scale down to very small
                        startScale=(1.0, 1.0, 1.0)  # From normal size
                    )
                    
                    # Clean up after animation completes
                    def cleanupParticleEffect():
                        try:
                            if baseFlameEffect:
                                baseFlameEffect.cleanup()
                            if sparkEffect:
                                sparkEffect.cleanup()
                        except:
                            pass  # Ignore cleanup errors
                        
                        # Remove the node
                        if not indicator.isEmpty():
                            indicator.removeNode()
                    
                    # Play both animations in parallel, then cleanup
                    disappearanceInterval = Sequence(
                        Parallel(safeGlowFadeInterval, particleScaleDownInterval),
                        Func(cleanupParticleEffect)
                    )
                    disappearanceInterval.start()
                else:
                    # Fallback: immediate cleanup if safe not found
                    try:
                        if baseFlameEffect:
                            baseFlameEffect.cleanup()
                        if sparkEffect:
                            sparkEffect.cleanup()
                    except:
                        pass
                    if not indicator.isEmpty():
                        indicator.removeNode()
            else:
                # This is a text indicator - remove immediately
                if not indicator.isEmpty():
                    indicator.removeNode()
            
            # Remove from dictionary
            del self.fireElementalIndicators[safeDoId]
            self.notify.info(f"Removed elemental indicator for safe {safeDoId}")

    def __nextRound(self, task=None):
        """Transition to the next round"""
        # The server will handle the transition to the next round automatically
        # We just need to clean up the victory state
        return Task.done

    def setCFOElementalStatus(self, elementType, enabled):
        """Handle CFO elemental status updates from server"""
        if enabled:
            self.__createCFOElementalEffect(elementType)
        else:
            self.__removeCFOElementalEffect(elementType)

    def __createCFOElementalEffect(self, elementType):
        """Create elemental effects on the CFO"""
        if elementType == ElementType.FIRE:
            self.__createCFOFireEffect()
        elif elementType == ElementType.VOLT:
            self.__createCFOVoltEffect()
        # Future element types can be handled here:
        # elif elementType == ElementType.ICE:
        #     self.__createCFOIceEffect()

    def __createCFOFireEffect(self):
        """Create fire effects on the CFO when he's taking Fire DoT"""
        if not self.boss:
            self.notify.warning("Cannot create CFO fire effect - no boss found")
            return
            
        # Remove existing fire effect if present
        self.__removeCFOElementalEffect(ElementType.FIRE)
        
        # Load the battle particles system
        BattleParticles.loadParticles()
        
        # Create a container node for the fire effects on the CFO
        fireContainer = self.boss.attachNewNode('cfoFireElementalEffect')
        fireContainer.setPos(0, 0, 8)  # Position above CFO's center
        fireContainer.setScale(0.01, 0.01, 0.01)  # Start very small for smooth appearance
        
        # Create large fire effect that engulfs the CFO
        fireEffect = BattleParticles.createParticleEffect(file='firedBaseFlame')
        BattleParticles.setEffectTexture(fireEffect, 'fire')
        fireEffect.reparentTo(fireContainer)
        fireEffect.setPos(0, 0, 0)
        fireEffect.setScale(25.0, 25.0, 30.0)  # Very large to engulf the CFO
        
        # Store reference to the effect for cleanup
        fireContainer.setPythonTag('fireEffect', fireEffect)
        
        # Start the fire effect
        fireEffect.start(fireContainer, fireContainer)
        
        # Make individual particles bigger for dramatic effect
        try:
            particles = fireEffect.getParticlesNamed('particles-1')
            if particles:
                renderer = particles.getRenderer()
                
                # Large particles that grow over time
                renderer.setInitialXScale(0.1)   # Start larger than safe fire
                renderer.setInitialYScale(0.1)   
                renderer.setFinalXScale(0.5)     # Grow to very large size
                renderer.setFinalYScale(1.0)     # Extra tall flames
                
                # Enable smooth scaling interpolation
                renderer.setXScaleFlag(1)
                renderer.setYScaleFlag(1)
                
                # Dramatic fire animation settings
                particles.setBirthRate(0.005)     # More frequent spawning for intensity
                particles.factory.setLifespanBase(0.6)    # Longer life for sustained effect
                particles.factory.setLifespanSpread(0.2)  
                particles.setLitterSize(8)        # More particles per spawn
                particles.setLitterSpread(3)      
                
                # Improved blending for dramatic effect
                renderer.setAlphaMode(BaseParticleRenderer.PRALPHAOUT)
                renderer.setAlphaBlendMethod(BaseParticleRenderer.PPBLENDLINEAR)
                
                self.notify.info("CFO fire effect particles configured successfully")
        except Exception as e:
            self.notify.warning(f"Could not modify CFO fire particle properties: {e}")
        
        # Create smooth appearance animation
        try:
            # Add fire color effect using the additive system
            fireColorContribution = (1.4, 0.6, 0.3, 1.0)  # Fiery orange tint
            self.addCFOColorEffect('fire', fireColorContribution, duration=0.6)
            
            # Fire particles scale up smoothly
            particleScaleInterval = LerpScaleInterval(
                fireContainer, 0.6,  # 0.6 second duration for snappy response
                scale=(1.0, 1.0, 1.0),  # Scale to normal size
                startScale=(0.01, 0.01, 0.01)
            )
            
            # Start particle animation
            particleScaleInterval.start()
            
            # Store the appearance interval for cleanup
            fireContainer.setPythonTag('appearanceInterval', particleScaleInterval)
            
        except Exception as e:
            self.notify.warning(f"Could not create CFO fire appearance animation: {e}")
            # Fallback: set effects immediately
            fireContainer.setScale(1.0, 1.0, 1.0)
            fireColorContribution = (1.4, 0.6, 0.3, 1.0)
            self.addCFOColorEffect('fire', fireColorContribution, duration=0.0)
        
        # Store the fire effect
        self.cfoElementalEffects[ElementType.FIRE] = fireContainer
        self.notify.info("Created fire effect on CFO")

    def __createCFOVoltEffect(self):
        """Create electric effects on the CFO when he's taking VOLT DoT"""
        if not self.boss:
            self.notify.warning("Cannot create CFO volt effect - no boss found")
            return
            
        # Remove existing volt effect if present
        self.__removeCFOElementalEffect(ElementType.VOLT)
        
        # Load the battle particles system
        BattleParticles.loadParticles()
        
        # Create a container node for the electric effects on the CFO
        voltContainer = self.boss.attachNewNode('cfoVoltElementalEffect')
        voltContainer.setPos(0, 0, 8)  # Position above CFO's center
        voltContainer.setScale(0.01, 0.01, 0.01)  # Start very small for smooth appearance
        
        # Create multiple electric spark effects for dramatic CFO electrocution
        sparkEffect = BattleParticles.createParticleEffect(file='tnt')
        BattleParticles.setEffectTexture(sparkEffect, 'spark')
        sparkEffect.reparentTo(voltContainer)
        sparkEffect.setPos(0, 0, 0)  # Center
        sparkEffect.setScale(45.0, 45.0, 50.0)  # Very large to engulf the CFO
        
        # Store references to all effects for cleanup
        voltContainer.setPythonTag('sparkEffect1', sparkEffect)
        
        # Start all electric effects
        sparkEffect.start(voltContainer, voltContainer)
        
        # Customize all spark effects for intense electric CFO effect
        for i, effect in enumerate([sparkEffect], 1):
            try:
                particles = effect.getParticlesNamed('particles-1')
                if particles:
                    renderer = particles.getRenderer()
                    
                    # Intense electric sparks for CFO electrocution
                    renderer.setInitialXScale(0.2)   # Start larger for dramatic effect
                    renderer.setInitialYScale(0.2)   
                    renderer.setFinalXScale(0.8)     # Grow to very large electric bolts
                    renderer.setFinalYScale(1.4)     # Very thin like lightning
                    
                    # Enable smooth scaling interpolation
                    renderer.setXScaleFlag(1)
                    renderer.setYScaleFlag(1)
                    
                    # Bright electric yellow-white color
                    renderer.setColor(Vec4(1.0, 0.85, 0.6, 1.0))  # Darker electric yellow-white
                    
                    # Intense electric crackling animation
                    particles.setBirthRate(0.002)     # Very frequent for intense effect
                    
                    # Quick electric bursts for CFO effect
                    particles.factory.setLifespanBase(0.3)     # Slightly longer for visibility
                    particles.factory.setLifespanSpread(0.15)   
                    
                    # More intense electric crackling
                    particles.setLitterSize(5 + i)     # Increasing intensity per effect
                    particles.setLitterSpread(2)       
                    
                    # Bright electric blending
                    renderer.setAlphaMode(BaseParticleRenderer.PRALPHAOUT)
                    renderer.setAlphaBlendMethod(BaseParticleRenderer.PPBLENDLINEAR)
                    
                    self.notify.info(f"CFO electric effect {i} particles configured successfully")
            except Exception as e:
                self.notify.warning(f"Could not modify CFO electric effect {i} particle properties: {e}")
        
        # Create smooth appearance animation with intense electric effect
        try:
            # Add electric color effect using the additive system
            voltColorContribution = (1.2, 1.2, 0.6, 1.0)  # Darker electric yellow-white tint
            self.addCFOColorEffect('volt', voltColorContribution, duration=0.5)
            
            # Electric particles scale up dramatically and quickly
            particleScaleInterval = LerpScaleInterval(
                voltContainer, 0.5,  # 0.5 second duration for quick electric response
                scale=(1.0, 1.0, 1.0),  # Scale to normal size
                startScale=(0.01, 0.01, 0.01)
            )
            
            # Start particle animation
            particleScaleInterval.start()
            
            # Store the appearance interval for cleanup
            voltContainer.setPythonTag('appearanceInterval', particleScaleInterval)
            
        except Exception as e:
            self.notify.warning(f"Could not create CFO electric appearance animation: {e}")
            # Fallback: set effects immediately
            voltContainer.setScale(1.0, 1.0, 1.0)
            voltColorContribution = (1.2, 1.2, 0.6, 1.0)
            self.addCFOColorEffect('volt', voltColorContribution, duration=0.0)
        
        # Store the volt effect
        self.cfoElementalEffects[ElementType.VOLT] = voltContainer
        self.notify.info("Created electric effect on CFO")

    def __removeCFOElementalEffect(self, elementType):
        """Remove elemental effects from the CFO"""
        if elementType not in self.cfoElementalEffects:
            return
            
        effect = self.cfoElementalEffects[elementType]
        
        if elementType == ElementType.FIRE:
            # Create smooth disappearance animation for fire effect
            try:
                # Remove fire color effect using the additive system
                self.removeCFOColorEffect('fire', duration=1.0)
                
                # Fire particles scale down
                particleScaleDownInterval = LerpScaleInterval(
                    effect, 1.0,  # 1 second duration
                    scale=(0.01, 0.01, 0.01),  # Scale down to very small
                    startScale=(1.0, 1.0, 1.0)
                )
                
                # Clean up after animation
                def cleanupCFOFireEffect():
                    try:
                        fireEffect = effect.getPythonTag('fireEffect')
                        if fireEffect:
                            fireEffect.cleanup()
                    except:
                        pass
                    
                    if not effect.isEmpty():
                        effect.removeNode()
                
                # Play disappearance animation then cleanup
                disappearanceInterval = Sequence(
                    particleScaleDownInterval,
                    Func(cleanupCFOFireEffect)
                )
                disappearanceInterval.start()
            except Exception as e:
                self.notify.warning(f"Error during CFO fire effect removal: {e}")
                # Fallback: immediate cleanup
                self.removeCFOColorEffect('fire', duration=0.0)
                if not effect.isEmpty():
                    effect.removeNode()
        elif elementType == ElementType.VOLT:
            # Create smooth disappearance animation for electric effect
            try:
                # Remove volt color effect using the additive system
                self.removeCFOColorEffect('volt', duration=0.7)
                
                # Electric particles scale down quickly
                particleScaleDownInterval = LerpScaleInterval(
                    effect, 0.7,  # 0.7 second duration for quick electric fade
                    scale=(0.01, 0.01, 0.01),  # Scale down to very small
                    startScale=(1.0, 1.0, 1.0)
                )
                
                # Clean up after animation
                def cleanupCFOVoltEffect():
                    try:
                        # Cleanup spark effect
                        sparkEffect = effect.getPythonTag('sparkEffect1')
                        if sparkEffect:
                            sparkEffect.cleanup()
                    except:
                        pass
                    
                    if not effect.isEmpty():
                        effect.removeNode()
                
                # Play disappearance animation then cleanup
                disappearanceInterval = Sequence(
                    particleScaleDownInterval,
                    Func(cleanupCFOVoltEffect)
                )
                disappearanceInterval.start()
            except Exception as e:
                self.notify.warning(f"Error during CFO electric effect removal: {e}")
                # Fallback: immediate cleanup
                self.removeCFOColorEffect('volt', duration=0.0)
                if not effect.isEmpty():
                    effect.removeNode()
        else:
            # For other element types, just remove immediately
            if not effect.isEmpty():
                effect.removeNode()
        
        # Remove from dictionary
        del self.cfoElementalEffects[elementType]
        
        elementName = {ElementType.FIRE: 'Fire', ElementType.VOLT: 'Volt'}.get(elementType, f'Element{elementType}')
        self.notify.info(f"Removed {elementName} effect from CFO")

    def disable(self):
        # Clean up any elemental indicators
        for safeDoId in list(self.fireElementalIndicators.keys()):
            self.__removeElementalIndicator(safeDoId)
        self.fireElementalIndicators.clear()
        
        # Clean up CFO elemental effects
        for elementType in list(self.cfoElementalEffects.keys()):
            self.__removeCFOElementalEffect(elementType)
        self.cfoElementalEffects.clear()
        
        # Clean up all CFO color effects
        self.clearAllCFOColorEffects()
        
        if self.boss:
            # Reset CFO color scale to normal
            try:
                self.boss.setColorScale(1.0, 1.0, 1.0, 1.0)
            except:
                pass
        
        DistributedMinigame.disable(self)

    def addCFOColorEffect(self, effectName, colorContribution, duration=0.5):
        """Add a color effect to the CFO using additive blending"""
        if not self.boss:
            return
            
        # Store the color contribution for this effect
        self.cfoColorEffects[effectName] = colorContribution
        
        # Calculate the new target color by combining all active effects
        targetColor = self.__calculateCombinedCFOColor()
        
        # Smoothly transition to the new color
        self.__lerpCFOColorTo(targetColor, duration)
        
        activeEffects = list(self.cfoColorEffects.keys())
        self.notify.info(f"Added CFO color effect '{effectName}': {colorContribution}")
        self.notify.info(f"Active effects: {activeEffects} -> Combined target: {targetColor}")

    def removeCFOColorEffect(self, effectName, duration=0.5):
        """Remove a color effect from the CFO using additive blending"""
        if effectName not in self.cfoColorEffects:
            self.notify.info(f"CFO color effect '{effectName}' not found to remove")
            return
            
        if not self.boss:
            return
            
        # Remove the color contribution
        del self.cfoColorEffects[effectName]
        
        # Calculate the new target color without this effect
        targetColor = self.__calculateCombinedCFOColor()
        
        # Smoothly transition to the new color
        self.__lerpCFOColorTo(targetColor, duration)
        
        activeEffects = list(self.cfoColorEffects.keys())
        self.notify.info(f"Removed CFO color effect '{effectName}'")
        self.notify.info(f"Remaining effects: {activeEffects} -> Combined target: {targetColor}")

    def __calculateCombinedCFOColor(self):
        """Calculate the combined color from all active effects"""
        if not self.cfoColorEffects:
            return self.cfoBaseColor
            
        # Start with base color
        r, g, b, a = self.cfoBaseColor
        
        # Add contributions from all active effects
        for effectName, (dr, dg, db, da) in self.cfoColorEffects.items():
            r += dr - 1.0  # Convert from color scale to additive offset
            g += dg - 1.0
            b += db - 1.0
            a += da - 1.0
            
        # Clamp values to reasonable ranges
        r = max(0.1, min(3.0, r))  # Prevent too dark or too bright
        g = max(0.1, min(3.0, g))
        b = max(0.1, min(3.0, b))
        a = max(0.1, min(2.0, a))
        
        combinedColor = (r, g, b, a)
        self.notify.debug(f"Combined CFO color calculation: Base {self.cfoBaseColor} + Effects {self.cfoColorEffects} = {combinedColor}")
        
        return combinedColor

    def __lerpCFOColorTo(self, targetColor, duration):
        """Smoothly lerp the CFO color to a target color"""
        if not self.boss:
            return
            
        # Stop any existing color lerp
        if self.cfoColorLerpTask:
            self.cfoColorLerpTask.pause()
            self.cfoColorLerpTask = None
            
        # Get current color
        currentColor = self.boss.getColorScale()
        
        # Create smooth color transition
        self.cfoColorLerpTask = LerpColorScaleInterval(
            self.boss, duration,
            colorScale=targetColor,
            startColorScale=currentColor,
            blendType='easeInOut'
        )
        
        # Start the transition
        self.cfoColorLerpTask.start()
        
        self.notify.info(f"Lerping CFO color from {currentColor} to {targetColor} over {duration}s")

    def clearAllCFOColorEffects(self):
        """Clear all color effects and return to base color"""
        if not self.boss:
            return
            
        self.cfoColorEffects.clear()
        
        # Return to base color
        self.__lerpCFOColorTo(self.cfoBaseColor, 1.0)
