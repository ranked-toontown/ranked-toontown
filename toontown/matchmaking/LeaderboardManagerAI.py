from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobalAI import DistributedObjectGlobalAI

from toontown.matchmaking.player_skill_profile import PlayerSkillProfile


class LeaderboardManagerAI(DistributedObjectGlobalAI):
    notify = DirectNotifyGlobal.directNotify.newCategory("LeaderboardManagerAI")

    def __init__(self, air):
        DistributedObjectGlobalAI.__init__(self, air)
        self.air = air
        self.notify.info(f"booting up")

    def reportMatchToUd(self, results: list[PlayerSkillProfile], nameMap: list[list]):
        """
        Alerts the UD that a match concluded to keep leaderboard up to date.
        The nameMap parameter is temporary (maybe), it just saves us a database call on the UD since we have to
        also associate names with players using the leaderboard.
        """
        self.notify.info('Sending ranked results to UD...')
        self.sendUpdate('handleRankedMatchResultsAiToUd', [[profile.to_astron() for profile in results], nameMap])