from typing import Any

from .match_event import MatchEvent
from .match_player import MatchPlayer
from .common import Serializable


class MatchMetadata(Serializable):

    def __init__(self):
        self.timestamp: float = 0
        self.player_information: dict[int, MatchPlayer] = {}

    def serialize(self) -> dict[str, Any]:
        player_info = [p.serialize() for p in self.player_information.values()]
        return {
            "timestamp": self.timestamp,
            "players": player_info,
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]):

        ret = MatchMetadata()

        ret.timestamp = data["timestamp"]
        for player_object in data["players"]:
            player = MatchPlayer.deserialize(player_object)
            ret.player_information[player.get_id()] = player

        return ret

    def get_players(self) -> list[MatchPlayer]:
        return list(self.player_information.values())

    def get_or_create_player(self, _id, name=""):
        if _id in self.player_information:
            return self.player_information[_id]

        player = MatchPlayer(_id, name)
        self.player_information[_id] = player
        return player

    def add_player(self, player: MatchPlayer):
        self.player_information[player.get_id()] = player

    def get_timestamp(self):
        return self.timestamp

    def get_player(self, _id) -> MatchPlayer | None:
        return self.player_information.get(_id, None)

    def set_timestamp(self, timestamp):
        self.timestamp = timestamp


class MatchReplay:

    def __init__(self, timestamp=None):
        self.events: list[MatchEvent] = []
        self.metadata: MatchMetadata = MatchMetadata()
        if timestamp is not None:
            self.metadata.timestamp = timestamp

    def get_events(self) -> list[MatchEvent]:
        return self.events

    def get_metadata(self) -> MatchMetadata:
        return self.metadata

    def add_event(self, event: MatchEvent):
        self.events.append(event)

    def set_metadata(self, metadata: MatchMetadata):
        self.metadata = metadata

    def get_player(self, _id: int) -> MatchPlayer | None:
        return self.metadata.get_player(_id)
