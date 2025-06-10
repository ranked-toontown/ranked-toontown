import math
import random
from operator import itemgetter

from direct.fsm import ClassicFSM
from direct.fsm import State
from direct.showbase.PythonUtil import clamp
from direct.task.TaskManagerGlobal import taskMgr
from panda3d.core import CollisionInvSphere, CollisionNode, CollisionSphere, CollisionTube, CollisionPolygon, CollisionBox, NodePath, Vec3, Point3
from toontown.coghq import CraneLeagueGlobals
from toontown.coghq.CashbotBossComboTracker import CashbotBossComboTracker
from toontown.coghq.CraneLeagueGlobals import ScoreReason
from toontown.coghq.DistributedCashbotBossCraneAI import DistributedCashbotBossCraneAI
from toontown.coghq.DistributedCashbotBossHeavyCraneAI import DistributedCashbotBossHeavyCraneAI
from toontown.coghq.DistributedCashbotBossSafeAI import DistributedCashbotBossSafeAI
from toontown.coghq.DistributedCashbotBossSideCraneAI import DistributedCashbotBossSideCraneAI
from toontown.coghq.DistributedCashbotBossTreasureAI import DistributedCashbotBossTreasureAI
from toontown.matchmaking.skill_profile_keys import SkillProfileKey
from toontown.minigame.DistributedMinigameAI import DistributedMinigameAI
from toontown.minigame.craning import CraneGameGlobals
from toontown.minigame.craning.CraneGamePracticeCheatAI import CraneGamePracticeCheatAI
from toontown.suit.DistributedCashbotBossGoonAI import DistributedCashbotBossGoonAI
from toontown.suit.DistributedCashbotBossStrippedAI import DistributedCashbotBossStrippedAI
from toontown.toon.DistributedToonAI import DistributedToonAI
from toontown.toonbase import ToontownGlobals
from toontown.minigame.statuseffects.DistributedStatusEffectSystemAI import DistributedStatusEffectSystemAI
from toontown.minigame.statuseffects.StatusEffectGlobals import StatusEffect, SAFE_ALLOWED_EFFECTS

class DistributedCraneGameAI(DistributedMinigameAI):
    DESPERATION_MODE_ACTIVATE_THRESHOLD = 1800

    # If time limit is enabled, how many seconds should be remaining to activate when an overtake happens?
    OVERTIME_OVERTAKE_ACTIVATION_THRESHOLD = 15

    def __init__(self, air, minigameId):
        DistributedMinigameAI.__init__(self, air, minigameId)
        self.setProfileSkillKey(None)  # By default, no ranked mode.

        self.ruleset = CraneLeagueGlobals.CraneGameRuleset()
        self.modifiers = []  # A list of CFORulesetModifierBase instances
        self.goonCache = ("Recent emerging side", 0) # Cache for goon spawn bad luck protection
        self.cranes = []
        self.safes = []
        self.goons = []
        self.treasures = {}
        self.grabbingTreasures = {}
        self.recycledTreasures = []
        self.boss = None

        # We need a scene to do the collision detection in.
        self.scene = NodePath('scene')

        self.toonsWon = False

        self.rollModsOnStart = False
        self.numModsWanted = 5
        self.desiredModifiers = []  # Modifiers added manually via commands or by the host during game settings. Will always ensure these are added every crane round.

        self.customSpawnPositions = {}
        self.customSpawnOrderSet = False  # Track if spawn order has been manually set by leader
        self.bestOfValue = 1  # Default to Best of 1
        self.currentRound = 1
        self.roundWins = {}  # Maps avId -> number of rounds won
        self.originalSpawnOrder = []  # Store original spawn order for rotation
        self.goonMinScale = 0.8
        self.goonMaxScale = 2.4

        self.comboTrackers = {}  # Maps avId -> CashbotBossComboTracker instance

        self.gameFSM = ClassicFSM.ClassicFSM('DistributedMinigameTemplateAI',
                               [
                                State.State('inactive',
                                            self.enterInactive,
                                            self.exitInactive,
                                            ['prepare']),
                                State.State('prepare',
                                            self.enterPrepare,
                                            self.exitPrepare,
                                            ['play']),
                                State.State('play',
                                            self.enterPlay,
                                            self.exitPlay,
                                            ['victory', 'cleanup']),
                                State.State('victory',
                                            self.enterVictory,
                                            self.exitVictory,
                                            ['cleanup']),
                                State.State('cleanup',
                                            self.enterCleanup,
                                            self.exitCleanup,
                                            ['inactive']),
                                ],
                               # Initial State
                               'inactive',
                               # Final State
                               'inactive',
                               )

        # Add our game ClassicFSM to the framework ClassicFSM
        self.addChildGameFSM(self.gameFSM)

        # State tracking related to the overtime mechanic.
        self.overtimeWillHappen = False  # Setting this to True will cause the CFO to enter "overtime" mode when time runs out.
        self.currentlyInOvertime = False  # Only true when the game is currently in overtime.
        self.currentWinners: list[int] = []  # Keeps track of who's in the lead so we know when to trigger overtime.

        # Instances of "cheats" that can be interacted with to make the crane round behave a certain way.
        self.practiceCheatHandler: CraneGamePracticeCheatAI = CraneGamePracticeCheatAI(self)

        self.statusEffectSystem = DistributedStatusEffectSystemAI(self, air,
            StatusEffect.BURNED, 
            StatusEffect.DRENCHED, 
            StatusEffect.WINDED, 
            StatusEffect.GROUNDED, 
            StatusEffect.EXPLODE, 
            StatusEffect.FROZEN, 
            StatusEffect.SHATTERED
        )

        # Memory leak prevention - track event listeners and task names
        self._deathListenerEvents = []
        self._allTaskNames = set()

        self.asmr = False

    def isRanked(self) -> bool:
        # Todo: setting for this. We don't want EVERY game to be ranked.
        return len(self.getParticipantsNotSpectating()) > 1

    def generate(self):
        self.notify.debug("generate")
        self.__makeBoss()
        DistributedMinigameAI.generate(self)

    def announceGenerate(self):
        self.notify.debug("announceGenerate")
        self.__updateSkillProfile()

    def __makeBoss(self):
        self.__deleteBoss()

        self.boss = DistributedCashbotBossStrippedAI(self.air, self)
        self.boss.generateWithRequired(self.zoneId)
        self.statusEffectSystem.generateWithRequired(self.zoneId)
        self.d_setBossCogId()
        self.d_setStatusEffectSystemId()
        self.boss.reparentTo(self.scene)

        # And some solids to keep the goons constrained to our room.
        cn = CollisionNode('walls')
        #cs = CollisionSphere(0, 0, 0, 13)
        #cn.addSolid(cs)

        collisionSolids = [CollisionTube(6.5, -7.5, 0, 6.5, 7.5, 0, 2.5), #tube1
                           CollisionTube(-6.5, -7.5, 0, -6.5, 7.5, 0, 2.5), #tube2
                           CollisionSphere(0, 0, 0, 8.35) #box (as sphere)
        ]

        for collisionSolid in collisionSolids:
            cn.addSolid(collisionSolid)

        cs = CollisionInvSphere(0, 0, 0, 42)
        cn.addSolid(cs)
        self.boss.attachNewNode(cn)

    def __deleteBoss(self):
        if self.__bossExists():
            self.boss.cleanupBossBattle()
            self.boss.requestDelete()
        self.boss = None

    def __bossExists(self) -> bool:
        return self.boss is not None

    # Disable is never called on the AI so we do not define one
    def cleanup(self):
        """Clean up all resources to prevent memory leaks"""
        # Clean up event listeners
        self.ignoreToonDeaths()
        
        # Clean up all tracked tasks
        for taskName in self._allTaskNames:
            taskMgr.remove(taskName)
        self._allTaskNames.clear()
        
        # Clean up specific known tasks
        taskMgr.remove(self.uniqueName('times-up-task'))
        taskMgr.remove(self.uniqueName('post-times-up-task'))
        taskMgr.remove(self.uniqueName('NextGoon'))
        taskMgr.remove(self.uniqueName('safe-effects'))
        taskMgr.remove(self.uniqueName('laff-drain-task'))
        taskMgr.remove(self.uniqueName('craneGameVictory'))
        taskMgr.remove(self.uniqueName('craneGameNextRound'))
        taskMgr.remove(self.uniqueName('startNextRound'))
        
        # Clean up combo trackers
        self.cleanupComboTrackers()
        
        # Clean up objects
        self.__deleteCraningObjects()
        self.__deleteBoss()
        
        # Clean up scene
        if self.scene is not None:
            self.scene.removeNode()
            self.scene = None
        
        # Break circular references
        if hasattr(self, 'practiceCheatHandler'):
            self.practiceCheatHandler = None

    def delete(self):
        self.notify.debug("delete")
        # Clean up all resources
        self.cleanup()
        del self.gameFSM
        DistributedMinigameAI.delete(self)

    # override some network message handlers
    def setGameReady(self):
        self.notify.debug("setGameReady")
        DistributedMinigameAI.setGameReady(self)
        # all of the players have checked in
        # they will now be shown the rules
        self.d_setBossCogId()
        self.setupRuleset()
        self.setupSpawnpoints()
        # Reset custom spawn order flag for new games (not restarts)
        self.resetCustomSpawnOrder()
        # Reset round information for new games
        self.roundWins = {}
        self.originalSpawnOrder = []
        self._inMultiRoundMatch = False
        # Initialize best-of settings
        self.d_setBestOf()
        self.d_setRoundInfo()

    def setupRuleset(self):

        self.ruleset = CraneLeagueGlobals.CraneGameRuleset()
        self.modifiers.clear()
        modifiers = []
        for modifier in self.desiredModifiers:
            modifiers.append(modifier)
        # Should we randomize some modifiers?
        if self.rollModsOnStart:
            modifiers += self.rollRandomModifiers()

        # Temporary until the ruleset/modifiers tabs are implemented into the rules panel interface.
        # If a toon is performing a solo crane round, use clash rules.
        # If there is more than one toon present, use competitive crane league rules.
        if len(self.getParticipantsNotSpectating()) >= 2:
            modifiers.append(CraneLeagueGlobals.ModifierInvincibleBoss())
            modifiers.append(CraneLeagueGlobals.ModifierTimerEnabler(3))

        self.applyModifiers(modifiers, updateClient=True)

        if self.getBoss() is not None:
            self.getBoss().setRuleset(self.ruleset)

    # Call to update the ruleset with the modifiers active, note calling more than once can cause unexpected behavior
    # if the ruleset doesn't fallback to an initial value, for example if a cfo hp increasing modifier is active and we
    # call this multiply times, his hp will be 1500 * 1.5 * 1.5 * 1.5 etc etc
    def applyModifiers(self, modifiers: list[CraneLeagueGlobals.CFORulesetModifierBase], updateClient=False):
        for modifier in modifiers:
            self.applyModifier(modifier, updateClient=False)
        if updateClient:
            self.d_setRawRuleset()
            self.d_setModifiers()

    def applyModifier(self, modifier: CraneLeagueGlobals.CFORulesetModifierBase, updateClient=False):
        self.modifiers.append(modifier)
        modifier.apply(self.ruleset)
        self.ruleset.validate()
        if updateClient:
            self.d_setRawRuleset()
            self.d_setModifiers()

    def removeModifier(self, modifierClass):
        modifiers = list(self.modifiers)
        for mod in self.modifiers:
            if mod.__class__ == modifierClass:
                modifiers.remove(mod)
        for mod in list(self.desiredModifiers):
            if mod.__class__ == modifierClass:
                self.desiredModifiers.remove(mod)
        self.modifiers = modifiers
        self.d_setRawRuleset()
        self.d_setModifiers()

    # Any time you change the ruleset, you should call this to sync the clients
    def d_setRawRuleset(self):
        self.sendUpdate('setRawRuleset', [self.getRawRuleset()])

    def __getRawModifierList(self):
        mods = []
        for modifier in self.modifiers:
            mods.append(modifier.asStruct())
        return mods

    def d_setModifiers(self):
        self.sendUpdate('setModifiers', [self.__getRawModifierList()])

    def rollRandomModifiers(self):
        tierLeftBound = self.ruleset.MODIFIER_TIER_RANGE[0]
        tierRightBound = self.ruleset.MODIFIER_TIER_RANGE[1]
        pool: list[CraneLeagueGlobals.CFORulesetModifierBase] = [c(random.randint(tierLeftBound, tierRightBound)) for c in
                CraneLeagueGlobals.NON_SPECIAL_MODIFIER_CLASSES]

        alreadyApplied = [mod.MODIFIER_ENUM for mod in self.desiredModifiers]
        for choice in list(pool):
            if choice.MODIFIER_ENUM in alreadyApplied:
                pool.remove(choice)

        if len(pool) <= 0:
            return

        random.shuffle(pool)

        modifiers = [pool.pop() for _ in range(self.numModsWanted)]

        # If we roll a % roll, go ahead and make this a special cfo
        # Doing this last also ensures any rules that the special mod needs to set override
        if random.randint(0, 99) < CraneLeagueGlobals.SPECIAL_MODIFIER_CHANCE:
            cls = random.choice(CraneLeagueGlobals.SPECIAL_MODIFIER_CLASSES)
            tier = random.randint(tierLeftBound, tierRightBound)
            mod_instance = cls(tier)
            modifiers.append(mod_instance)

        return modifiers

    def setGameStart(self, timestamp):
        self.notify.debug("setGameStart")
        # base class will cause gameFSM to enter initial state
        DistributedMinigameAI.setGameStart(self, timestamp)
        # all of the players are ready to start playing the game
        # transition to the appropriate ClassicFSM state
        self.gameFSM.request('prepare')

    def setGameAbort(self):
        self.notify.debug("setGameAbort")
        # this is called when the minigame is unexpectedly
        # ended (a player got disconnected, etc.)
        if self.gameFSM.getCurrentState():
            self.gameFSM.request('cleanup')

        DistributedMinigameAI.setGameAbort(self)
        if self.scene is not None:
            self.scene.removeNode()
            self.scene = None

    def gameOver(self):
        self.notify.debug("gameOver")
        # call this when the game is done
        # clean things up in this class
        self.gameFSM.request('cleanup')
        # tell the base class to wrap things up
        DistributedMinigameAI.gameOver(self)
        if self.scene is not None:
            self.scene.removeNode()
            self.scene = None

    def clearObjectSpeedCaching(self):
        for safe in self.safes:
            safe.d_resetSpeedCaching()

        for goon in self.goons:
            goon.d_resetSpeedCaching()

    def __makeCraningObjects(self):

        # Generate all of the cranes.
        self.cranes.clear()
        ind = 0

        for _ in CraneLeagueGlobals.NORMAL_CRANE_POSHPR:
            crane = DistributedCashbotBossCraneAI(self.air, self, ind)
            crane.generateWithRequired(self.zoneId)
            self.cranes.append(crane)
            ind += 1

        # Generate the sidecranes if wanted
        if self.ruleset.WANT_SIDECRANES:
            for _ in CraneLeagueGlobals.SIDE_CRANE_POSHPR:
                crane = DistributedCashbotBossSideCraneAI(self.air, self, ind)
                crane.generateWithRequired(self.zoneId)
                self.cranes.append(crane)
                ind += 1

        # Generate the heavy cranes if wanted
        if self.ruleset.WANT_HEAVY_CRANES:
            for _ in CraneLeagueGlobals.HEAVY_CRANE_POSHPR:
                crane = DistributedCashbotBossHeavyCraneAI(self.air, self, ind)
                crane.generateWithRequired(self.zoneId)
                self.cranes.append(crane)
                ind += 1

        # And all of the safes.
        self.safes.clear()
        for index in range(min(self.ruleset.SAFES_TO_SPAWN, len(CraneLeagueGlobals.SAFE_POSHPR))):
            safe = DistributedCashbotBossSafeAI(self.air, self, index)
            safe.generateWithRequired(self.zoneId)
            self.safes.append(safe)

        self.goons.clear()
        return

    def __resetCraningObjects(self):
        for crane in self.cranes:
            crane.request('Free')

        for safe in self.safes:
            safe.request('Initial')

    def __deleteCraningObjects(self):
        for crane in self.cranes:
            crane.request('Off')
            crane.requestDelete()

        self.cranes.clear()

        for safe in self.safes:
            safe.request('Off')
            safe.requestDelete()
        self.safes.clear()

        for goon in self.goons:
            goon.request('Off')
            goon.requestDelete()
        self.goons.clear()

    # Call to listen for toon death events. Useful for catching deaths caused by DeathLink.
    def listenForToonDeaths(self):
        self.ignoreToonDeaths()
        for toon in self.getParticipatingToons():
            self.__listenForToonDeath(toon)

    # Ignore toon death events. We don't need to worry about toons dying in specific scenarios
    # Such as turn based battles as BattleBase handles that for us.
    def ignoreToonDeaths(self):
        for event in self._deathListenerEvents:
            self.ignore(event)
        self._deathListenerEvents.clear()

    def __listenForToonDeath(self, toon):
        event = toon.getGoneSadMessage()
        self.accept(event, self.toonDied, [toon])
        self._deathListenerEvents.append(event)

    def __ignoreToonDeath(self, avId):
        self.ignore(DistributedToonAI.getGoneSadMessageForAvId(avId))

    def toonDied(self, toon):
        self.resetCombo(toon.doId)
        self.sendUpdate('toonDied', [toon.doId])

        # If we are in overtime, we don't need to do anything else.
        if self.currentlyInOvertime:
            self.__checkOvertimeState()
            return

        # Toons are expected to die in overtime. Only penalize them if it is in the normal round.
        self.addScore(toon.doId, self.ruleset.POINTS_PENALTY_GO_SAD, reason=ScoreReason.WENT_SAD)

        # Add a task to revive the toon.
        taskMgr.doMethodLater(self.ruleset.REVIVE_TOONS_TIME, self.reviveToon,
                              self.uniqueName(f"reviveToon-{toon.doId}"), extraArgs=[toon.doId])

    def getHighestScorers(self):
        """
        Gets a list of who is currently in the lead.
        If the list is empty, we have no players playing.
        If the list has one person, someone is in the lead.
        If the last has multiple people, they are tied for 1st place.
        """

        all_scores = self.getScoringContext().get_round(self.currentRound).get_all_scores()

        # Are there no players?
        if len(all_scores) <= 0:
            return []

        # Create a reversed dict where we map score to the players who have that score.
        results = {}
        highestScore = -999_999
        for player, score in all_scores.items():
            toonsWithScore = results.get(score, [])
            toonsWithScore.append(player)
            results[score] = toonsWithScore
            highestScore = max(highestScore, score)

        # Query the players with the highest score.
        return results[highestScore]

    def reviveToon(self, toonId: int) -> None:
        toon = self.air.getDo(toonId)
        if toon is None:
            return

        toon.b_setHp(int(self.ruleset.REVIVE_TOONS_LAFF_PERCENTAGE * toon.getMaxHp()))

        self.sendUpdate("revivedToon", [toonId])

    def d_updateCombo(self, avId, comboLength):
        self.sendUpdate('updateCombo', [avId, comboLength])

    def handleExitedAvatar(self, avId):
        taskMgr.remove(self.uniqueName(f"reviveToon-{avId}"))
        self.removeToon(avId)

        super().handleExitedAvatar(avId)

    def removeToon(self, avId):
        # The toon leaves the zone, either through disconnect, death,
        # or something else.  Tell all of the safes, cranes, and goons.
        for crane in self.cranes:
            crane.removeToon(avId)

        for safe in self.safes:
            safe.removeToon(avId)

        for goon in self.goons:
            goon.removeToon(avId)

    def initializeComboTrackers(self):
        self.cleanupComboTrackers()
        for avId in self.getParticipants():
            if avId in self.air.doId2do:
                self.comboTrackers[avId] = CashbotBossComboTracker(self, avId)

    def incrementCombo(self, avId, amount):
        tracker = self.comboTrackers.get(avId)
        if not tracker:
            return

        tracker.incrementCombo(amount)

    def resetCombo(self, avId):
        tracker = self.comboTrackers.get(avId)
        if not tracker:
            return

        tracker.resetCombo()

    def getComboLength(self, avId):
        tracker = self.comboTrackers.get(avId)
        if not tracker:
            return 0

        return tracker.combo

    def getComboAmount(self, avId):
        tracker = self.comboTrackers.get(avId)
        if not tracker:
            return 0

        return tracker.pointBonus

    def cleanupComboTrackers(self):
        for comboTracker in self.comboTrackers.values():
            comboTracker.cleanup()

    def grabAttempt(self, avId, treasureId):
        """
        A toon wants to grab a certain treasure. Validates the treasure is valid to grab
        """

        # First, try to see if we can find the treasure that was grabbed.
        treasure = self.treasures.get(treasureId)
        if treasure is None:
            return

        # Now get the toon that wants to grab it.
        toon = simbase.air.getDo(avId)
        if toon is None:
            return

        # Are they allowed to take this treasure?
        if not treasure.validAvatar(toon):
            treasure.d_setReject()
            return

        del self.treasures[treasureId]
        treasure.d_setGrab(avId)  # Todo a lot of logic is in this method call. This is such bad design and should prob be refactored.
        self.grabbingTreasures[treasureId] = treasure

        # Wait a few seconds for the animation to play, then
        # recycle the treasure.
        taskMgr.doMethodLater(5, self.__recycleTreasure, treasure.uniqueName('recycleTreasure'), extraArgs=[treasure])

    def __recycleTreasure(self, treasure):
        if treasure.doId in self.grabbingTreasures:
            del self.grabbingTreasures[treasure.doId]
            self.recycledTreasures.append(treasure)

    def deleteAllTreasures(self):
        for treasure in self.treasures.values():
            treasure.requestDelete()

        self.treasures = {}
        for treasure in self.grabbingTreasures.values():
            taskMgr.remove(treasure.uniqueName('recycleTreasure'))
            treasure.requestDelete()

        self.grabbingTreasures = {}
        for treasure in self.recycledTreasures:
            treasure.requestDelete()

        self.recycledTreasures = []

    def makeTreasure(self, goon):
        # Places a treasure, as pooped out by the given goon.  We
        # place the treasure at the goon's current position, or at
        # least at the beginning of its current path.  Actually, we
        # ignore Z, and always place the treasure at Z == 0,
        # presumably the ground.

        # Too many treasures on the field?
        if len(self.treasures) >= self.ruleset.MAX_TREASURE_AMOUNT:
            return

        # Drop chance?
        if self.ruleset.GOON_TREASURE_DROP_CHANCE < 1.0:
            if random.random() > self.ruleset.GOON_TREASURE_DROP_CHANCE:
                return

        # The BossCog acts like a treasure planner as far as the
        # treasure is concerned.
        pos = goon.getPos(self.boss)

        # The treasure pops out and lands somewhere nearby.  Let's
        # start by choosing a point on a ring around the boss, based
        # on our current angle to the boss.
        v = Vec3(pos[0], pos[1], 0.0)
        if not v.normalize():
            v = Vec3(1, 0, 0)
        v = v * 27

        # Then perterb that point by a distance in some random
        # direction.
        angle = random.uniform(0.0, 2.0 * math.pi)
        radius = 10
        dx = radius * math.cos(angle)
        dy = radius * math.sin(angle)

        fpos = self.scene.getRelativePoint(self.boss, Point3(v[0] + dx, v[1] + dy, 0))

        # Find an index based on the goon strength we should use
        treasureHealIndex = 1.0 * (goon.strength - self.ruleset.MIN_GOON_DAMAGE) / (
                    self.ruleset.MAX_GOON_DAMAGE - self.ruleset.MIN_GOON_DAMAGE)
        treasureHealIndex *= len(self.ruleset.GOON_HEALS)
        treasureHealIndex = int(clamp(treasureHealIndex, 0, len(self.ruleset.GOON_HEALS) - 1))
        healAmount = self.ruleset.GOON_HEALS[treasureHealIndex]
        availStyles = self.ruleset.TREASURE_STYLES[treasureHealIndex]
        style = random.choice(availStyles)

        if self.recycledTreasures:
            # Reuse a previous treasure object
            treasure = self.recycledTreasures.pop(0)
            treasure.d_setGrab(0)
            treasure.b_setGoonId(goon.doId)
            treasure.b_setStyle(style)
            treasure.b_setPosition(pos[0], pos[1], 0)
            treasure.b_setFinalPosition(fpos[0], fpos[1], 0)
        else:
            # Create a new treasure object
            treasure = DistributedCashbotBossTreasureAI(self.air, self, goon, style, fpos[0], fpos[1], 0)
            treasure.generateWithRequired(self.zoneId)
        treasure.healAmount = healAmount
        self.treasures[treasure.doId] = treasure

    def getMaxGoons(self):
        return self.progressValue(self.ruleset.MAX_GOON_AMOUNT_START, self.ruleset.MAX_GOON_AMOUNT_END)

    def __chooseGoonEmergeSide(self) -> str:
        """
        Determines the next side for a goon to emerge from.
        To limit the amount of RNG present, we prevent goons from spawning from the same side over and over in a row.
        """

        if self.practiceCheatHandler.wantOpeningModifications:
            # Controlled goon spawning logic, activated through commands.
            # Evaluate the toon position and spawn a goon based on it.
            avId = self.avIdList[self.practiceCheatHandler.openingModificationsToonIndex]
            toon = self.air.doId2do.get(avId)
            pos = toon.getPos()
            if pos[1] < -315:
                return 'EmergeB'
            return 'EmergeA'

        # Default goon spawning logic.
        # Is it okay to pick a random side?
        if self.goonCache[1] < 2:
            return random.choice(['EmergeA', 'EmergeB'])

        # There's too many goons coming from a certain side. Pick the opposite one.
        if self.goonCache[0] == 'EmergeA':
            return 'EmergeB'
        return 'EmergeA'

    def __isPositionClear(self, x, y, minDistance=5):
        # Check distance to all safes
        for safe in self.safes:
            safePos = safe.getPos()
            if abs(safePos[0] - x) < minDistance and abs(safePos[1] - y) < minDistance:
                return False
                
        # Check distance to all cranes
        for crane in self.cranes:
            # Get crane position based on its type and index
            if isinstance(crane, DistributedCashbotBossSideCraneAI):
                poshpr = CraneLeagueGlobals.SIDE_CRANE_POSHPR[crane.index - len(CraneLeagueGlobals.NORMAL_CRANE_POSHPR)]
            else:
                poshpr = CraneLeagueGlobals.NORMAL_CRANE_POSHPR[crane.index]
            cranePos = (poshpr[0], poshpr[1], poshpr[2])
            if abs(cranePos[0] - x) < minDistance and abs(cranePos[1] - y) < minDistance:
                return False
                
        return True

    def makeGoon(self, side=None, forceNormalSpawn=False, fallingChance=0.5):
        # Picks a side for a goon to generate on if not specified
        if side is None:
            side = self.__chooseGoonEmergeSide()

        # Should this goon fall if we are in overtime?
        falling = random.random() < fallingChance

        # Long logic process to determine whether a goon should be made and what type.
        # If we are at max goon size, do not make a new goon
        if len(self.goons) >= self.getMaxGoons():
            return

        #Only 2 current cases where goons should spawn when the CFO is stunned
        if self.boss.isStunned():
            #If we are in OT and we roll a falling goon and it's not a forced normal spawn
            if self.currentlyInOvertime and falling and not forceNormalSpawn:
                pass
            #Or if we are in live goon practice mode
            elif self.practiceCheatHandler.wantGoonPractice:
                pass
            else:
                return

        #From here on out, a goon is guaranteed to be created on a specific side of the room
        self.__updateGoonCache(side)

        # Create and generate the goon
        goon = DistributedCashbotBossGoonAI(self.air, self)
        goon.generateWithRequired(self.zoneId)
        self.goons.append(goon)

        # Attributes for desperation mode goons
        goon_stun_time = 6
        goon_velocity = 7
        goon_hfov = 90
        goon_attack_radius = 17
        goon_strength = self.ruleset.MAX_GOON_DAMAGE + 10
        goon_scale = self.goonMaxScale + .1

        # If the battle isn't in desperation yet override the values to normal values
        if self.getBattleThreeTime() <= 1.0:
            goon_stun_time = self.progressValue(30, 8)
            goon_velocity = self.progressRandomValue(3, 7)
            goon_hfov = self.progressRandomValue(70, 80)
            goon_attack_radius = self.progressRandomValue(6, 15)
            goon_strength = int(self.progressRandomValue(self.ruleset.MIN_GOON_DAMAGE, self.ruleset.MAX_GOON_DAMAGE))
            goon_scale = self.progressRandomValue(self.goonMinScale, self.goonMaxScale, noRandom=self.practiceCheatHandler.wantMaxSizeGoons)

        # Apply multipliers if necessary
        goon_velocity *= self.ruleset.GOON_SPEED_MULTIPLIER

        # Apply attributes to the goon
        goon.STUN_TIME = goon_stun_time
        goon.b_setupGoon(velocity=goon_velocity, hFov=goon_hfov, attackRadius=goon_attack_radius,
                         strength=goon_strength, scale=goon_scale)

        # Properly set up the goon in "Falling" state if necessary
        if self.currentlyInOvertime and falling:
            self.__makeFallingGoon(goon, side)
        else:
            goon.request(side)

    def __updateGoonCache(self, side):
        if side == self.goonCache[0]:
            self.goonCache = (side, self.goonCache[1] + 1)
        else:
            self.goonCache = (side, 1)

    def __makeFallingGoon(self, goon, side):
        bossPos = self.boss.getPos()

        # Keep trying positions until we find a clear one
        # Took out prevent infinite loops code because 8 safes give a maximum of 200pi area covered
        # Half of our allotted area for falling goons is 250 pi. Chance of 21+ iterations is 1.15%. 41+ is 0.013%.
        while True:
            # Random position 15-20 units away from CFO on correct side
            radius = random.uniform(20, 30)
            theta = random.uniform(-math.pi, math.pi)
            xPos = bossPos[0] + radius * math.cos(theta)

            #Bad luck protection position calculation
            if side == "EmergeA":
                yPos = bossPos[1] + abs(radius * math.sin(theta))
            else:
                yPos = bossPos[1] - abs(radius * math.sin(theta))

            # Check if position is clear
            if self.__isPositionClear(xPos, yPos):
                randomH = random.uniform(0, 360)  # Random heading between 0-360 degrees
                goon.b_setPosHpr(xPos, yPos, 40, randomH, 0, 0)
                goon.request('Falling')
                return

    def waitForNextGoon(self, delayTime):
        taskName = self.uniqueName('NextGoon')
        taskMgr.remove(taskName)
        self._allTaskNames.add(taskName)
        taskMgr.doMethodLater(delayTime, self.doNextGoon, taskName)

    def stopGoons(self):
        taskName = self.uniqueName('NextGoon')
        taskMgr.remove(taskName)

    def doNextGoon(self, task):
        self.makeGoon()
        # How long to wait for the next goon?
        delayTime = self.progressValue(10, 2)
        if self.practiceCheatHandler.wantFasterGoonSpawns:
            delayTime = 4
        self.waitForNextGoon(delayTime)

    def progressValue(self, fromValue, toValue):
        if self.ruleset.TIMER_MODE:
            elapsed = globalClock.getFrameTime() - self.battleThreeStart
            t = elapsed / float(self.ruleset.TIMER_MODE_TIME_LIMIT)
        else:
            t0 = float(self.getBoss().bossDamage) / float(self.ruleset.CFO_MAX_HP)
            elapsed = globalClock.getFrameTime() - self.battleThreeStart
            t1 = elapsed / float(self.DESPERATION_MODE_ACTIVATE_THRESHOLD)
            t = max(t0, t1)
        return fromValue + (toValue - fromValue) * min(t, 1)

    def progressRandomValue(self, fromValue, toValue, radius=0.2, noRandom=False):
        t = self.progressValue(0, 1)
        radius = radius * (1.0 - abs(t - 0.5) * 2.0)
        if noRandom:
            t += radius
        else:
            t += radius * random.uniform(-1, 1)
        t = max(min(t, 1.0), 0.0)
        return fromValue + (toValue - fromValue) * t

    def getBattleThreeTime(self):
        elapsed = globalClock.getFrameTime() - self.battleThreeStart
        duration = self.ruleset.TIMER_MODE_TIME_LIMIT if self.ruleset.TIMER_MODE else self.DESPERATION_MODE_ACTIVATE_THRESHOLD
        t1 = elapsed / float(duration)
        return t1

    def setupSpawnpoints(self):
        # Only reset spawn order if it hasn't been manually customized by the leader
        if not hasattr(self, 'customSpawnOrderSet') or not self.customSpawnOrderSet:
            self.toonSpawnpointOrder = [i for i in range(16)]
            if self.ruleset.RANDOM_SPAWN_POSITIONS:
                random.shuffle(self.toonSpawnpointOrder)
        self.d_setToonSpawnpointOrder()

    def resetCustomSpawnOrder(self):
        """Reset the custom spawn order flag, allowing spawn points to be randomized again"""
        self.customSpawnOrderSet = False

    def d_setToonSpawnpointOrder(self):
        self.sendUpdate('setToonSpawnpointOrder', [self.toonSpawnpointOrder])

    def updateSpawnOrder(self, newOrder):
        """Handle spawn order update from the leader"""
        # Verify the sender is the leader (first player in avIdList)
        senderId = self.air.getAvatarIdFromSender()
        if senderId != self.avIdList[0]:
            self.notify.warning(f"Non-leader {senderId} tried to update spawn order")
            return
            
        # Validate the new order contains the same avatars
        if set(newOrder) != set(self.toonSpawnpointOrder):
            self.notify.warning(f"Invalid spawn order update from {senderId}: {newOrder}")
            return
            
        # Update the spawn order and mark it as customized
        self.toonSpawnpointOrder = newOrder[:]
        self.customSpawnOrderSet = True
        self.d_setToonSpawnpointOrder()
        self.notify.info(f"Spawn order updated by leader {senderId}: {self.toonSpawnpointOrder}")

    def setBestOf(self, value):
        """Handle best-of setting from the leader"""
        # Verify the sender is the leader (first player in avIdList)
        senderId = self.air.getAvatarIdFromSender()
        if senderId != self.avIdList[0]:
            self.notify.warning(f"Non-leader {senderId} tried to set best-of value")
            return
            
        # Validate the value
        if value not in [1, 3, 5, 7]:
            self.notify.warning(f"Invalid best-of value from {senderId}: {value}")
            return
            
        self.bestOfValue = value
        self.d_setBestOf()
        self.notify.info(f"Best-of value set to {value} by leader {senderId}")

    def d_setBestOf(self):
        """Send best-of value to all clients"""
        self.sendUpdate('setBestOf', [self.bestOfValue])

    def d_setRoundInfo(self):
        """Send round information to all clients"""
        # Convert roundWins dict to list format for transmission
        roundWinsList = []
        for avId in self.avIdList:
            roundWinsList.append(self.roundWins.get(avId, 0))
        self.sendUpdate('setRoundInfo', [self.currentRound, roundWinsList])

    def nextRound(self):
        """Handle transition to next round in best-of matches"""
        if self.bestOfValue <= 1:
            return  # Not a best-of match
        
        self.currentRound += 1
        self._inMultiRoundMatch = True  # Flag to indicate we're in a multi-round match
        
        # Start the next round after a brief delay
        taskMgr.doMethodLater(0.5, self.__startNextRound, self.uniqueName("startNextRound"))

    def __startNextRound(self, task=None):
        """Start the next round in a best-of match"""
        # Rotate spawn positions for variety
        self.__rotateSpawnPositions()
        
        # Use proper FSM transitions like the RestartCraneRound magic word
        self.gameFSM.request("cleanup")
        self.gameFSM.request('prepare')
        
        # Send round info to clients immediately after restart
        self.d_setRoundInfo()

    def __rotateSpawnPositions(self):
        """Rotate spawn positions for the next round"""
        # Get participating toons (not spectating)
        participatingToons = self.getParticipantIdsNotSpectating()
        numParticipants = len(participatingToons)
        
        if numParticipants <= 1:
            return  # No rotation needed for single player
        
        # Store the original spawn positions if this is the first rotation
        if not hasattr(self, 'originalSpawnOrder') or not self.originalSpawnOrder:
            self.originalSpawnOrder = self.toonSpawnpointOrder[:numParticipants]
        
        # Get the current spawn positions for participating players
        currentPositions = self.toonSpawnpointOrder[:numParticipants]
        
        # Rotate positions: each player moves to the next position
        # Player at position 0 -> position 1, position 1 -> position 2, etc.
        # Last player wraps around to position 0
        rotatedPositions = [currentPositions[(i + 1) % numParticipants] for i in range(numParticipants)]
        
        # Update the spawn order with rotated positions
        for i in range(numParticipants):
            self.toonSpawnpointOrder[i] = rotatedPositions[i]
        
        # Mark spawn order as customized so setupSpawnpoints() doesn't override it
        self.customSpawnOrderSet = True
        
        self.d_setToonSpawnpointOrder()
        self.notify.info(f"Rotated spawn positions for round {self.currentRound}: {self.toonSpawnpointOrder[:numParticipants]}")

    def getRawRuleset(self):
        return self.ruleset.asStruct()

    def d_setBossCogId(self) -> None:
        self.sendUpdate("setBossCogId", [self.boss.getDoId()])
    
    def d_setStatusEffectSystemId(self) -> None:
        self.sendUpdate("setStatusEffectSystemId", [self.statusEffectSystem.getDoId()])

    def getBoss(self):
        return self.boss

    def damageToon(self, toon, deduction):
        if toon.getHp() <= 0:
            return

        if self.isSpectating(toon.getDoId()):
            return

        toon.takeDamage(deduction)

    def getToonOutgoingMultiplier(self, avId):
        return 100

    def recordHit(self, damage, impact=0, craneId=-1, objId=0, isGoon=False, isDOT=False):

        # Don't process a hit if we aren't in the play state.
        if self.gameFSM.getCurrentState().getName() != 'play':
            return

        avId = self.air.getAvatarIdFromSender()
        crane = simbase.air.doId2do.get(craneId)
        if not self.validate(avId, avId in self.getParticipants(), 'recordHit from unknown avatar'):
            return
        
        # Apply damage vulnerability if SHATTERED is active
        if self.statusEffectSystem.hasStatusEffect(self.getBoss().doId, StatusEffect.SHATTERED):
            damage += int(damage * 0.5)

        # Record a successful hit in battle three.
        self.boss.b_setBossDamage(self.boss.bossDamage + damage, avId=avId, objId=objId, isGoon=isGoon, isDOT=isDOT)

        # Award bonus points for hits with maximum impact (but not for DOT)
        if impact == 1.0 and not isDOT:
            self.addScore(avId, self.ruleset.POINTS_IMPACT, reason=CraneLeagueGlobals.ScoreReason.FULL_IMPACT)
        self.addScore(avId, damage)

        # DOT damage should not contribute to combos
        if not isDOT:
            comboTracker = self.comboTrackers[avId]
            comboTracker.incrementCombo((comboTracker.combo + 1.0) / 10.0 * damage)

        # The CFO has been defeated, proceed to Victory state
        if self.boss.bossDamage >= self.ruleset.CFO_MAX_HP:
            self.addScore(avId, self.ruleset.POINTS_KILLING_BLOW, CraneLeagueGlobals.ScoreReason.KILLING_BLOW)
            self.toonsWon = True
            self.gameFSM.request('victory')
            return

        # DOT damage should not cause flinching, stunning, or helmet behavior
        if isDOT:
            return

        # The CFO is already dizzy, OR the crane is None, so get outta here
        if self.boss.attackCode == ToontownGlobals.BossCogDizzy or not crane:
            return

        self.boss.stopHelmets()

        # Is the damage high enough to stun? or did a side crane hit a high impact hit?
        hitMeetsStunRequirements = self.boss.considerStun(crane, damage, impact)
        if hitMeetsStunRequirements:
            # A particularly good hit (when he's not already
            # dizzy) will make the boss dizzy for a little while.
            delayTime = self.progressValue(20, 5)
            self.boss.b_setAttackCode(ToontownGlobals.BossCogDizzy, delayTime=delayTime)
            isSideCrane = isinstance(crane, DistributedCashbotBossSideCraneAI)
            reason = CraneLeagueGlobals.ScoreReason.SIDE_STUN if isSideCrane else CraneLeagueGlobals.ScoreReason.STUN
            self.addScore(avId, crane.getPointsForStun(), reason=reason)
        else:

            if self.ruleset.CFO_FLINCHES_ON_HIT:
                self.boss.b_setAttackCode(ToontownGlobals.BossCogNoAttack)

            self.boss.waitForNextHelmet()

        # Now at the very end, if we have momentum mechanic on add some damage multiplier
        if self.ruleset.WANT_MOMENTUM_MECHANIC:
            self.increaseToonOutgoingMultiplier(avId, damage)

    def increaseToonOutgoingMultiplier(self, avId, n):
        """
        todo: implement
        """
        pass
    
    def recordHitWithAttribution(self, damage, attributeToAvId, impact=0, craneId=-1, objId=0, isGoon=False, isDOT=False):
        """
        Record a hit with damage attributed to a specific avatar ID.
        Used for status effects that deal damage on behalf of other players.
        """
        # Don't process a hit if we aren't in the play state.
        if self.gameFSM.getCurrentState().getName() != 'play':
            return

        # Validate that the attributed player is in the game
        if not self.validate(attributeToAvId, attributeToAvId in self.getParticipants(), 'recordHitWithAttribution to unknown avatar'):
            return
        
        # Apply damage vulnerability if SHATTERED is active
        if self.statusEffectSystem.hasStatusEffect(self.getBoss().doId, StatusEffect.SHATTERED):
            damage += int(damage * 0.5)

        # Record a successful hit in battle three.
        self.boss.b_setBossDamage(self.boss.bossDamage + damage, avId=attributeToAvId, objId=objId, isGoon=isGoon, isDOT=isDOT)

        # Award points for the damage (no impact bonus for attributed damage)
        self.addScore(attributeToAvId, damage)

        # DOT damage should not contribute to combos
        if not isDOT:
            comboTracker = self.comboTrackers[attributeToAvId]
            comboTracker.incrementCombo((comboTracker.combo + 1.0) / 10.0 * damage)

        # The CFO has been defeated, proceed to Victory state
        if self.boss.bossDamage >= self.ruleset.CFO_MAX_HP:
            self.addScore(attributeToAvId, self.ruleset.POINTS_KILLING_BLOW, CraneLeagueGlobals.ScoreReason.KILLING_BLOW)
            self.toonsWon = True
            self.gameFSM.request('victory')
            return

        # DOT damage should not cause flinching, stunning, or helmet behavior
        if isDOT:
            return

        # The CFO is already dizzy, OR there's no crane, so get outta here
        if self.boss.attackCode == ToontownGlobals.BossCogDizzy:
            return

        self.boss.stopHelmets()

        # For attributed damage, we don't handle stunning since there's no crane
        if self.ruleset.CFO_FLINCHES_ON_HIT:
            self.boss.b_setAttackCode(ToontownGlobals.BossCogNoAttack)

        self.boss.waitForNextHelmet()

        # Now at the very end, if we have momentum mechanic on add some damage multiplier
        if self.ruleset.WANT_MOMENTUM_MECHANIC:
            self.increaseToonOutgoingMultiplier(attributeToAvId, damage)

    def addScore(self, avId: int, amount: int, reason: CraneLeagueGlobals.ScoreReason = CraneLeagueGlobals.ScoreReason.DEFAULT):

        if amount == 0:
            return

        self.getScoringContext().get_round(self.currentRound).add_score(avId, amount)
        self.d_addScore(avId, amount, reason)

        # Update current winners so we can check for position overtakes (where we should enable overtime)
        self.__updateCurrentWinners()

        # If we are in overtime, check the overtime state. There is a chance this toon overtook 1st place when
        # everyone is dead and should be declared winner.
        if self.currentlyInOvertime and reason != CraneLeagueGlobals.ScoreReason.COIN_FLIP:
            self.__checkOvertimeState()

        # Check if we can award an uber bonus for being low laff
        self.__awardUberBonusIfEligible(avId, amount, reason)

    def __updateCurrentWinners(self):

        newLeaders = self.getHighestScorers()

        # Perform a quick check for overtime enabling.
        # This check basically is making sure that we are the clock is running low and there is a new leader to check.
        if self.ruleset.TIMER_MODE and not self.overtimeWillHappen and len(newLeaders) > 0 and self.__calculateTimeToSend() < self.OVERTIME_OVERTAKE_ACTIVATION_THRESHOLD:

            # Is there a tie (or was there a tie)?
            tie = len(newLeaders) > 1 or len(self.currentWinners) > 1
            # Is the new leader not the previous?
            overtake = newLeaders[0] != self.currentWinners[0]
            if tie or overtake:
                self.enableOvertime()

        # Update who is currently winning
        self.currentWinners = newLeaders


    def __awardUberBonusIfEligible(self, avId, amount, reason):
        if not self.ruleset.WANT_LOW_LAFF_BONUS:
            return

        if reason.ignore_uber_bonus():
            return

        toon = simbase.air.getDo(avId)
        if toon is None:
            return

        if toon.getHp() > self.ruleset.LOW_LAFF_BONUS_THRESHOLD:
            return

        uberAmount = int(self.ruleset.LOW_LAFF_BONUS * amount)
        if uberAmount == 0:
            return

        # Add additional score if uber bonus is on.
        self.addScore(avId, uberAmount, reason=CraneLeagueGlobals.ScoreReason.LOW_LAFF)


    def d_addScore(self, avId: int, amount: int, reason: CraneLeagueGlobals.ScoreReason = CraneLeagueGlobals.ScoreReason.DEFAULT):
        self.sendUpdate('addScore', [avId, amount, reason.to_astron()])

    def d_setCraneSpawn(self, want, spawn, toonId):
        self.sendUpdate('setCraneSpawn', [want, spawn, toonId])

    """
    FSM states
    """

    def enterInactive(self):
        self.notify.debug("enterInactive")

    def exitInactive(self):
        pass

    def __updateSkillProfile(self):
        # Todo: Not every crane game needs to be ranked. Add in an option to make a game unranked.
        if len(self.getParticipantsNotSpectating()) == 2:
            self.b_setProfileSkillKey(SkillProfileKey.CRANING_SOLOS)
        elif len(self.getParticipantsNotSpectating()) >= 3:
            self.b_setProfileSkillKey(SkillProfileKey.CRANING_FFA)

    def enterPrepare(self):
        self.notify.debug("enterPrepare")
        if not self.__bossExists():
            self.__makeBoss()
        self.boss.b_setAttackCode(ToontownGlobals.BossCogNoAttack)
        self.__makeCraningObjects()
        self.__resetCraningObjects()
        self.setupRuleset()
        self.setupSpawnpoints()

        self.__updateSkillProfile()

        # Send round info to clients if this is a best-of match
        if self.bestOfValue > 1:
            self.d_setRoundInfo()

        # Calculate how long we should wait to actually start the game.
        # If more than 1 player is present, we want to have a delay present for a cutscene to play.
        delayTime = CraneGameGlobals.PREPARE_LATENCY_FACTOR
        if len(self.getParticipantIdsNotSpectating()) != 1:
            delayTime += CraneGameGlobals.PREPARE_DELAY
        taskMgr.doMethodLater(delayTime, self.gameFSM.request, self.uniqueName('start-game-task'), extraArgs=['play'])
        self.d_restart()

    def exitPrepare(self):
        self.notify.debug("exitPrepare")
        taskMgr.remove(self.uniqueName('start-game-task'))

    def enterPlay(self):
        self.notify.debug("enterPlay")
        taskMgr.remove(self.uniqueName("craneGameVictory"))
        self.battleThreeStart = globalClock.getFrameTime()

        # Stop toon passive healing.
        for toon in self.getParticipatingToons():
            toon.stopToonUp()

        # Listen to death messages.
        self.listenForToonDeaths()
        self.boss.clearSafeHelmetCooldowns()
        self.__resetCraningObjects()
        self.boss.prepareBossForBattle()

        # Just in case we didn't pass through PrepareBattleThree state.
        self.setupSpawnpoints()

        # Make four goons up front to keep things interesting from the
        # beginning.
        self.makeGoon(side='EmergeA', forceNormalSpawn=True)
        self.makeGoon(side='EmergeB', forceNormalSpawn=True)
        taskName = self.uniqueName('NextGoon')
        taskMgr.remove(taskName)
        taskMgr.doMethodLater(2, self.__doInitialGoons, taskName)

        self.initializeComboTrackers()

        # Fix all toon's HP that are present.
        for toon in self.getParticipatingToons():
            if self.ruleset.FORCE_MAX_LAFF:
                toon.b_setMaxHp(self.ruleset.FORCE_MAX_LAFF_AMOUNT)

            if self.ruleset.HEAL_TOONS_ON_START:
                toon.b_setHp(toon.getMaxHp())

        self.toonsWon = False
        taskMgr.remove(self.uniqueName('times-up-task'))
        taskMgr.remove(self.uniqueName('post-times-up-task'))
        # If timer mode is active, end the crane round later
        if self.ruleset.TIMER_MODE:
            taskMgr.doMethodLater(self.ruleset.TIMER_MODE_TIME_LIMIT, self.__timesUp, self.uniqueName('times-up-task'))

        r = self.getScoringContext().get_round(self.currentRound).reset_scores()

        self.currentWinners = self.getParticipantIdsNotSpectating()

        self.d_setOvertime(CraneLeagueGlobals.OVERTIME_FLAG_DISABLE)

        # Laff drain?
        if self.ruleset.WANT_LAFF_DRAIN:
            self.startDrainingLaff(self.ruleset.LAFF_DRAIN_FREQUENCY)

        # Check for special logic if we are restarting the round with cheats enabled previously.
        self.practiceCheatHandler.checkCheatModifier()
        if self.practiceCheatHandler.wantAimPractice or self.practiceCheatHandler.wantAimRightPractice or self.practiceCheatHandler.wantAimLeftPractice or self.practiceCheatHandler.wantAimAlternatePractice or self.practiceCheatHandler.wantGoonPractice:
            self.practiceCheatHandler.setupAimMode()
        if self.practiceCheatHandler.cheatIsEnabled():
            taskMgr.remove(self.uniqueName('times-up-task'))
            self.d_updateTimer()

        if self.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            self.startSafeEffectTask()

    def __applyRandomSafeEffects(self, task=None):
        """Apply random status effects to safes periodically"""
        if random.random() < 0.9:  # 90% chance
            for safe in self.safes:
                if safe and not self.statusEffectSystem.isObjectStatusEffected(safe.getDoId()):
                    statusEffect = random.choice(list(SAFE_ALLOWED_EFFECTS))
                    self.statusEffectSystem.b_applyStatusEffect(safe.getDoId(), statusEffect)
                    # Remove the effect after 10 seconds
                    taskMgr.doMethodLater(10.0, lambda task, doId=safe.getDoId(), effect=statusEffect: self.statusEffectSystem.b_removeStatusEffect(doId, effect) or task.done, self.uniqueName(f'remove-effect-{safe.getDoId()}'))
        return task.again

    def startSafeEffectTask(self):
        """Start the task that periodically applies effects to safes"""
        taskName = self.uniqueName('safe-effects')
        taskMgr.remove(taskName)
        taskMgr.doMethodLater(10.0, self.__applyRandomSafeEffects, taskName)

    # Called when we actually run out of time, simply tell the clients we ran out of time then handle it later
    def __timesUp(self, task=None):
        taskMgr.remove(self.uniqueName('times-up-task'))

        # If we aren't about to enter overtime, feel free to end the game here.
        if not self.overtimeWillHappen:
            self.toonsWon = False
            self.gameFSM.request('victory')
            return

        self.__enterOvertimeMode()

    def enableOvertime(self):
        """
        Marks this game in progress to enter overtime when time is up.
        """
        self.overtimeWillHappen = True
        self.d_setOvertime(CraneLeagueGlobals.OVERTIME_FLAG_ENABLE)

    def __enterOvertimeMode(self):
        """
        Adjust the state of the boss to force this game to find a winner with more extreme measures.
        """
        self.currentlyInOvertime = True
        self.d_setOvertime(CraneLeagueGlobals.OVERTIME_FLAG_START)

        modifiers = [
            CraneLeagueGlobals.ModifierGoonCapIncreaser(tier=1),
            CraneLeagueGlobals.ModifierNoSafeHelmet(tier=1),
            CraneLeagueGlobals.ModifierTreasureHealDecreaser(tier=2),
            CraneLeagueGlobals.ModifierLaffDrain(tier=3),
            CraneLeagueGlobals.ModifierNoRevives(tier=1),
        ]

        self.applyModifiers(modifiers, updateClient=True)

        # Some modifiers don't exactly support us adding them mid-round based on state. Perform that logic here.
        self.getBoss().stopHelmets()
        self.startDrainingLaff(self.ruleset.LAFF_DRAIN_FREQUENCY)
        self.__cancelReviveTasks()
        self.d_setModifiers()

    def __checkOvertimeState(self):
        """
        Analyze the state of the game right now.
        We can only end overtime if it is impossible for someone else to win.
        """
        aliveToons = []
        for toon in self.getParticipantsNotSpectating():
            if toon.getHp() > 0:
                aliveToons.append(toon)

        allToonsAreDead = len(aliveToons) == 0
        winnerIsAlreadyDetermined = len(aliveToons) == 1 and len(self.currentWinners) == 1 and self.currentWinners[0] == aliveToons[0].getDoId()

        # Absolute freak incident check. Are we STILL tied for first place when everyone died?
        # If so, assign one lucky person the win.
        # In the future, we can probably determine this another way, but right now I am lazy.
        if allToonsAreDead and len(self.currentWinners) > 1:
            self.addScore(random.choice(self.currentWinners), 1, CraneLeagueGlobals.ScoreReason.COIN_FLIP)

        # End the game if everyone died or if it is literally impossible for the winner to be overtaken.
        if allToonsAreDead or winnerIsAlreadyDetermined:
            self.toonsWon = False
            self.gameFSM.request('victory')
            return

    def __getLaffDrainTaskName(self):
        return self.uniqueName('laff-drain-task')

    def stopDrainingLaff(self):
        taskMgr.remove(self.__getLaffDrainTaskName())

    def startDrainingLaff(self, interval):
        self.stopDrainingLaff()
        taskMgr.add(self.__laffDrainTask, self.__getLaffDrainTaskName(), delay=interval)

    def __laffDrainTask(self, task):
        """
        Drain all present toons' laff by one.
        """
        for toon in self.getParticipantsNotSpectating():
            if not self.ruleset.LAFF_DRAIN_KILLS_TOONS and toon.getHp() <= 1:
                continue
            self.damageToon(toon, 1)
        return task.again

    def __doInitialGoons(self, task):
        # Initial goons should ALWAYS come from doors
        self.makeGoon(side='EmergeA', forceNormalSpawn=True)
        self.makeGoon(side='EmergeB', forceNormalSpawn=True)
        self.goonCache = (None, 0)
        self.waitForNextGoon(10)
        self.__cancelReviveTasks()

    def __cancelReviveTasks(self):
        """
        Cleanup function to cancel any impending revives.
        """
        for toonId in self.getParticipants():
            taskMgr.remove(self.uniqueName(f"reviveToon-{toonId}"))

    def exitPlay(self):

        for comboTracker in self.comboTrackers.values():
            comboTracker.finishCombo()

        # Get rid of all the CFO objects.
        self.deleteAllTreasures()
        self.stopGoons()
        self.__resetCraningObjects()
        self.deleteAllTreasures()
        taskMgr.remove(self.uniqueName('times-up-task'))
        taskName = self.uniqueName('NextGoon')
        taskMgr.remove(taskName)

        self.stopDrainingLaff()
        self.currentlyInOvertime = False
        self.overtimeWillHappen = False
        self.d_setOvertime(CraneLeagueGlobals.OVERTIME_FLAG_DISABLE)

        # Ignore death messages.
        self.ignoreToonDeaths()
        self.__cancelReviveTasks()

        for toon in self.getParticipatingToons():
            # Restart toon passive healing.
            toon.startToonUp(ToontownGlobals.PassiveHealFrequency)
            # Restore health.
            toon.b_setHp(toon.getMaxHp())

        if self.boss is not None:
            self.boss.cleanupBossBattle()

        craneTime = globalClock.getFrameTime()
        actualTime = craneTime - self.battleThreeStart
        timeToSend = 0.0 if self.ruleset.TIMER_MODE and not self.toonsWon else actualTime
        self.d_updateTimer(timeToSend)

    def __calculateTimeToSend(self):
        """
        Determine a proper time to send to the client to show on their timers.
        """
        craneTime = globalClock.getFrameTime()
        actualTime = craneTime - self.battleThreeStart
        return actualTime if not self.ruleset.TIMER_MODE else self.ruleset.TIMER_MODE_TIME_LIMIT - actualTime

    def d_updateTimer(self, time=None):
        if time is None:
            time = self.__calculateTimeToSend()
        self.sendUpdate('updateTimer', [time])

    def d_restart(self):
        self.sendUpdate('restart', [])

    def d_setOvertime(self, flag):
        self.sendUpdate('setOvertime', [flag])

    def enterVictory(self):


        highest_scorers = self.getHighestScorers()

        # If nobody is in the lead (?) then go next round.
        if len(highest_scorers) == 0:
            self.sendUpdate("declareVictor", [0])
            taskMgr.doMethodLater(5, self.__startNextRound, self.uniqueName("craneGameNextRound"), extraArgs=[])
            return

        # If multiple people are in the lead (?) then just pick the first person. Otherwise, it will be THE winner.
        victorId = highest_scorers[0]
        self.getScoringContext().get_round(self.currentRound).set_winners(highest_scorers)

        # Handle best-of matches
        if self.bestOfValue > 1:
            # Track round wins
            self.roundWins[victorId] = self.roundWins.get(victorId, 0) + 1

            winsNeeded = (self.bestOfValue + 1) // 2
            
            # Send round info to clients
            self.d_setRoundInfo()
            
            # Check if match is complete
            if self.roundWins[victorId] >= winsNeeded:
                # Match is complete
                self.sendUpdate("declareVictor", [victorId])
                taskMgr.doMethodLater(5, self.gameOver, self.uniqueName("craneGameVictory"), extraArgs=[])
            else:
                # Round is complete, but match continues
                self.sendUpdate("declareVictor", [victorId])
                taskMgr.doMethodLater(3, self.__startNextRound, self.uniqueName("craneGameNextRound"), extraArgs=[])
        else:
            # Single round match
            self.sendUpdate("declareVictor", [victorId])
            taskMgr.doMethodLater(5, self.gameOver, self.uniqueName("craneGameVictory"), extraArgs=[])

    def getWinners(self):

        # Find who has most round wins.
        most = -1
        for avId, wins in self.roundWins.items():
            if wins > most:
                most = wins

        # Filter who has most round wins
        winners = []
        for avId, wins in self.roundWins.items():
            if wins == most:
                winners.append(avId)

        return winners


    def exitVictory(self):
        taskMgr.remove(self.uniqueName("craneGameVictory"))
        taskMgr.remove(self.uniqueName("craneGameNextRound"))

    def enterCleanup(self):
        self.notify.debug("enterCleanup")
        self.__deleteCraningObjects()
        self.__deleteBoss()
        self.gameFSM.request('inactive')

    def exitCleanup(self):
        pass

    def handleSpotStatusChanged(self, spotIndex, isPlayer):
        """
        Called when the leader changes a spot's status between Player and Spectator
        """
        if spotIndex >= len(self.avIdList):
            return
            
        avId = self.avIdList[spotIndex]
        currentSpectators = list(self.getSpectators())
        
        if isPlayer and avId in currentSpectators:
            currentSpectators.remove(avId)
        elif not isPlayer and avId not in currentSpectators:
            currentSpectators.append(avId)
            
        self.b_setSpectators(currentSpectators)
        # Broadcast the spot status change to all clients
        self.sendUpdate('updateSpotStatus', [spotIndex, isPlayer])

        self.__updateSkillProfile()

    def b_setAsmr(self, asmr: bool):
        self.setAsmr(asmr)
        self.d_setAsmr(asmr)

    def d_setAsmr(self, asmr: bool):
        self.sendUpdate('setAsmr', [asmr])

    def setAsmr(self, asmr: bool):
        self.asmr = asmr