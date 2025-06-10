from __future__ import annotations

import time
import typing

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectAI import DistributedObjectAI
from direct.distributed.DistributedObjectGlobalAI import DistributedObjectGlobalAI
from direct.task import Task

from toontown.groups.DistributedGroupManagerAI import DistributedGroupManagerAI
from toontown.matchmaking.player_skill_profile import STARTING_RATING
from toontown.matchmaking.skill_profile_keys import SkillProfileKey
from toontown.minigame.MinigameCreatorAI import GeneratedMinigame
from toontown.toonbase import ToontownGlobals

if typing.TYPE_CHECKING:
    from toontown.ai.ToontownAIRepository import ToontownAIRepository
    from toontown.toon.DistributedToonAI import DistributedToonAI

class MatchmakingPlayer:
    """
    Wrapper class that contains a DistributedToonAI instance as well as additional information to aid in the
    queue process. This is so we can keep track of things like wait time, OpenSkill matching softness, etc.
    """

    STARTING_SKILL_RANGE = 250

    def __init__(self, avatar: DistributedToonAI):
        self.avatar: DistributedToonAI = avatar

        # The allowed range of players that are allowed to match with us.
        self.skill_range = MatchmakingPlayer.STARTING_SKILL_RANGE

        # How long we have been waiting for a match.
        self.started_queue_at: float = time.time()

    def get_elapsed_queue_time(self) -> float:
        """
        Get the elapsed queue time in seconds.
        """
        return time.time() - self.started_queue_at

    def get_skill(self, key: str) -> int:
        """
        Retrieves the hidden MMR of this player for a given category.
        """
        profile = self.avatar.getSkillProfile(key)
        if profile is None:
            return STARTING_RATING

        return profile.mu

    def get_skill_disparity(self, other: MatchmakingPlayer, key: str) -> int:
        """
        Returns the difference in skill between us and another player. Will always be a positive integer to
        represent the "gap" in skill.
        """
        return abs(self.get_skill(key) - other.get_skill(key))

    def can_match_against(self, other: MatchmakingPlayer, key: str) -> bool:
        """
        Checks if we can match against the opponent. In order for that to be the case, our acceptable range must
        be permissive of the skill disparity for both players.
        """
        disparity = self.get_skill_disparity(other, key)
        if disparity <= self.skill_range and disparity <= other.skill_range:
            return True

        return False

    def determine_match_quality(self, otherPlayer: MatchmakingPlayer, key: str) -> float:
        """
        Match quality is determined by how "close" of a match the two players should have.
        There are many ways to come to a conclusion for this, but for a 1v1 we simply just want to know how
        close these players are in terms of having a 50/50 win chance. We can calculate this pretty easy by
        taking the difference in their win chance, and scaling it from 0->100. The lower the difference,
        the better the matchup is. (return 100 if win chance is 50/50)
        """
        our_skill = self.avatar.getOrCreateSkillProfile(key)
        other_skill = otherPlayer.avatar.getOrCreateSkillProfile(key)
        win_prediction = our_skill.calculate_win_prediction(other_skill)
        return (1 - abs(win_prediction - 0.5) * 2) * 100


class DistributedMatchmakerAI(DistributedObjectGlobalAI):
    """
    The main matchmaking logic for pairing up players and sending them to an activity.
    This is currently a prototype, and is planned to have much smarter functionality later on.
    For now, we just want a primitive system to match players together in a 1v1 scenario.
    """

    Notify = DirectNotifyGlobal.directNotify.newCategory('DistributedMatchmakerAI')

    # How often in seconds should we run the matchmaking check? Lower number = check queue more often. (seconds)
    MATCHMAKING_AGGRESSIVENESS = 5

    def __init__(self, air: ToontownAIRepository):
        DistributedObjectAI.__init__(self, air)
        self.air: ToontownAIRepository = air

        # The queue of players who are currently trying to find a match.
        self.profile_key: SkillProfileKey = SkillProfileKey.CRANING_SOLOS
        self.queue: list[MatchmakingPlayer] = []

    def getNumPlayersInQueue(self) -> int:
        return len(self.queue)

    def announceGenerate(self):
        super().announceGenerate()
        self.Notify.debug(f"Generating!")

        # Listen for toon logouts.
        self.accept('avatarExited', self.__handleUnexpectedExit)

        # Start the matchmaking task.
        taskMgr.add(self.__matching_algorithm, self.uniqueName('matchmake_algorithm'))
        taskMgr.add(self.__queue_information_update, self.uniqueName('queue_information_update'))

    def delete(self):
        super().delete()
        self.queue.clear()
        self.ignoreAll()
        taskMgr.remove(self.uniqueName('matchmake_algorithm'))
        taskMgr.remove(self.uniqueName('queue_information_update'))
        self.Notify.debug(f"Deleting")

    def isPlayerInQueue(self, av: DistributedToonAI) -> bool:
        for p in self.queue:
            if p.avatar.getDoId() == av.getDoId():
                return True

        return False

    def addPlayerToQueue(self, av: DistributedToonAI) -> bool:
        """
        Attempts to add the player to the queue. Returns True if they were successfully added, False otherwise.
        """
        if self.isPlayerInQueue(av):
            self.Notify.debug(f"Player {av.getName()}-{av.getDoId()} has been denied from the queue. They're already in it.")
            return False

        self.Notify.debug(f"Player {av.getName()}-{av.getDoId()} has been added to queue.")
        self.queue.append(MatchmakingPlayer(av))

        _len = len(self.queue)
        self.d_setMatchmakingStatus(av.getDoId(), _len, _len)
        return True

    def removePlayerFromQueue(self, av: DistributedToonAI) -> bool:
        found = False
        for p in list(self.queue):
            if p.avatar.getDoId() == av.getDoId():
                self.queue.remove(p)
                found = True
        self.d_setMatchmakingStatus(av.getDoId(), 0, 0)
        return found

    def __isPlayerInGroup(self, av: DistributedToonAI) -> bool:
        for groupManager in self.air.doFindAllInstances(DistributedGroupManagerAI):
            group = groupManager.getGroup(av)
            if group is not None:
                return True
        return False

    """
    Astron methods
    """

    def requestQueueState(self, flag: bool):
        """
        Called from clients when they wish to join/leave the queue.
        """
        avId = self.air.getAvatarIdFromSender()
        av = self.air.getDo(avId)
        if av is None:
            return

        if not flag:
            removed = self.removePlayerFromQueue(av)
            if removed:
                av.d_setSystemMessage(0, "Removed you from the queue!")
        else:

            if self.__isPlayerInGroup(av):
                av.d_setSystemMessage(0, "You cannot join the queue if you are in a group!")
                return

            added = self.addPlayerToQueue(av)
            if added:
                av.d_setSystemMessage(0, "Now queueing up!")

    def d_setMatchmakingStatus(self, avId: int, position: int, total: int):
        self.sendUpdateToAvatarId(avId, 'setMatchmakingStatus', [position, total])

    def d_setMinigameZone(self, avId, minigame: GeneratedMinigame):
        self.sendUpdateToAvatarId(avId, 'setMinigameZone', [minigame.zone, minigame.gameId])

    """
    Private util methods
    """

    def __handleUnexpectedExit(self, toon: DistributedToonAI):
        """
        Called when a toon logs out.
        """

        found = self.removePlayerFromQueue(toon)
        if found:
            self.Notify.debug(f"Removing {toon.getName()} from the queue if they were in it since they logged out.")

    def __send_players_to_match(self, matchup: tuple[MatchmakingPlayer, MatchmakingPlayer]) -> None:
        """
        Sends a matchup to their match.
        """

        # Create a minigame instance just like the group manager does. We are doing it almost no different.
        minigame: GeneratedMinigame = self.air.minigameMgr.createMinigame(
            [player.avatar.getDoId() for player in matchup],
            self.zoneId,
            desiredNextGame=ToontownGlobals.CraneGameId,
            hostId=None
        )

        # Send the players to the zone that are playing this match.
        for player in matchup:
            self.d_setMinigameZone(player.avatar.getDoId(), minigame)
            self.d_setMatchmakingStatus(player.avatar.getDoId(), 0, 0)

    def __matching_algorithm(self, task: Task.Task) -> int:
        """
        The internal matchmaking algorithm that runs over and over and attempts to match players together.
        This should only be instantiated by a task when the matchmaker boots up, and will consistently keep
        repeating.
        """
        task.delayTime = DistributedMatchmakerAI.MATCHMAKING_AGGRESSIVENESS

        # Nobody queueing? Don't do anything this run.
        if self.getNumPlayersInQueue() <= 0:
            return Task.again

        self.Notify.debug(f"Running matchmaking algorithm. Next run is in {task.delayTime} seconds. There are {len(self.queue)} people queued.")

        # Keep a list of matchups we are sending to play a game.
        matchups: list[tuple[MatchmakingPlayer, MatchmakingPlayer]] = []
        _players_matched: set[int] = set() # A flat set of players that have been matched up. Helps keep the code fast for lookups.

        # Loop in order from the start to the end. Check if two players meet each other's criteria.
        for i, player in enumerate(self.queue):

            if len(self.queue) <= 1:
                break

            # If this player was already matched up with someone previously, skip them.
            if player.avatar.getDoId() in _players_matched:
                continue

            # This player needs a match. Try and find one.
            matchup: MatchmakingPlayer | None = None
            best_match_quality: float = 0
            for otherPlayer in self.queue[i+1:]:

                # If this other player has already found a match, skip them.
                if otherPlayer.avatar.getDoId() in _players_matched:
                    continue

                # Can these players play against each other? And is it a higher quality match?
                allowed_to_match = player.can_match_against(otherPlayer, self.profile_key.value)
                this_match_quality = player.determine_match_quality(otherPlayer, self.profile_key.value)
                if allowed_to_match and this_match_quality > best_match_quality:
                    matchup = otherPlayer
                    best_match_quality = this_match_quality


            # Did we find a match? If not, skip and try again later.
            if matchup is None:
                continue

            # We found one. Add the matchup and update required variables for future checks.
            matchups.append((player, matchup))
            _players_matched.add(player.avatar.getDoId())
            _players_matched.add(matchup.avatar.getDoId())

        # Loop through the matchups. Remove them from the queue, and send them to their match.
        self.Notify.debug(f'Found {len(matchups)} matchups this run. Sending them to their game.')
        for pair in matchups:
            self.__send_players_to_match(pair)
            for player in pair:
                if player in self.queue:
                    self.queue.remove(player)

        # For everyone still in the queue, gradually increase their acceptable match range.
        for player in self.queue:
            player.skill_range += 10
            self.Notify.debug(f"{player.avatar.getName()} now has an MMR tolerance of {player.skill_range}.")

        return Task.again


    def __queue_information_update(self, task: Task.Task):
        """
        Loops every so often to keep everyone in queue synced with information about the queue.
        """
        task.delayTime = 3
        total = len(self.queue)
        for index, player in enumerate(self.queue):
            self.d_setMatchmakingStatus(player.avatar.getDoId(), index+1, total)
        return task.again
