import copy
import json
from typing import Any

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobalUD import DistributedObjectGlobalUD

from toontown.matchmaking.player_skill_profile import PlayerSkillProfile
from toontown.matchmaking.skill_profile_keys import SkillProfileKey


class LeaderboardManagerUD(DistributedObjectGlobalUD):

    notify = DirectNotifyGlobal.directNotify.newCategory('LeaderboardManagerUD')
    cache_filepath = "sr_leaderboard_cache.json"

    def __init__(self, air):
        DistributedObjectGlobalUD.__init__(self, air)
        self.air = air
        self.notify.info("Leaderboard initiated")

        # This is a tough one. Astron's DB interface doesn't allow us to perform advanced queries on every DO record. (I think?)
        # So to remedy this, we are going to use a JSON file that keeps track of toon IDs that are considered "active",
        # and when UD starts up we can query the DB for these players and cache their information. Then, when ranked
        # matches conclude, we can update the cache. That way when information is requested, we can just read values
        # from memory. Ideally, I would prefer to read database every 5 minutes and grab top X people.
        # todo: when we are committed to using either SQL/Mongo, refactor this to interact with the DB directly.
        self.__leaderboard_active_players_cache = {}  # {mode: [toonids....]}
        self.__sr_cache = {}  # {mode: toonid: [name, sr]}
        self.__read_or_create_cached_leaderboard_data()

        # todo: once again, this can go. our refresh task should handle this with a real DB.
        _dclass = self.air.dclassesByName['DistributedToonUD']
        for key, activePlayerList in self.__leaderboard_active_players_cache.items():
            for activePlayer in activePlayerList:
                # Queue up a request to query skill profiles for the toon. Once queried, the __database_callback function will fire.
                self.air.dbInterface.queryObject(self.air.dbId, activePlayer, self.__database_callback, dclass=_dclass, fieldNames=('setName', 'setSkillProfiles',))

        taskMgr.doMethodLater(10, self.__refresh_task, 'leaderboard-refresh-task')

    def getCachedLeaderboardResults(self) -> dict[str, dict[int, list[Any]]]:
        return self.__sr_cache

    def handleRankedMatchResultsAiToUd(self, results, nameMap):
        """
        Called from the AI. A ranked match has just concluded, and the district is informing of us of rating updates.
        """
        self.notify.debug('got results: ' + str(results))
        names = {key: value for key, value in nameMap}

        # Any toon that we just got word of needs to start being tracked if they aren't already.
        for result in results:
            profile = PlayerSkillProfile.from_astron(result)
            players = self.__leaderboard_active_players_cache.get(profile.key)
            if players is None:
                players = []

            players.append(profile.identifier)
            self.__leaderboard_active_players_cache[profile.key] = list(set(players))

            # Also, update the SR cache so that we can quickly query SR data.
            data = self.__sr_cache.get(profile.key)
            if data is None:
                data = {}
                self.__sr_cache[profile.key] = data

            data[profile.identifier] = [names[profile.identifier], profile.skill_rating, profile.wins, profile.games_played]
            self.__sr_cache[profile.key] = data

        self.__save_leaderboard_data()

    def requestRankingsClientToUd(self, key: str, start: int, amount: int):
        avId = self.air.getAvatarIdFromSender()

        # Validate the key. If it is invalid, don't do anything.
        profileKey = SkillProfileKey.from_value(key)
        if profileKey is None:
            return

        # Validate that proper bounds were given.
        if start <= 0:
            return

        # Verify that we weren't given some ridiculous amount to query. Our GUI only does 10 at a time.
        if amount > 50:
            return

        # Verify that we aren't attempting to query something insanely out of reach.
        if start > 500:
            return

        # Check that we have entries cached for the key. If we don't we can send an empty list of records!
        if profileKey.value not in self.__sr_cache:
            self.notify.debug(f"Sending empty {profileKey.value} ratings update to {avId} - no records on file")
            self.sendUpdateToAvatarId(avId, 'requestRankingsResponse', [profileKey.value, []])
            return

        # We are good to return some data. Do not make DB calls. Create a sorted list of the top profile entries.
        records = copy.deepcopy(list(self.__sr_cache[profileKey.value].values()))
        # Sort the records based on SR.
        records.sort(key=lambda x: x[1], reverse=True)
        # Slice the list from where the user wanted it to start. Just to make this easier, let's add a dummy record
        # First of all, do we even have enough records? If they requested out of bounds, we want to give them an empty list.
        end_index = start + amount - 1
        end_index = min(end_index, len(records))
        if len(records) < start:
            records = []
        else:
            records = records[start-1:end_index]

        # Append ranking to all the records.
        for i, record in enumerate(records):
            record.insert(0, i+1)

        self.notify.debug(f"Sending {profileKey.value} ratings update to {avId}: {records}")
        self.sendUpdateToAvatarId(avId, 'requestRankingsResponse', [profileKey.value, records])

    def __database_callback(self, dclass, fields):
        """
        Database callback that only runs on startup. Queries avatar information regarding skill profiles.
        """
        if dclass is None:
            self.notify.error('Failed to resolve DB query. dclass is None.')
            return

        if fields is None:
            self.notify.error(f'Failed to resolve fields for dclass {dclass}. fields is None.')
            return

        if 'setSkillProfiles' not in fields:
            self.notify.debug(f"Failed to retrieve skill profiles. Toon does not have any skill profiles on record.")
            return

        if 'setName' not in fields:
            self.notify.error(f"Failed to retrieve name. Toon does not have a name?")
            return

        profiles = fields['setSkillProfiles'][0]
        name = fields['setName'][0]

        # Loop through this player's skill profiles.
        for raw in profiles:

            # Convert the profile to something we can work with.
            profile = PlayerSkillProfile.from_astron(raw)

            # Grab all the data cached for the gamemode. If it is non-existent, initialize it with an empty dictionary.
            mode_data = self.__sr_cache.get(profile.key)
            if mode_data is None:
                self.__sr_cache[profile.key] = {}
                mode_data = {}

            # Store the player's name and SR under their toon ID for this gamemode and save the changes to the cache.
            mode_data[profile.identifier] = [name, profile.skill_rating, profile.wins, profile.games_played]
            self.__sr_cache[profile.key] = mode_data

    def __refresh_task(self, task):
        """
        Called every so often to refresh the leaderboard cache. We prefer this so that clients can request updates
        as frequently as they want without calling the database over and over.
        """

        # Currently does nothing. Once we have the technology to query DB directly, we should do a full toon record
        # query for all modes and sort by SR and update our cache that way. Since there's no way we are every going to
        # have more than like 10k toons on file at once, I don't see how this could ever become an issue.

        # task.delayTime = 60 * 5
        task.delayTime = 5
        return task.again

    def __read_or_create_cached_leaderboard_data(self):
        """
        Reads data from the JSON file and syncs it in memory to our leaderboard cache. Should only be called once.
        """

        # Open a JSON file containing leaderboard data.
        try:
            with open(self.cache_filepath, 'r') as f:
                data = json.load(f)

                # If this JSON data is malformed or non-existent, save a fresh copy and abort.
                if not isinstance(data, dict):
                    self.__leaderboard_active_players_cache = {key.value: [] for key in SkillProfileKey}
                    self.__save_leaderboard_data()
                    return

                # Loop through all the keys. These are meant to map to types of modes.
                for key in data.keys():
                    profile_type = SkillProfileKey.from_value(key)

                    # Skip bad keys.
                    if profile_type is None:
                        self.notify.debug(f"Failed to parse key: {key} - JSON is either malformed or out of date. Skipping.")
                        continue

                    # Skip bad data as a value for this key.
                    active_ids = data[key]
                    if not isinstance(active_ids, list):
                        self.notify.debug(f"Failed to parse data for key {key} - Expected list of IDs but got {type(active_ids)}")
                        continue

                    # Set the data.
                    self.__leaderboard_active_players_cache[key] = active_ids

        except FileNotFoundError:
            # If the file wasn't found, simply just create the file.
            self.__leaderboard_active_players_cache = {key.value: [] for key in SkillProfileKey}
            self.__save_leaderboard_data()

    def __save_leaderboard_data(self):
        """
        Saves whatever data we have in memory to our JSON leaderboard file. Should be called after SR updates.
        """
        with open(self.cache_filepath, 'w') as f:
            json.dump(self.__leaderboard_active_players_cache, f)
