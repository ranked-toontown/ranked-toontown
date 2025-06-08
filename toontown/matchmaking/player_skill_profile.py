from __future__ import annotations

import dataclasses
from typing import Any, ClassVar

from toontown.matchmaking.skill_globals import MODEL, RATING_CLASS, STARTING_RATING, STARTING_UNCERTAINTY, \
    ZERO_SUM_MODEL, MODEL_CLASS
from toontown.matchmaking.skill_profile_keys import SkillProfileKey
from toontown.matchmaking.zero_sum_elo_model import ZeroSumEloModel


@dataclasses.dataclass
class PlayerSkillProfile:
    """
    A data storage container that has information about a player's skill that is necessary for adjusting
    their OpenSkill rating.
    """
    identifier: int  # A unique identifier to retrieve this profile from. Should be toon ID.
    key: str  # The "key" of this profile. Used to associate it with a gamemode or activity.
    mu: int  # The estimation of the player's skill. Used for OpenSkill. Synonymous with "hidden MMR".
    sigma: int  # The confidence of the player's skill. Used for OpenSkill.
    skill_rating: int  # The front facing "SR" players see on their profiles. Directly mapped to rank.
    wins: int  # The amount of wins in this category.
    games_played: int  # The amount of total games played in this category.
    placements_needed: int  # The amount of placements needed in order to get a rank to display.

    def _model(self) -> MODEL_CLASS | ZeroSumEloModel:
        """
        Gets the model to use for this profile.
        """
        profile_type = SkillProfileKey.from_value(self.key)
        if profile_type is None:
            return MODEL

        return profile_type.get_model()

    def calculate_win_prediction(self, other: PlayerSkillProfile) -> float:
        """
        Calculate the percentage that this player will win against another. Can be used as a match quality metric.
        In skill based matchmaking, we want the chance of a win as close to 50/50 as possible.
        """
        return self._model().predict_win([[self.to_openskill_rating()], [other.to_openskill_rating()]])[0]

    def to_openskill_rating(self) -> RATING_CLASS:
        """
        Converts this skill profile into an OpenSkill rating to be used with OpenSkill methods.
        """
        return self._model().rating(mu=self.mu, sigma=self.sigma, name=str(self.identifier))

    def to_astron(self) -> list[Any]:
        """
        Converts this instance to an astron struct.
        """
        return [self.identifier, self.key, self.mu, self.sigma, self.skill_rating, self.wins, self.games_played, self.placements_needed]

    @classmethod
    def from_astron(cls, args: list[Any]):
        """
        Converts the low level astron struct to a proper SkillProfile instance.
        Identifier needs to be provided manually however, as astron does not store it. (Toon ID)
        """
        return cls(*args)

    @classmethod
    def create_fresh(cls, avId: int, key: str):
        """
        Creates a fresh skill profile. Call this if you find that a player is new!
        """

        # Resolve a model override for the profile key.
        key_inst = SkillProfileKey.from_value(key)
        model = MODEL
        if key_inst is not None:
            model = key_inst.get_model()

        rating = model.rating(mu=STARTING_RATING, sigma=STARTING_UNCERTAINTY, name=str(avId))
        return cls(
            identifier=avId,
            key=key,
            mu=int(rating.mu),
            sigma=int(rating.sigma),
            skill_rating=STARTING_RATING,
            wins=0,
            games_played=0,
            placements_needed=10
        )


class TeamSkillProfileCollection:
    """
    A data storage container that holds multiple player skill profiles said to be "on the same team", with a score
    they can be rated against.
    """

    def __init__(self):
        self.players: dict[int, PlayerSkillProfile] = {}
        self._indexed: list[PlayerSkillProfile] = []
        self.points: dict[int, int] = {}
        self.team_score = 0

    def add_player(self, player: PlayerSkillProfile, points: int):
        self.players[player.identifier] = player
        self._indexed.append(player)
        self.points[player.identifier] = points

    def as_list(self) -> list[PlayerSkillProfile]:
        return self._indexed

    def get_player_points(self) -> dict[int, int]:
        return self.points

    def get_total_player_points(self) -> int:
        return sum(self.points.values())

    def set_team_score(self, score: int):
        self.team_score = score

    def get_team_score(self) -> int:
        """
        Returns the team score. Keep in mind this is the team score that determines the result of the match, not
        individual player performance. Use player points for player performance.
        """
        return self.team_score

    def generate_weight_list(self) -> list[float]:
        """
        Generates a "weight map", representing the effectiveness of this player's contributions to the team.
        A higher weight represents more contribution to the team's performance.
        """
        # Maybe we want to tweak this later, but for now we just use scores.
        return [max(0, self.points[player_id]) for player_id in self.players.keys()]