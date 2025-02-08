from direct.directnotify import DirectNotifyGlobal
from . import HoodDataAI, ZoneUtil
from toontown.toonbase import ToontownGlobals
from panda3d.core import *
from toontown.dna.DNAParser import DNAGroup, DNAVisGroup
from toontown.racing.RaceGlobals import *
from toontown.safezone.DistributedGolfKartAI import DistributedGolfKartAI
from toontown.safezone import GZTreasurePlannerAI
if __debug__:
    import pdb

class GZHoodDataAI(HoodDataAI.HoodDataAI):
    notify = DirectNotifyGlobal.directNotify.newCategory('GZHoodDataAI')

    def __init__(self, air, zoneId=None):
        hoodId = ToontownGlobals.GolfZone
        if zoneId == None:
            zoneId = hoodId
        HoodDataAI.HoodDataAI.__init__(self, air, zoneId, hoodId)
        return

    def startup(self):
        HoodDataAI.HoodDataAI.startup(self)
        self.treasurePlanner = GZTreasurePlannerAI.GZTreasurePlannerAI(self.zoneId)
        self.treasurePlanner.start()
        self.createGolfKarts()

    def cleanup(self):
        pass

    def findAndCreateGolfKarts(self, dnaGroup, zoneId, area, overrideDNAZone=False):
        golfKarts = []
        golfKartGroups = []
        if isinstance(dnaGroup, DNAGroup.DNAGroup) and ('golf_kart' in dnaGroup.getName()):
            golfKartGroups.append(dnaGroup)
            nameInfo = dnaGroup.getName().split('_')
            golfCourse = int(nameInfo[2])
            for i in range(dnaGroup.getNumChildren()):
                childDnaGroup = dnaGroup.at(i)
                if 'starting_block' in childDnaGroup.getName():
                    pos = childDnaGroup.getPos()
                    hpr = childDnaGroup.getHpr()
                    golfKart = DistributedGolfKartAI(self.air, golfCourse, pos[0], pos[1], pos[2], hpr[0], hpr[1], hpr[2])
                    golfKart.generateWithRequired(zoneId)
                    golfKarts.append(golfKart)
            else:
                self.notify.warning('unhandled case')
        elif isinstance(dnaGroup, DNAVisGroup) and not overrideDNAZone:
                zoneId = ZoneUtil.getTrueZoneId(int(dnaGroup.getName().split(':')[0]), zoneId)
        for i in range(dnaGroup.getNumChildren()):
            childGolfKarts, childGolfKartGroups = self.findAndCreateGolfKarts(dnaGroup.at(i), zoneId, area, overrideDNAZone)
            golfKarts.extend(childGolfKarts)
            golfKartGroups.extend(childGolfKartGroups)

        return (golfKarts, golfKartGroups)

    def createGolfKarts(self):
        self.golfKarts = []
        self.golfKartGroups = []
        for zone in self.air.zoneTable[self.canonicalHoodId]:
            zoneId = ZoneUtil.getTrueZoneId(zone[0], self.zoneId)
            dnaData = self.air.dnaDataMap[self.zoneId]
            if dnaData.getName() == 'root':
                area = ZoneUtil.getCanonicalZoneId(zoneId)
                foundKarts, foundKartGroups = self.findAndCreateGolfKarts(dnaData, zoneId, area, overrideDNAZone=True)
                self.golfKarts.extend(foundKarts)
                self.golfKartGroups.extend(foundKartGroups)

        for golfKart in self.golfKarts:
            golfKart.start()
            self.addDistObj(golfKart)

        return