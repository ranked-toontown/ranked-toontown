from __future__ import annotations

import typing

import uvicorn
from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobalUD import DistributedObjectGlobalUD
from fastapi import FastAPI

from direct.stdpy import threading

from otp.uberdog.authentication import AuthenticationGlobals
from toontown.api.district_information import DistrictInformation

if typing.TYPE_CHECKING:
    from toontown.uberdog.ToontownUberRepository import ToontownUberRepository


class ApiManagerUD(DistributedObjectGlobalUD):
    """
    UD global that is in charge of external communication from outside the game server to interact with
    game functions and information. This class will expose a public REST API for anybody to interact with,
    and also provide an internal gRPC API for internal applications to use to perform actions on the server
    with elevated permissions (Website dashboards, discord bots, CLI tools, etc.)
    """

    air: ToontownUberRepository

    Notify = DirectNotifyGlobal.directNotify.newCategory('ApiManagerUD')

    def __init__(self, air: ToontownUberRepository):
        super().__init__(air)

        self.districts: dict[int, DistrictInformation] = {}

        self.public_api = FastAPI(title="Toontown Ranked API", version="1.0")
        self.__setup_routes()
        self.__public_api_running = False

        self.__start_public_api()

    def announceGenerate(self):
        super().announceGenerate()
        self.Notify.debug("Starting up...")
        self.d_queryDistrictStats()

    """
    Astron communication
    """

    def d_queryDistrictStats(self):
        """
        Clears the district cache, and forces an update from all districts.
        """
        self.districts.clear()
        self.sendUpdate('queryDistrictStatsUdToAi')
        self.Notify.debug(f"Forcing district stats update. Clearing cache.")

    def postDistrictStatsAiToUd(self, raw: list[typing.Any]):
        """
        A district has just given us some new updated information.
        """
        stats = DistrictInformation.from_astron(raw)
        self.districts[stats.doId] = stats
        self.Notify.debug(f"Received update from district {stats.doId}: {stats}")

    def districtShutdownAiToUd(self, _id: int):
        """
        A district has just informed us that it is shutting down. Remove it.
        """
        if _id in self.districts:
            del self.districts[_id]
        self.Notify.debug(f"Received shutdown update from district: {_id}")

    """
    Public API inner workings
    """
    def __start_public_api(self, host="0.0.0.0", port=8080):

        if self.__public_api_running:
            self.Notify.Warning(f"Tried to start public API when it is already running! Aborting...")
            return

        def run():
            self.Notify.debug(f"Starting public API at {host}:{port}")
            self.__public_api_running = True
            uvicorn.run(self.public_api, host=host, port=port)
            self.__public_api_running = False
            self.__public_api_shutdown_callback()

        # Boot it up
        threading.Thread(target=run).start()

    def __setup_routes(self):

        @self.public_api.get("/status")
        def status():
            return {"status": "ok"}

        @self.public_api.get("/leaderboard")
        def leaderboard():
            return self.air.leaderboardManager.getCachedLeaderboardResults()

        @self.public_api.get("/districts")
        def districts():
            response = {"districts": []}
            total_pop = 0
            for district in self.districts.values():
                val = {"id": district.doId, "name": district.name, "population": district.population}
                response["districts"].append(val)
                total_pop += district.population
            response["totalPopulation"] = total_pop
            return response

        @self.public_api.get("/auth/discord/callback")
        def auth(code: str = None, state: str = None):
            """
            Called via discord authentication redirect. This will fire every time someone tries to login.
            We need to let our backend know that someone is trying to login using the given code and state.
            """

            # If this was a bogus API call, don't even bother.
            if None in [code, state]:
                return

            # Broadcast an event that our authentication services can intercept. You can honestly think of this as a username and password event :p
            ctx = AuthenticationGlobals.DiscordAuthenticationEventContext(code=code, session=state)
            messenger.send(ctx.AUTH_EVENT_IDENTIFIER, [ctx])

    def __public_api_shutdown_callback(self):
        self.Notify.debug("Public API shutting down...")