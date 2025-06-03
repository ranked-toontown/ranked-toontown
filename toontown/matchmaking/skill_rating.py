from copy import deepcopy
from typing import Any

from direct.directnotify import DirectNotifyGlobal
from openskill.models import PlackettLuce, PlackettLuceRating

from toontown.matchmaking.player_skill_profile import PlayerSkillProfile, TeamSkillProfileCollection
from toontown.matchmaking.skill_rating_utils import interpolate_number, mu_to_skill_rating

BASE_SR_CHANGE = 20

# Define the model you want to use here.
# You can view the different models available here: https://openskill.me/en/stable/manual.html#picking-models
# You can also customize the inner workings on skill estimation, but the defaults are probably fine.
MODEL = PlackettLuce()
notify = DirectNotifyGlobal.directNotify.newCategory("OpenSkill")

class OpenSkillMatchDeltaResults:
    """
    Mirrors the effects of what changes were made to player ratings after a match was calculated.
    This can be used not only to determine SR changes, but also underlying mu/sigma changes as well.
    This should be something that is sent to the client upon a results screen so they see all the rank changes.
    """

    def __init__(self):

        # Maps player ID to a player skill profile. Keep in mind, that this profile actually stores deltas of values
        # and not the final values.
        self.players: dict[int, PlayerSkillProfile] = {}

    def get_player_results(self) -> dict[int, PlayerSkillProfile]:
        return self.players

    @classmethod
    def from_match(cls, match: "OpenSkillMatch"):
        """
        Construct an instance of this from a match object. Uses the data stored within the match to calculate data.
        """
        ret = OpenSkillMatchDeltaResults()

        # Loop through all the player data.
        for key, old_data in match.old_player_data.items():
            new_data = match.new_player_data[key]
            ret.players[key] = PlayerSkillProfile(
                old_data.identifier,
                old_data.key,
                # Use differences in values to construct the profile.
                new_data.mu - old_data.mu,
                new_data.sigma - old_data.sigma,
                new_data.skill_rating - old_data.skill_rating
            )

        return ret




class OpenSkillMatch:

    def __init__(self):

        # Represents skill profiles that don't get affected by any changes, so you can observe changes afterward.
        self.old_player_data: dict[int, PlayerSkillProfile] = {}
        # Represents current skill profiles, so you can easily query a single user's data.
        self.new_player_data: dict[int, PlayerSkillProfile] = {}
        self.teams: list[TeamSkillProfileCollection] = []

    def __store_player(self, player: PlayerSkillProfile):
        """
        Caches old and new player data to be used for comparisons after skill adjustment.
        """
        # Store the data so it can be retrieved by ID.
        self.new_player_data[player.identifier] = player

        # Store a copy of the data so it can be compared against.
        self.old_player_data[player.identifier] = deepcopy(player)

    def add_player(self, player: PlayerSkillProfile, score: int) -> TeamSkillProfileCollection:
        """
        Adds a player to this match. Under the hood, this method adds a player as if they were on a team alone.
        In a free for all setting, all players are considered to be on "their own team".
        If you choose to use this functionality, note that you need to use the returned team in order to set the winner.
        """
        team = TeamSkillProfileCollection()
        team.add_player(player, score)
        team.set_team_score(score)
        self.add_team(team)
        return team

    def add_team(self, team: TeamSkillProfileCollection):
        """
        Adds a team of players to this match. If you add players in this fashion, you do NOT need to call
        add_player().
        """
        self.teams.append(team)
        for player in team.as_list():
            self.__store_player(player)

    def get_team_ranking(self, team) -> tuple[int, int]:

        sorted_teams = sorted(self.teams, key=lambda t: t.get_team_score(), reverse=True)
        rank = 1
        point_value = sorted_teams[0].get_team_score()
        found_team = 1
        for t in sorted_teams:

            if point_value != t.get_team_score():
                point_value = t.get_team_score()
                rank += 1

            if t == team:
                found_team = rank

        return found_team, rank

    def adjust_ratings(self) -> OpenSkillMatchDeltaResults:
        """
        Adjusts all the ratings of the players/teams added to this match.
        Keep in mind that the first team/player you added is considered the winner of the match.
        """

        # Construct the low level OpenSkill "match", where it is a 2D list of teams with players.
        match: list[list[Any]] = []
        for team in self.teams:
            members = []
            for player in team.as_list():
                members.append(MODEL.rating(mu=player.mu, sigma=player.sigma, name=str(player.identifier)))
            match.append(members)

        # Adjust OpenSkill ratings.
        scores = [t.get_team_score() for t in self.teams]
        weights = [t.generate_weight_list() for t in self.teams]
        results = MODEL.rate(
            match,
            scores=scores,
            weights=weights,
        )

        notify.warning(f"Generated match with the following teams: {match}")
        notify.warning(f"the following scores were used to rate: {scores}")
        notify.warning(f"the following weights were used: {weights}")
        notify.warning(f"the following results were returned: {results}")

        # The results should match up 1-to-1 with our team layout. Adjust sigma and mu values according to OpenSkill.
        for teamIndex, team in enumerate(results):
            for memberIndex, member in enumerate(team):
                old_player = self.teams[teamIndex].as_list()[memberIndex]
                old_player.sigma = member.sigma
                old_player.mu = member.mu

        # Now, SR adjustment. SR is pretty artificial, and is meant to be a dopamine chaser.
        # SR should attempt to "equalize" on the player's mu rating, but it can be affected by a lot of things.
        # First give everyone the base SR adjustment of 20 for winning/losing. Note that this also scales for teams
        # who came in rankings that weren't last place if we are playing a multi team mode.
        # For example, 4 team mode means +20, +7, -7, -20
        sr_adjustments = {}
        for team in self.teams:
            rank, total_ranks = self.get_team_ranking(team)
            if total_ranks == 1:
                t = .5
            else:
                t = 1 -  (rank-1) / (total_ranks-1)
            base_sr = interpolate_number(-BASE_SR_CHANGE, BASE_SR_CHANGE, t)
            for player in team.as_list():
                sr_adjustments[player.identifier] = base_sr

        # Now we can apply modifiers for certain things.
        # First, the most important, we need to apply "catchup" SR to equalize. This has nothing to do with the match.
        for player in self.new_player_data.values():

            # If this person drew, don't even bother with this step.
            if sr_adjustments[player.identifier] == 0:
                continue

            mu_to_sr = mu_to_skill_rating(player.mu)
            # How big is the gap? Rate this from -400-400.
            gap = mu_to_sr - player.skill_rating
            # If gap is positive, that means they deserve higher SR, so we should apply a bonus.
            if gap > 0:
                sr_adjustments[player.identifier] += interpolate_number(0, 10, gap/500)
            # Gap is negative, we need to slow them down as they are getting inflated/boosted.
            else:
                sr_adjustments[player.identifier] -= interpolate_number(0, 10, gap/-500)

        # Todo: apply more modifiers, such as match mvp, underdog close game wins, penalize expected wins, etc.

        # Now apply the sr_adjustments!
        for player in self.new_player_data.values():
            player.skill_rating += sr_adjustments[player.identifier]

        # We can now return results!
        return OpenSkillMatchDeltaResults.from_match(self)
