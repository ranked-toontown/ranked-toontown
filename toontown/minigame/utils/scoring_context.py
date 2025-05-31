from toontown.matchmaking.skill_rating_utils import interpolate_number


class RoundContext:
    """
    Simply stores player scores for a round.
    """
    def __init__(self):
        self._player_id_to_score: dict[int, int] = {}
        self._winners: list[int] = []

    def add_score(self, player_id: int, score: int):
        """
        Adds to the score for this player. If they aren't present, they will be added.
        """
        self._player_id_to_score[player_id] = self.get_score(player_id) + score

    def get_score(self, player_id: int) -> int:
        """
        Gets the score of the given player ID. Returns 0 if they are not present.
        """
        return self._player_id_to_score.get(player_id, 0)

    def get_scores(self, player_ids: list[int]) -> int:
        """
        Return a sum of scores for the given players. Can be used to get the score of a team.
        """
        total = 0
        for player_id in player_ids:
            total += self.get_score(player_id)

        return total

    def get_all_scores(self) -> dict[int, int]:
        """
        Returns the scores for every player being tracked. Maps player ID -> score.
        """
        return self._player_id_to_score

    def set_winners(self, player_ids: list[int]):
        """
        Set who won this round.
        """
        self._winners = list(player_ids)

    def get_winners(self) -> list[int]:
        """
        Get who won this round. If this is empty, either nobody won or nobody has won yet.
        """
        return self._winners

    def get_losers(self) -> list[int]:
        """
        Get who participated in this round, but didn't win.
        """
        return [p for p in self._player_id_to_score.keys() if p not in self._winners]

    def reset_scores(self):
        """
        Resets the scores for this round as if it just started.
        """
        self._player_id_to_score.clear()


class ScoringContext:
    """
    Stores RoundContext instances, that can be used to extract data for certain points in a context.
    """

    def __init__(self):
        self._round_to_context: dict[int, RoundContext] = {}

    def get_round(self, _round: int) -> RoundContext:
        """
        Gets the RoundContext for a certain round number. If it doesn't exist, a new one will be tracked and returned.
        """
        ctx = self._round_to_context.get(_round)
        if ctx is None:
            ctx = RoundContext()
            self._round_to_context[_round] = ctx

        return ctx

    def set_winners(self, _round: int, winners: list[int]) -> RoundContext:
        """
        Sets the winners of a certain round.
        """
        ctx = self.get_round(_round)
        ctx.set_winners(winners)
        return ctx

    def get_total_points(self) -> dict[int, int]:
        """
        Calculates the total amount of points scored for the ENTIRE GAME, per player.
        {player_id: points}
        """
        ret = {}

        # Loop through every round, then every player in that round.
        for _round in self._round_to_context.values():
            for player_id, score in _round.get_all_scores().items():
                pts = ret.get(player_id, 0) + score
                ret[player_id] = pts

        return ret

    def get_round_wins(self) -> dict[int, int]:
        """
        Calculates the amount of round wins every player has. Keep in mind, if you are using teams, the players on the
        same team probably have the same amount of round wins.
        """
        ret = {}

        # Loop through every round, and get every winner in that round and add one.
        for _round in self._round_to_context.values():
            for winner in _round.get_winners():
                wins = ret.get(winner, 0) + 1
                ret[winner] = wins

        return ret

    def generate_score_rankings(self) -> dict[int, int]:
        """
        Generates a total "score" for every player. Keep in mind since that this is used for winner determination in
        rank calculations, "winning a round" is considered the most amount of points you can win in a round.
        This means the winners of the match will all have the maximum amount of points.
        """
        scores = {}

        # Loop through every round.
        for _round in self._round_to_context.values():

            highest_score = max(_round.get_all_scores().values())

            # The winners get max point weight.
            for winner in _round.get_winners():
                scores[winner] = scores.get(winner, 0) + 100

            # The losers get a weighted score of 0-99 in relation to the highest score.
            for loser in _round.get_losers():
                score = interpolate_number(0, 99, _round.get_score(loser) / highest_score)
                scores[loser] = scores.get(loser, 0) + score

        return scores


    def generate_rankings(self) -> dict[int, int]:
        """
        Based on the scores in this entire context (including multiple rounds), generate a "ranking" to put the players.
        Round wins are favorable, but score within individual rounds can affect rankings.
        Returns a mapped dictionary of player IDs and their ranking. (1st place, 2nd place, etc.)
        Keep in mind that ties can occur.
        Example:
        Input: {'A': 100, 'B': 200, 'C': 100}
        Output: {'B': 1, 'A': 2, 'C': 2}
        """

        scores = self.generate_score_rankings()

        # Sort items by score descending, keeping original player IDs
        sorted_items = sorted(scores.items(), key=lambda x: -x[1])

        ranks = {}
        current_rank = 1
        prev_score = None

        for i, (player_id, score) in enumerate(sorted_items):
            if score != prev_score:
                # New score group starts here
                current_rank = i + 1
                prev_score = score
            ranks[player_id] = current_rank

        return ranks