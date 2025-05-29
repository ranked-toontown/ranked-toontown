from typing import Any

from .common import Serializable


class MatchPlayer(Serializable):

    def __init__(self, _id: int, name: str):
        self._id: int = _id
        self.name: str = name

    def get_id(self) -> int:
        """
        Get the toon ID of the player.
        """
        return self._id

    def get_name(self) -> str:
        """
        Get the name of the player at the time of the replay.
        """
        return self.name

    @classmethod
    def deserialize(cls, data: dict[str, Any]):
        return MatchPlayer(data["id"], data["name"])

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.get_id(),
            "name": self.get_name(),
        }

    def __str__(self):
        return f"{self.name} ({self._id})"

    def __repr__(self):
        return self.__str__()