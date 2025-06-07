from __future__ import annotations

import typing

from toontown.matchmaking.skill_rating_utils import interpolate_float

if typing.TYPE_CHECKING:
    from toontown.matchmaking.skill_rating import OpenSkillMatch


class SkillRatingModifier:
    """
    Base class for a skill rating modifier to use in skill rating adjustments.
    Extend this class to do define adjustments to make to players based on the context of a match.
    """
    def apply(self, ctx: OpenSkillMatch, player: int, base_sr: float) -> float:
        return base_sr


class HiddenMmrConvergenceModifier(SkillRatingModifier):
    """
    Converges the player's skill rating adjustment to swing towards their hidden MMR before the match started.
    If a player has a higher hidden MMR than their skill rating, it should have higher gains/lower losses and vice versa.
    """

    def apply(self, ctx: OpenSkillMatch, player: int, base_sr: float) -> float:

        data = ctx.old_player_data.get(player)
        if data is None:
            return base_sr

        gap = data.mu - data.skill_rating
        t = min(abs(gap) / 500, 1.0)  # Clamp to 0–1

        is_winner = base_sr > 0

        # Determine direction of interpolation
        # If player is behind (gap > 0), inflate rewards and reduce penalties
        # If player is ahead (gap < 0), reduce rewards and inflate penalties
        if (is_winner and gap > 0) or (not is_winner and gap < 0):
            multiplier = interpolate_float(1.0, 1.5, t)
        else:
            multiplier = interpolate_float(1.0, 0.5, t)

        return base_sr * multiplier


class OneOnOneWinExpectancyModifier(SkillRatingModifier):
    """
    Adjusts the player's skill rating based on the expected result of the match explicitly 1v1 setting.
    If the player was expected to win by a large margin and won, then they should be awarded less SR.
    If the player was expected to win by a large margin and lost, they should lose even more SR.
    If the player was expected to lose and lost, they shouldn't lose as much SR.
    If the player was expected to lose and won, they should be awarded even more SR.
    """
    def apply(self, ctx: OpenSkillMatch, player: int, base_sr: float) -> float:

        # Only apply in strict 1v1 matches
        if len(ctx.teams) != 2 or any(len(t.players) != 1 for t in ctx.teams):
            return base_sr

        # Identify this player's team and opponent's team.
        team = ctx.get_player_team(player)
        if team is None:
            return base_sr

        # Data retrieval. Retrieve our data and our opponent's data.
        opponent_team = [t for t in ctx.teams if t != team][0]
        opponent = list(opponent_team.players.values())[0]
        player_data = ctx.old_player_data[player]
        opponent_data = ctx.old_player_data[opponent.identifier]

        # Compute chance we had to win. Anywhere from ~0%-~100%, determined by OpenSkill. Balanced match = 50%.
        win_chance = player_data.calculate_win_prediction(opponent_data)
        is_win = base_sr > 0

        # t = how "surprising" the result was (higher means bigger upset)
        t = 1 - win_chance if is_win else win_chance

        sr_multiplier = interpolate_float(0.4, 1.6, t)
        return base_sr * sr_multiplier


class GeneralWinExpectancyModifier(SkillRatingModifier):
    """
    Adjusts SR based on how well a player performed relative to their expected placement.
    High MMR players who place low should be punished, and low MMR players who place high should be rewarded.
    """

    def apply(self, ctx: OpenSkillMatch, player: int, base_sr: float) -> float:

        if len(ctx.teams) < 2:
            return base_sr

        # Get predicted ranks with confidence and actual ranks
        rank_predictions = ctx.generate_rank_predictions()  # [(predicted_rank, probability)]
        actual_ranks = ctx.get_actual_rankings()

        # Get player's team and ranks
        team = ctx.get_player_team(player)
        if team is None:
            return base_sr

        team_index = ctx.teams.index(team)

        expected_rank, confidence = rank_predictions[team_index]
        actual_rank = actual_ranks[team_index]

        # Determine rank delta and normalize
        total_teams = len(ctx.teams)
        rank_delta = expected_rank - actual_rank  # Positive = overperformance
        normalized_delta = rank_delta / (total_teams - 1)  # Range ~[-1, 1]

        # Scale SR modifier from 0.5x to 1.5x
        base_multiplier = interpolate_float(0.5, 1.5, (normalized_delta + 1) / 2)

        # Confidence weighting (0.0–1.0): shrink bonus/penalty if model wasn't confident
        confidence_weight = interpolate_float(0.3, 1.0, confidence)

        # Final multiplier scales proportionally to model certainty
        final_multiplier = 1 + ((base_multiplier - 1) * confidence_weight)

        return base_sr * final_multiplier


# Define one instance for each modifier as a singleton. There's no state attached to modifiers so no point on
# creating new instances over and over.
HIDDEN_MMR_CONVERGENCE_MODIFIER = HiddenMmrConvergenceModifier()
ONE_V_ONE_WIN_EXPECTANCY_MODIFIER = OneOnOneWinExpectancyModifier()
GENERAL_WIN_EXPECTANCY_MODIFIER = GeneralWinExpectancyModifier()