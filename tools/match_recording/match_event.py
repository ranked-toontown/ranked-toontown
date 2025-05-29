import time
from abc import abstractmethod
from enum import Enum
from typing import Any

from .common import Serializable
from .match_player import MatchPlayer


class MatchEvent(Serializable):

    def __init__(self, timestamp: float):
        self.timestamp: float = timestamp

    @classmethod
    @abstractmethod
    def get_event_type(cls) -> int:
        raise NotImplementedError("Please implement this method")


class PointEvent(MatchEvent):

    class Reason(Enum):
        DEFAULT = ""
        LOW_LAFF = "UBER BONUS"
        GOON_STOMP = 'STOMP!'
        STUN = "STUN!"
        SIDE_STUN = "SIDE-STUN!"
        FULL_IMPACT = "PERFECT!"
        REMOVE_HELMET = "DE-SAFE!"
        GOON_KILL = "DESTRUCTION!"
        KILLING_BLOW = 'FINAL BLOW!'
        COIN_FLIP = 'COIN FLIP!'
        COMBO = "COMBO!"
        APPLIED_HELMET = "SAFED!"
        TOOK_TREASURE = 'TREASURE!'
        WENT_SAD = "DIED!"
        LOW_IMPACT = 'SLOPPY!'
        UNSTUN = 'UN-STUN!'

        @classmethod
        def from_value(cls, value):
            for member in PointEvent.Reason.__members__.values():
                if member.value == value:
                    return member
            return PointEvent.Reason.DEFAULT

    def __init__(self, timestamp: float, player_id: int, reason: Reason, points: int):
        super().__init__(timestamp)
        self.player: int = player_id
        self.reason: PointEvent.Reason = reason
        self.points: int = points

    def get_player(self) -> int:
        """
        Get the ID of the player that is earning/losing points.
        """
        return self.player

    def get_points(self) -> int:
        """
        Get the amount of points that was earned/lost in this event. If the number of points is positive, then points
        were earned. If the number of points is negative, then points were lost.
        """
        return self.points

    @classmethod
    def get_event_type(cls) -> int:
        return 1

    def serialize(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event": self.get_event_type(),
            "player": self.player,
            "reason": self.reason.value,
            "points": self.points
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]):
        return PointEvent(
            data['timestamp'],
            data['player'],
            PointEvent.Reason.from_value(data["reason"]),
            data["points"]
        )

class ComboChangeEvent(MatchEvent):

    def __init__(self, timestamp: float, player_id: int, chain: int):
        super().__init__(timestamp)
        self.player_id: int = player_id
        self.chain: int = chain

    @classmethod
    def get_event_type(cls) -> int:
        return 4

    def serialize(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event": self.get_event_type(),
            "player": self.player_id,
            "chain": self.chain
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]):
        return ComboChangeEvent(
            data['timestamp'],
            data['player'],
            data["chain"]
        )

    def get_chain(self):
        return self.chain

    def get_player(self):
        return self.player_id


class RoundBeginEvent(MatchEvent):

    @classmethod
    def get_event_type(cls) -> int:
        return 2

    def serialize(self) -> dict[str, Any]:
        return {
            "event": self.get_event_type(),
            "timestamp": self.timestamp
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]):
        return RoundBeginEvent(data["timestamp"])


class RoundEndEvent(MatchEvent):

    def __init__(self, timestamp: float, winner: int):
        super().__init__(timestamp)
        self.winner: int | None = winner

    def get_winner(self) -> int | None:
        """
        Returns the winner of the match. If this is None, this means there was a draw.
        """
        return self.winner

    @classmethod
    def get_event_type(cls) -> int:
        return 3

    def serialize(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event": self.get_event_type(),
            "timestamp": self.timestamp
        }

        if self.winner is not None:
            data["winner"] = self.winner

        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]):

        winner = None
        if 'winner' in data:
            winner = data['winner']

        return RoundEndEvent(data['timestamp'], winner)


EVENT_REGISTRY = [
    PointEvent,
    RoundBeginEvent,
    RoundEndEvent,
]

EVENT_ID_TO_REGISTERED_EVENT = {e.get_event_type(): e for e in EVENT_REGISTRY}

def get_event_class(event_type: int):
    return EVENT_ID_TO_REGISTERED_EVENT.get(event_type, None)
