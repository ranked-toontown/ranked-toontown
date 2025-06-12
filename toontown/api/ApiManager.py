from direct.distributed.DistributedObjectGlobal import DistributedObjectGlobal


class ApiManager(DistributedObjectGlobal):

    def __init__(self, cr):
        DistributedObjectGlobal.__init__(self, cr)