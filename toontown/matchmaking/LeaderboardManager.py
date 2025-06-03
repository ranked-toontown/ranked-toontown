from direct.directnotify import DirectNotifyGlobal
from direct.distributed.DistributedObjectGlobal import DistributedObjectGlobal


class LeaderboardManager(DistributedObjectGlobal):
    notify = DirectNotifyGlobal.directNotify.newCategory('LeaderboardManager')
    neverDisable = 1

    def __init__(self, cr):
        DistributedObjectGlobal.__init__(self, cr)
        self.notify.info('LeaderboardManager initiated')