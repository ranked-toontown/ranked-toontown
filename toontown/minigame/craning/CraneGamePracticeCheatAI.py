import math
import random
import typing

from direct.directnotify import DirectNotifyGlobal

from toontown.coghq import CraneLeagueGlobals
from toontown.toonbase import ToontownGlobals

if typing.TYPE_CHECKING:
    from toontown.minigame.craning.DistributedCraneGameAI import DistributedCraneGameAI


class CraneGamePracticeCheatAI:

    notify = DirectNotifyGlobal.directNotify.newCategory("CraneGameSafeAimCheatAI")

    # Practice modes
    RNG_MODE = 1
    SAFE_RUSH_PRACTICE = 2
    LIVE_GOON_PRACTICE = 3
    AIM_PRACTICE = 4
    GOON_PRACTICE = 5  # New practice mode
    A_R_PRACTICE = 6
    A_L_PRACTICE = 7
    A_ALT_PRACTICE = 8

    """
    Activated via magic words when cheats are enabled for a crane game minigame.
    Provides various methods of practicing in the crane round.
    """
    def __init__(self, game: "DistributedCraneGameAI"):
        self.game = game
        self.numSafesWanted = 0
        self.forwardDistance = 10
        self.alternateDirection = True  # True for right, False for left
        self.isFirstAlternate = True   # Used to make random choice on first drop

        # Practice mode bools
        self.wantRNGMode = False
        self.wantSafeRushPractice = False
        self.wantLiveGoonPractice = False
        self.wantAimPractice = False
        self.wantAimRightPractice = False
        self.wantAimLeftPractice = False
        self.wantAimAlternatePractice = False
        self.wantGoonPractice = False

        # Practice mode parameters
        self.wantOpeningModifications = False
        self.openingModificationsToonIndex = 0
        self.wantMaxSizeGoons = False
        self.wantStunning = False
        self.wantNoStunning = False
        self.wantFasterGoonSpawns = False
        self.wantAlwaysStunned = False

    def cheatIsEnabled(self):
        return True in (self.wantRNGMode, self.wantSafeRushPractice, self.wantLiveGoonPractice, self.wantAimPractice, self.wantAimRightPractice, self.wantAimLeftPractice, self.wantAimAlternatePractice, self.wantGoonPractice)

    def setPracticeParams(self, practiceMode):

        # If we are setting a practice mode, we probably don't want the timer!
        if practiceMode is not None:
            self.__pauseTimer()

        # Get current state of requested mode before disabling all
        if practiceMode == self.RNG_MODE:
            currentState = self.wantRNGMode
        elif practiceMode == self.SAFE_RUSH_PRACTICE:
            currentState = self.wantSafeRushPractice
        elif practiceMode == self.LIVE_GOON_PRACTICE:
            currentState = self.wantLiveGoonPractice
        elif practiceMode == self.AIM_PRACTICE:
            currentState = self.wantAimPractice
        elif practiceMode == self.A_R_PRACTICE:
            currentState = self.wantAimRightPractice
        elif practiceMode == self.A_L_PRACTICE:
            currentState = self.wantAimLeftPractice
        elif practiceMode == self.A_ALT_PRACTICE:
            currentState = self.wantAimAlternatePractice
        elif practiceMode == self.GOON_PRACTICE:
            currentState = self.wantGoonPractice
        else:
            currentState = False

        # Disable all practice modes
        self.wantRNGMode = False
        self.wantSafeRushPractice = False
        self.wantLiveGoonPractice = False
        self.wantAimPractice = False
        self.wantAimRightPractice = False
        self.wantAimLeftPractice = False
        self.wantAimAlternatePractice = False
        self.wantGoonPractice = False

        # Disable all practice parameters
        self.wantOpeningModifications = False
        self.wantMaxSizeGoons = False
        self.wantStunning = False
        self.wantNoStunning = False
        self.wantFasterGoonSpawns = False
        self.wantAlwaysStunned = False

        # Toggle the requested mode to opposite of its previous state
        if practiceMode == self.RNG_MODE:
            self.wantRNGMode = not currentState
        elif practiceMode == self.SAFE_RUSH_PRACTICE:
            self.wantSafeRushPractice = not currentState
        elif practiceMode == self.LIVE_GOON_PRACTICE:
            self.wantLiveGoonPractice = not currentState
        elif practiceMode == self.AIM_PRACTICE:
            self.wantAimPractice = not currentState
        elif practiceMode == self.A_R_PRACTICE:
            self.wantAimRightPractice = not currentState
        elif practiceMode == self.A_L_PRACTICE:
            self.wantAimLeftPractice = not currentState
        elif practiceMode == self.A_ALT_PRACTICE:
            self.wantAimAlternatePractice = not currentState
        elif practiceMode == self.GOON_PRACTICE:  # New practice mode
            self.wantGoonPractice = not currentState

        # Enable the requested mode's params
        if self.wantRNGMode:
            self.wantOpeningModifications = True
            self.wantMaxSizeGoons = True
        elif self.wantSafeRushPractice:
            self.wantStunning = True
        elif self.wantLiveGoonPractice:
            self.wantNoStunning = True
            self.openingModificationsToonIndex = 0
            self.wantFasterGoonSpawns = True
        elif self.wantAimPractice or self.wantAimRightPractice or self.wantAimLeftPractice or self.wantAimAlternatePractice:
            self.wantAlwaysStunned = True
            self.setupAimMode()
        elif self.wantGoonPractice:  # New practice mode setup
            self.wantOpeningModifications = True
            self.wantAlwaysStunned = True
            self.setupGoonPracticeMode()

        # We probably want some sort of indicator so we know if someone has cheats enabled.
        # We can use a modifier with a really low heat value to display this, so we know we are in
        # some sort of "easy mode"
        self.checkCheatModifier()

    def checkCheatModifier(self):
        self.game.removeModifier(CraneLeagueGlobals.ModifierCFOCheatsEnabled)
        if self.cheatIsEnabled():
            self.game.applyModifier(CraneLeagueGlobals.ModifierCFOCheatsEnabled(tier=1), updateClient=True)

    def clearSafes(self):
        """Move all safes far away to clear the field"""
        for safe in self.game.safes:
            if safe.index != 0:  # Skip helmet safe
                safe.move(1000, 1000, 1000, 0)

    def setupAimMode(self):
        # Initial setup for aim mode - stun CFO and remove goons
        self.game.getBoss().stopHelmets()
        self.game.getBoss().b_setAttackCode(ToontownGlobals.BossCogDizzy)
        taskMgr.remove(self.game.uniqueName('NextGoon'))
        for goon in self.game.goons:
            goon.request('Off')
            goon.requestDelete()
        self.__pauseTimer()
        
        # Clear all safes from the field
        self.clearSafes()

    def __pauseTimer(self):
        self.notify.debug("Pausing timer")
        taskMgr.remove(self.game.uniqueName('times-up-task'))
        self.game.d_updateTimer()

    def handleSafeDropped(self, safe):
        if not (self.wantAimPractice or self.wantAimRightPractice or self.wantAimLeftPractice or self.wantAimAlternatePractice):
            return

        # Get the first toon's position
        players = self.game.getParticipantsNotSpectating()
        if len(players) == 0:
            return
        toon = players[0]

        # Find which crane the toon is controlling
        controlledCrane = None
        for crane in self.game.cranes:
            if crane.avId == toon.doId:
                controlledCrane = crane
                break

        if not controlledCrane:
            return  # Toon isn't controlling a crane

        # Get crane's position and heading from the predefined positions
        cranePos = CraneLeagueGlobals.ALL_CRANE_POSHPR[controlledCrane.index]
        craneX = cranePos[0]
        craneY = cranePos[1]
        craneH = cranePos[3]  # Index 3 is the H value in POSHPR
        
        if self.wantAimRightPractice or self.wantAimLeftPractice or self.wantAimAlternatePractice:
            # For alternate mode, randomly choose first direction then alternate
            if self.wantAimAlternatePractice and self.isFirstAlternate:
                self.alternateDirection = random.choice([True, False])
                self.isFirstAlternate = False
            elif self.wantAimAlternatePractice:
                self.alternateDirection = not self.alternateDirection

            # Convert heading to radians for math calculations
            # Add 90 because in Panda3D, 0 degrees points down +Y axis, and we want to point forward
            headingRadians = math.radians(craneH + 90)
            
            # Calculate unit vectors for forward and rightward directions
            forwardUnitX = math.cos(headingRadians)
            forwardUnitY = math.sin(headingRadians)
            rightwardUnitX = forwardUnitY  # Rotate 90 degrees clockwise
            rightwardUnitY = -forwardUnitX

            # Calculate progressive shift (2 to 25 units)
            # For AimLeft or alternating left, we negate the shift
            shiftAmount = self.game.progressValue(2, 25)
            if self.wantAimLeftPractice or (self.wantAimAlternatePractice and not self.alternateDirection):
                shiftAmount = -shiftAmount
            
            # Calculate base position:
            # 1. Start at crane position
            # 2. Add forward/backward offset based on forwardDistance (can be negative)
            # 3. Add rightward/leftward shift
            baseX = craneX + (forwardUnitX * self.forwardDistance) + (rightwardUnitX * shiftAmount)
            baseY = craneY + (forwardUnitY * self.forwardDistance) + (rightwardUnitY * shiftAmount)

            # For Aim modes, we always want to reposition a safe
            # Find any available safe that isn't the helmet
            for potentialSafe in self.game.safes:
                if potentialSafe.index != 0 and potentialSafe.state in ['Free', 'Initial']:
                    # Pass 0 as repositionDistance to ensure exact positioning, and 180 for heading
                    self.repositionSafe(potentialSafe, baseX, baseY, 0, 180)
                    break
            return

        # Original AIM_PRACTICE logic below
        repositionDistance = self.game.progressValue(8, 28)  # Start at 8 units, progress to 28 units

        # First count how many safes are already nearby (always check within 35 units)
        checkDistance = 35
        nearbySafes = set()  # Using a set for faster lookup
        for potentialSafe in self.game.safes:
            if potentialSafe.index != 0 and potentialSafe.state in ['Free', 'Initial']:  # Not the helmet safe
                safeX = potentialSafe.getPos().x
                safeY = potentialSafe.getPos().y
                distance = math.sqrt((craneX - safeX) ** 2 + (craneY - safeY) ** 2)
                if distance <= checkDistance:
                    nearbySafes.add(potentialSafe)

        # If we already have enough nearby safes, don't reposition any
        if len(nearbySafes) >= self.numSafesWanted:
            return

        # Find available safes (not grabbed, not dropped, not helmet, not already nearby)
        availableSafes = []
        for potentialSafe in self.game.safes:
            if (potentialSafe.index != 0 and  # Not the helmet safe
                    potentialSafe.state in ['Free', 'Initial'] and  # Only free or initial safes
                    potentialSafe != safe and  # Not the safe that was just dropped
                    potentialSafe not in nearbySafes):  # Not already nearby
                distance = math.sqrt((craneX - potentialSafe.getPos().x) ** 2 + (craneY - potentialSafe.getPos().y) ** 2)
                availableSafes.append((distance, potentialSafe))

        # Sort safes by distance (furthest first)
        availableSafes.sort(reverse=True)

        # Calculate how many safes we need to reposition
        safesNeeded = self.numSafesWanted - len(nearbySafes)
        safesToMove = availableSafes[:safesNeeded]  # Take only as many as we need

        # Reposition each safe
        for _, safeToMove in safesToMove:
            self.repositionSafe(safeToMove, craneX, craneY, repositionDistance)

    def checkSafePosition(self, x, y, safes):
        # Safe radius is approximately 4 units (collision sphere is about 8 units)
        safeRadius = 4.0
        for safe in safes:
            if safe.state not in ['Free', 'Initial']:
                continue
            safeX = safe.getPos().x
            safeY = safe.getPos().y
            distance = math.sqrt((x - safeX) ** 2 + (y - safeY) ** 2)
            if distance < (safeRadius * 2):  # Multiply by 2 to account for both safes' radii
                return False
        return True

    def repositionSafe(self, safe, toonX, toonY, nearbyDistance, heading=None):
        # Keep trying new angles until we find a position in bounds and not colliding
        for i in range(100):
            angle = random.random() * 2.0 * math.pi
            x = toonX + nearbyDistance * math.cos(angle)
            y = toonY + nearbyDistance * math.sin(angle)

            # First check if this position is within the octagonal bounds
            if not self.isLocationInBounds(x, y):
                continue

            # Now check if this position collides with any other safes
            if not self.checkSafePosition(x, y, self.game.safes):
                continue

            # Found a valid position!
            z = 0
            if safe.state == 'Initial':
                safe.demand('Free')
            safe.move(x, y, z, 180 if heading is not None else 360 * random.random())
            return

        # If we still can't find a valid position, place it very close to the toon
        nearbyDistance = 5  # Very close radius as last resort
        angle = random.random() * 2.0 * math.pi
        x = toonX + nearbyDistance * math.cos(angle)
        y = toonY + nearbyDistance * math.sin(angle)

        # Final position must be within the octagonal bounds
        if not self.isLocationInBounds(x, y):
            x = toonX
            y = toonY

        z = 0
        if safe.state == 'Initial':
            safe.demand('Free')
        safe.move(x, y, z, 180 if heading is not None else 360 * random.random())

    # Probably a better way to do this but o well
    # Checking each line of the octogon to see if the location is outside
    def isLocationInBounds(self, x, y):
        if x > 165.7:
            return False
        if x < 77.1:
            return False
        if y > -274.1:
            return False
        if y < -359.1:
            return False

        if y - 0.936455 * x > -374.901:
            return False
        if y + 0.973856 * x < -254.118:
            return False
        if y - 1.0283 * x < -496.79:
            return False
        if y + 0.884984 * x > -155.935:
            return False

        return True

    def setupGoonPracticeMode(self):
        # Initial setup for goon practice mode - stun CFO but keep goons spawning
        self.game.getBoss().stopHelmets()
        self.game.getBoss().b_setAttackCode(ToontownGlobals.BossCogDizzy)
        
        # Remove existing goons and their spawn task
        taskMgr.remove(self.game.uniqueName('NextGoon'))
        for goon in self.game.goons:
            goon.request('Off')
            goon.requestDelete()
        self.game.goons = []  # Clear the goon list
        
        # Pause the timer
        self.__pauseTimer()
        
        # Set up faster goon spawning (4 seconds)
        self.game.waitForNextGoon(4.0)  # This will start the goon spawn cycle
        
        # Make sure we're using the correct side for spawning
        self.wantOpeningModifications = True
        self.wantAlwaysStunned = True