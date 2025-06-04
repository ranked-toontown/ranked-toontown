from __future__ import annotations
from enum import Enum


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