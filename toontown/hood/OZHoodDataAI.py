from direct.directnotify import DirectNotifyGlobal
from . import HoodDataAI, ZoneUtil
from toontown.toonbase import ToontownGlobals
from toontown.safezone import OZTreasurePlannerAI
from panda3d.core import *
from toontown.dna.DNAParser import DNAGroup, DNAVisGroup
from toontown.racing.RaceGlobals import *
from toontown.safezone.DistributedPicnicBasketAI import DistributedPicnicBasketAI
from toontown.distributed import DistributedTimerAI
from toontown.safezone.DistributedPicnicTableAI import DistributedPicnicTableAI
from toontown.safezone import DistributedChineseCheckersAI
from toontown.safezone import DistributedCheckersAI
if __debug__:
    import pdb

class OZHoodDataAI(HoodDataAI.HoodDataAI):
    notify = DirectNotifyGlobal.directNotify.newCategory('OZHoodDataAI')

    def __init__(self, air, zoneId=None):
        hoodId = ToontownGlobals.OutdoorZone
        if zoneId == None:
            zoneId = hoodId
        HoodDataAI.HoodDataAI.__init__(self, air, zoneId, hoodId)
        return

    def startup(self):
        HoodDataAI.HoodDataAI.startup(self)
        self.treasurePlanner = [
                                OZTreasurePlannerAI.OZTreasurePlannerAI(self.zoneId)
                                ]
        for planner in self.treasurePlanner:
            planner.start()
        self.timer = DistributedTimerAI.DistributedTimerAI(self.air)
        self.timer.generateWithRequired(self.zoneId)
        self.createTables()

    def cleanup(self):
        pass

    def findAndCreateTables(self, dnaGroup, zoneId, area, type):
        picnicTables = []
        if isinstance(dnaGroup, DNAGroup.DNAGroup) and type in dnaGroup.getName():
            nameInfo = dnaGroup.getName().split('_')
            for i in range(dnaGroup.getNumChildren()):
                childDnaGroup = dnaGroup.at(i)
                if 'game_table' in childDnaGroup.getName():
                    pos = childDnaGroup.getPos()
                    hpr = childDnaGroup.getHpr()
                    cls = DistributedPicnicTableAI if type == 'game_table' else DistributedPicnicBasketAI if type == 'picnic_table' else None
                    picnicTable = cls(self.air, zoneId, nameInfo[2], pos[0], pos[1], pos[2], hpr[0], hpr[1], hpr[2])
                    picnicTable.generateWithRequired(zoneId)
                    picnicTables.append(picnicTable)
        else:
            if isinstance(dnaGroup, DNAVisGroup):
                zoneId = ZoneUtil.getTrueZoneId(int(dnaGroup.getName().split(':')[0]), zoneId)
            for i in range(dnaGroup.getNumChildren()):
                childPicnicTables = self.findAndCreateTables(dnaGroup.at(i), zoneId, area, type)
                picnicTables += childPicnicTables

        return picnicTables

    def createTables(self):
        self.gameTables = []
        self.picnicTables = []
        for zone in self.air.zoneTable[self.canonicalHoodId]:
            zoneId = ZoneUtil.getTrueZoneId(zone[0], self.zoneId)
            dnaData = self.air.dnaDataMap[self.zoneId]
            if dnaData.getName() == 'root':
                area = ZoneUtil.getCanonicalZoneId(zoneId)
                foundGameTables = self.findAndCreateTables(dnaData, zoneId, area, 'game_table')
                self.gameTables.extend(foundGameTables)
                foundPicnicTables = self.findAndCreateTables(dnaData, zoneId, area, 'picnic_table')
                self.picnicTables.extend(foundPicnicTables)

        for gameTable in self.gameTables:
            self.addDistObj(gameTable)
        for picnicTable in self.picnicTables:
            picnicTable.start()
            self.addDistObj(picnicTable)

        return
