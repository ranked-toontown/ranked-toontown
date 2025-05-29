import time

from tools.match_recording import match_serializer
from tools.match_recording.match_event import PointEvent, RoundBeginEvent, RoundEndEvent, ComboChangeEvent
from tools.match_recording.match_player import MatchPlayer
from tools.match_recording.match_replay import MatchReplay, MatchMetadata


# Creating a match, adding players, adding events, and saving to a file.
# Use in your game to serialize match data!
match = MatchReplay()

metadata = MatchMetadata()
metadata.set_timestamp(time.time())
metadata.add_player(MatchPlayer(12345, "player 1"))
metadata.add_player(MatchPlayer(6789, "player 2"))

match.set_metadata(metadata)

match.add_event(RoundBeginEvent(time.time() + 4.5643540395890))
match.add_event(PointEvent(
    time.time() + 5.6984606908,
    6789,
    PointEvent.Reason.DEFAULT,
    5
))
match.add_event(ComboChangeEvent(time.time() + 4.5643540395890, 6789, 1))

match.add_event(PointEvent(
    time.time() + 6.6984606908,
    6789,
    PointEvent.Reason.DEFAULT,
    6
))
match.add_event(ComboChangeEvent(time.time() + 6.6984606908, 6789, 2))

match.add_event(PointEvent(
    time.time() + 8.234222222,
    12345,
    PointEvent.Reason.GOON_STOMP,
    1
))

match.add_event(ComboChangeEvent(time.time() + 8.6984606908, 6789, 0))

match.add_event(PointEvent(
    time.time() + 9.9348934899,
    6789,
    PointEvent.Reason.DEFAULT,
    50
))
match.add_event(PointEvent(
    time.time() + 9.9348934899,
    6789,
    PointEvent.Reason.STUN,
    50
))
match.add_event(RoundEndEvent(time.time() + 15.23894890274, 6789))

# Call this if you want to save the results!!!
match_serializer.save(match)


# Reading from a replay file. Use this to read the data from the file.
match = match_serializer.deserialize_match("./replays/crane_1748555997.replay")

# The method will return an exception if something goes wrong. You should check for this.
if isinstance(match, Exception):
    print(f"Failed to deserialize match: {match}")
    exit(-1)

# The match result should be an instance of MatchReplay:
print(f"Match played at time: {match.get_metadata().get_timestamp()}")
print(f"Players: {match.get_metadata().get_players()}")
print()
for event in match.get_events():
    print(f"Event class: {event.__class__.__name__}")
    if isinstance(event, PointEvent):
        player = match.get_player(event.get_player())
        print(f"{player} scored {event.get_points()} points from: {event.reason}")
    elif isinstance(event, RoundBeginEvent):
        print(f"RoundBeginEvent: {event.timestamp}")
    elif isinstance(event, ComboChangeEvent):
        print(f"ComboChangeEvent: {event.timestamp} {event.get_player()} is now on a {event.get_chain()} combo")
    elif isinstance(event, RoundEndEvent):
        print(f"RoundEndEvent: {event.timestamp}")
    print()

