import json
import os
import time
from typing import Any

from .match_replay import MatchReplay, MatchMetadata
from .match_event import get_event_class


def serialize_match(match: MatchReplay) -> dict[str, Any]:
    output = {"metadata": match.get_metadata().serialize(), "events": [event.serialize() for event in match.events]}
    return output

def deserialize_match(filepath: str) -> MatchReplay | Exception:

    # Read in the file as JSON data.
    data = None
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except Exception as e:
        return e

    # Attempt to read in the raw data to construct a match replay.
    replay = MatchReplay()

    # Metadata currently is just player information and timestamp.
    metadata = MatchMetadata.deserialize(data["metadata"])
    replay.metadata = metadata

    # Construct events.
    for event_object in data["events"]:
        class_id = event_object["event"]
        clazz = get_event_class(class_id)
        if clazz is None:
            return Exception(f"Failed to parse match. Unknown event class {class_id}")

        try:
            replay.add_event(clazz.deserialize(event_object))
        except Exception as e:
            return Exception(f"{e} Failed to parse match. JSON parse error for event data: {event_object}")

    return replay


def make_filename():
    return f"crane_{int(time.time())}.replay"


def save(match: MatchReplay):
    directory = "./replays"

    try:
        os.mkdir(directory)
    except FileExistsError:
        pass

    filename = make_filename()
    raw = serialize_match(match)
    with open(f"{directory}/{filename}", "w") as f:
        json.dump(raw, f, indent=2)