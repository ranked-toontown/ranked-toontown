import functools
import random
import math

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
from toontown.minigame.statuseffects.DistributedStatusEffectSystem import DistributedStatusEffectSystem
from toontown.minigame.statuseffects.StatusEffectGlobals import StatusEffect, SAFE_ALLOWED_EFFECTS
from direct.gui.DirectGui import DGG, DirectFrame
from direct.gui.DirectScrolledList import DirectScrolledList
from direct.gui.DirectLabel import DirectLabel
from direct.gui.DirectButton import DirectButton
from direct.showbase.ShowBaseGlobal import aspect2d
from direct.task import Task


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
        self.currentRound = 1
        self.roundWins = {}  # Maps avId -> number of rounds won
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
        
        # Status effect system will be set via setStatusEffectSystemId
        self.statusEffectSystem : DistributedStatusEffectSystem | None = None

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

        self.asmr = False

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
        from direct.gui.DirectButton import DirectButton
        from toontown.toonbase import TTLocalizer
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

    def exitPlay(self):

        if self.boss is not None:
            self.boss.cleanupBossBattle()

        self.scoreboard.disableSpectating()
        self.scoreboard.finish()

        self.walkStateData.exit()

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

    def exitVictory(self):
        taskMgr.remove(self.uniqueName("craneGameVictory"))
        taskMgr.remove(self.uniqueName("craneGameNextRound"))
        camera.reparentTo(base.localAvatar)

    def enterCleanup(self):
        self.notify.debug("enterCleanup")
        self.__cleanupRulesPanel()
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
        
        # Cleanup status effect system
        if hasattr(self, 'statusEffectSystem') and self.statusEffectSystem:
            self.statusEffectSystem.cleanup()

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

    def getStatusEffectSystem(self) -> DistributedStatusEffectSystem | None:
        return self.statusEffectSystem
    
    def setStatusEffectSystemId(self, statusEffectSystemId: int) -> None:
        self.statusEffectSystem = base.cr.getDo(statusEffectSystemId)

    def addScore(self, avId: int, score: int, reason: str):

        # Convert the reason into a valid reason enum that our scoreboard accepts.
        convertedReason = CraneLeagueGlobals.ScoreReason.from_astron(reason)
        if convertedReason is None:
            convertedReason = CraneLeagueGlobals.ScoreReason.DEFAULT
        self.scoreboard.addScore(avId, score, convertedReason)

    def updateCombo(self, avId, comboLength):
        self.scoreboard.setCombo(avId, comboLength)

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

    def __nextRound(self, task=None):
        """Transition to the next round"""
        # The server will handle the transition to the next round automatically
        # We just need to clean up the victory state
        return Task.done

    def setAsmr(self, asmr: bool):
        self.asmr = asmr