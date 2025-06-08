from __future__ import annotations
from enum import Enum

from toontown.matchmaking.skill_globals import MODEL_CLASS, ZERO_SUM_MODEL, MODEL
from toontown.matchmaking.zero_sum_elo_model import ZeroSumEloModel


class SkillProfileKey(Enum):
    MINIGAMES = "minigames"
    CRANING_SOLOS = "1v1_crane"
    CRANING_FFA = "craning"

    @classmethod
    def from_value(cls, value) -> SkillProfileKey | None:
        for member in cls.__members__.values():
            if member.value == value:
                return member
        return None

    def get_model(self) -> MODEL_CLASS | ZeroSumEloModel:
        """
        Gets the model to use for the given profile skill key.
        """
        match self:
            case SkillProfileKey.CRANING_SOLOS:
                return ZERO_SUM_MODEL
            case _:
                return MODEL
