import dataclasses
from typing import List, Optional

from direct.directnotify import DirectNotifyGlobal


@dataclasses.dataclass
class ZeroSumEloRating:
    mu: float = 1000
    sigma: float = 0  # Not used in this model, but present to ensure OpenSkill compatibility.
    name: str = '0'


class ZeroSumEloModel:
    """
    A custom ranking model that uses the classic zero-sum ELO model, and mimics the usage of OpenSkill's models so
    we can use both at the same time.
    """

    Notify = DirectNotifyGlobal.directNotify.newCategory("ZeroSumEloModel")

    def __init__(self, k_factor: float = 32, max_elo_discrepancy: int = 400):
        """
        Initialize the zero-sum elo model. Optionally, you can specify a custom K-factor to use for ELO swings.
        In simple terms, the K-factor is the maximum amount of hidden MMR you can gain or lose in a match.
        You can also tweak the elo discrepancy for maximum elo swings.
        In simple terms, if it is set to 400 and a 2000 rated player loses to a 1600 rated player, they lose the full
        amount of K-factor in terms of ELO for the winner to gain.
        """
        self.k_factor = k_factor
        self.skill_discrepancy: int = max_elo_discrepancy

    def rating(self, mu: float, sigma: float, name: str) -> ZeroSumEloRating:
        """
        Creates a rating instance.
        """
        return ZeroSumEloRating(mu=mu, sigma=0, name=name)

    def predict_win(self, teams: List[List[ZeroSumEloRating]]) -> list[float]:
        """
        Provides the probability of each player being able to win.
        """
        p1 = teams[0][0]
        p2 = teams[1][0]
        p1_chance = 1.0 / (1.0 + pow(10, ((p2.mu - p1.mu) / self.skill_discrepancy)))
        return [p1_chance, 1-p1_chance]

    def predict_rank(self, teams: List[List[ZeroSumEloRating]]) -> list[tuple[int, float]]:
        """
        Provides the predictions for how this match should go.
        """

        # This is actually pretty simple in a 1v1 context. Calculate the chance that p1 wins.
        p1_win_chance, p2_win_chance = self.predict_win(teams)

        # If they have a 50/50 chance, it's a tie. This means they have equivalent elo.
        if p1_win_chance == p2_win_chance:
            return [(1, .5), (1, .5)]

        # If p1 had a >50% chance, we predict they win with that probability, with p2 having a probability of the complement.
        if p1_win_chance > .5:
            return [(1, p1_win_chance), (2, p2_win_chance)]

        # Inverse if p2 has a bigger chance to win.
        return [(2, p1_win_chance), (1, p2_win_chance)]

    def rate(
            self,
            teams: List[List[ZeroSumEloRating]],
            ranks: Optional[List[float]] = None,
            **kwargs
    ) -> List[List[ZeroSumEloRating]]:
        """
        Directly mirrors OpenSkill's rate() function. A lot of these parameters don't do anything, but exist
        for the purpose of working alongside OpenSkill's elo model. You MUST use only the teams and ranks parameters
        to modify any behavior of this function.
        """
        self.Notify.debug(f"Calling rate() with teams: {teams}, ranks: {ranks}")
        # First, do some sanity checking. We can only perform zero-sum in 1v1 contexts. This is a severe developer
        # error if we call this function without first verifying it is a 1v1.
        if len(teams) != 2 or any(len(t) != 1 for t in teams):
            raise RuntimeError(f"Tried to perform 1v1 Zero-Sum ELO rating in a non 1v1 context! "
                               f"This is a developer error. Please check that the context of "
                               f"the match is a 1v1 before using this model. Team config: {teams}")

        # First, ensure that ranks was given to us. If it wasn't, we assume the first player won.
        if ranks is None:
            ranks = [1, 2]

        # Second, verify we were given either: [1, 1] (tie), [1, 2] player 1 won, [2, 1] player 2 won.
        if 1 not in ranks:
            raise RuntimeError(f"Invalid ranks provided! Someone MUST be in 1st place. Got: {ranks}")

        if any(place < 1 or place > 2 for place in ranks):
            raise RuntimeError(f"Invalid ranks provided! Detected non 1st or 2nd placement: {ranks}")

        # Extract player 1 and player 2.
        p1 = teams[0][0]
        p2 = teams[1][0]

        # Create new models that reflect these players. We only want to modify these so we can retain old data.
        p1_new = ZeroSumEloRating(mu=p1.mu, name=p1.name)
        p2_new = ZeroSumEloRating(mu=p2.mu, name=p2.name)

        # Run some predictions. We use these in our adjustment formula.
        p1_prediction, p2_prediction = self.predict_win([[p1], [p2]])

        # What actually happened? 1.0 indicates a win, 0 indicates a loss.
        p1_result = 1.0 if ranks[0] == 1 else 0.0
        p2_result = 1.0 if ranks[1] == 1 else 0.0

        # What about a draw? This means the result is 0.5
        if ranks == [1, 1]:
            p1_result = p2_result = 0.5

        # We now have the predictions and the results. We can adjust ratings.
        p1_new.mu = p1.mu + self.k_factor * (p1_result - p1_prediction)
        p2_new.mu = p2.mu + self.k_factor * (p2_result - p2_prediction)
        results = [[p1_new], [p2_new]]
        self.Notify.debug(f"Returning results from rate() -- old={teams} {results}")

        # Return the results matching the same format it was passed in.
        return results
