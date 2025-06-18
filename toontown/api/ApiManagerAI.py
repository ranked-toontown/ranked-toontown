from __future__ import annotations

import typing

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobalAI import DistributedObjectGlobalAI

from toontown.api.district_information import DistrictInformation

if typing.TYPE_CHECKING:
    from toontown.ai.ToontownAIRepository import ToontownAIRepository


class ApiManagerAI(DistributedObjectGlobalAI):

    Notify = DirectNotifyGlobal.directNotify.newCategory('ApiManagerAI')
    air: ToontownAIRepository

    def __init__(self, air):
        DistributedObjectGlobalAI.__init__(self, air)

    def announceGenerate(self):
        super().announceGenerate()
        self.Notify.debug("Starting up...")

        # Alert UD that we booted up.
        self.d_postDistrictStats()

    def d_postDistrictStats(self):
        stats = DistrictInformation(self.air.districtId, self.air.districtName, self.air.districtStats.getAvatarCount())
        self.sendUpdate('postDistrictStatsAiToUd', [stats])

    def queryDistrictStatsUdToAi(self):
        """
        The UD has instructed us to inform it of our stats.
        """
        self.d_postDistrictStats()

    def d_alertShutdown(self):
        self.sendUpdate('districtShutdownAiToUd', [self.air.districtId])