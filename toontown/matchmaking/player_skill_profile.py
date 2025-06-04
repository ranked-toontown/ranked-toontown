import dataclasses
from typing import Any

STARTING_RATING = 1000


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