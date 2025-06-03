from typing import Any

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobal import DistributedObjectGlobal

from toontown.matchmaking.skill_profile_keys import SkillProfileKey


class LeaderboardManager(DistributedObjectGlobal):
    notify = DirectNotifyGlobal.directNotify.newCategory('LeaderboardManager')
    neverDisable = 1

    def __init__(self, cr):
        DistributedObjectGlobal.__init__(self, cr)
        self.notify.info('LeaderboardManager initiated')
        self.__rankings_cache: dict[str, Any] = {}

    def getRankings(self, current_mode: SkillProfileKey, start_ranking: int, amount: int):

        # Do we have what we want cached?
        cached = self.__rankings_cache.get(current_mode.value, [])

        # Sort the records by ranking.
        cached.sort(key=lambda x: x[0])

        # Loop through every record we have cached and see if the ranking is what we want.
        results = []

        desired = start_ranking
        for record in cached:
            if desired == record[0]:
                results.append(record)
                desired += 1

        # If we didn't have what we wanted, contact UD.
        if len(results) != amount:
            self.d_requestRankings(current_mode.value, start_ranking, amount)

        # Return what we did end up finding.
        return results

    def clearRankingsCache(self):
        self.__rankings_cache.clear()

    def d_requestRankings(self, key: str, start: int, amount: int):
        """
        Sends a request to the UD. The UD should respond with leaderboard results.
        """
        self.sendUpdate('requestRankingsClientToUd', [key, start, amount])

    def requestRankingsResponse(self, key, results: list[Any]):
        """
        Called from the UD after a requestRankings call was invoked. Updates the internal cache of leaderboard ranks.
        """

        # Cache what we received.
        current = self.__rankings_cache.get(key, [])
        for result in results:
            current.append(result)
        self.__rankings_cache[key] = current

        # Send an event so that the page can hook into this if needed.
        messenger.send('leaderboard-ranking-response', [key, results])
