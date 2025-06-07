from copy import deepcopy
from typing import Any

from direct.directnotify import DirectNotifyGlobal

from toontown.matchmaking.player_skill_profile import PlayerSkillProfile, TeamSkillProfileCollection
from toontown.matchmaking.skill_globals import MODEL, BASE_SR_CHANGE, RATING_CLASS
from toontown.matchmaking.skill_rating_modifier import SkillRatingModifier, HIDDEN_MMR_CONVERGENCE_MODIFIER, \
    ONE_V_ONE_WIN_EXPECTANCY_MODIFIER, GENERAL_WIN_EXPECTANCY_MODIFIER
from toontown.matchmaking.skill_rating_utils import interpolate_number, interpolate_float

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
                new_data.skill_rating - old_data.skill_rating,
                new_data.wins,
                new_data.games_played,
                new_data.placements_needed
            )

        return ret




class OpenSkillMatch:

    def __init__(self):

        # Represents skill profiles that don't get affected by any changes, so you can observe changes afterward.
        self.old_player_data: dict[int, PlayerSkillProfile] = {}
        # Represents current skill profiles, so you can easily query a single user's data.
        self.new_player_data: dict[int, PlayerSkillProfile] = {}
        self.teams: list[TeamSkillProfileCollection] = []
        self.ranks: list[int] = []

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

    def get_team_ranking(self, team: TeamSkillProfileCollection) -> tuple[int, int]:

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
        match: list[list[RATING_CLASS]] = self.generate_openskill_match()

        # Generate the rankings of all the teams so we can rate the match using it.
        self.ranks = []
        for team in self.teams:
            rank, _ = self.get_team_ranking(team)
            self.ranks.append(rank)

        # Adjust OpenSkill ratings.
        weights = [t.generate_weight_list() for t in self.teams]
        results = MODEL.rate(
            match,
            ranks=self.ranks,
            weights=weights,
        )

        notify.warning(f"Generated match with the following teams: {match}")
        notify.warning(f"the following ranks were used to rate: {self.ranks}")
        notify.warning(f"the following weights were used: {weights}")
        notify.warning(f"the following results were returned: {results}")

        # The results should match up 1-to-1 with our team layout. Adjust sigma and mu values according to OpenSkill.
        for teamIndex, team in enumerate(results):
            for memberIndex, member in enumerate(team):
                old_player = self.teams[teamIndex].as_list()[memberIndex]
                old_player.sigma = int(round(member.sigma))
                old_player.mu = int(round(member.mu))

        # Update games played for everyone involved. If it's the winning team, give them a win.
        for i, team in enumerate(self.teams):
            for player in team.as_list():
                player.games_played += 1
                player.placements_needed -= 1
                player.placements_needed = max(0, player.placements_needed)
                if self.ranks[i] == 1 and max(self.ranks) > 1:
                    player.wins += 1

        # Now, SR adjustment. SR is pretty artificial, and is meant to be a dopamine chaser.
        # SR should attempt to "equalize" on the player's mu rating, but it can be affected by a lot of things.
        # First give everyone the base SR adjustment of 20 for winning/losing. Note that this also scales for teams
        # who came in rankings that weren't last place if we are playing a multi team mode.
        # For example, 4 team mode means +20, +7, -7, -20
        sr_adjustments: dict[int, float] = {}
        for team in self.teams:
            rank, total_ranks = self.get_team_ranking(team)
            if total_ranks == 1:
                t = .5
            else:
                t = 1 -  (rank-1) / (total_ranks-1)
            sr = interpolate_float(-BASE_SR_CHANGE, BASE_SR_CHANGE, t)
            for player in team.as_list():
                sr_adjustments[player.identifier] = sr

        # Now we can apply modifiers for certain things.
        # Based on the context of the match, determine what modifiers we want to add.
        # We should always add hidden MMR convergence.
        modifiers: list[SkillRatingModifier] = [HIDDEN_MMR_CONVERGENCE_MODIFIER]

        # If this is a 1v1, we should add 1v1 win expectancy. Otherwise, use a more general tuned one.
        if len(self.teams) == 2 and all([len(t.players) == 1 for t in self.teams]):
            modifiers.append(ONE_V_ONE_WIN_EXPECTANCY_MODIFIER)
        else:
            modifiers.append(GENERAL_WIN_EXPECTANCY_MODIFIER)

        # todo: more modifiers!!!

        # Loop through every player. Calculate SR modifiers based on the context of the game.
        for player in self.old_player_data.values():
            for modifier in modifiers:
                # Overwrite SR value when modifier is applied.
                sr_adjustments[player.identifier] = modifier.apply(self, player.identifier, sr_adjustments[player.identifier])

        # Now that SR adjustments are fully calculated, actually apply them. Always round SR to use an integer as well.
        for player in self.new_player_data.values():
            sr_delta = sr_adjustments[player.identifier]
            sr_delta = int(round(sr_delta))
            player.skill_rating += sr_delta

        # We can now return results!
        return OpenSkillMatchDeltaResults.from_match(self)

    def get_player_team(self, player: int) -> TeamSkillProfileCollection | None:
        """
        Gets the team that this player is on. Player parameter is the player's ID.
        """
        for team in self.teams:
            if player in team.players:
                return team
        return None

    def did_player_win(self, player):
        """
        Checks if the given player won. If the game was a draw, or they weren't first place, returns False.
        Returns True if they came in first place and it wasn't a draw.
        """
        team = self.get_player_team(player)
        if team is None:
            return False

        rank, total_ranks = self.get_team_ranking(team)
        if total_ranks == 1:
            return False

        return rank <= 1

    def generate_openskill_match(self) -> list[list[RATING_CLASS]]:
        """
        Generates the structure of what OpenSkill expects. A list of teams, where each team is a list of players.
        """
        match: list[list[Any]] = []
        ranks = []
        for team in self.teams:
            members = []
            rank, _ = self.get_team_ranking(team)
            ranks.append(rank)
            for player in team.as_list():
                members.append(MODEL.rating(mu=player.mu, sigma=player.sigma, name=str(player.identifier)))
            match.append(members)
        return match

    def generate_rank_predictions(self) -> list[tuple[int, float]]:
        """
        Returns the result of OpenSkill's rank predictions for this match for every team.
        Returns a list of pairs of data. The first entry is the predicted rank, and the second entry is the probability
        of that rank for every team. For example, if a team has a predicted rank of 1 with a high probability, then
        they were expected to win this match by quite a large margin.
        """
        return MODEL.predict_rank(self.generate_openskill_match())

    def get_actual_rankings(self) -> list[int]:
        """
        Returns the rankings of each team according to the outcome of this match.
        The index of the team will match up to the index here.
        """
        return self.ranks
