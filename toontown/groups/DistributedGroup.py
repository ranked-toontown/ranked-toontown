from direct.distributed.DistributedObject import DistributedObject
from direct.gui.DirectLabel import DirectLabel

from libotp.nametag.WhisperGlobals import WhisperType
from toontown.groups import GroupGlobals
from toontown.groups.GroupBase import GroupBase
from toontown.groups.GroupInterface import GroupInterface
from toontown.groups.GroupMemberStruct import GroupMemberStruct
from toontown.toonbase import ToontownGlobals


class DistributedGroup(DistributedObject, GroupBase):

    def __init__(self, cr):
        DistributedObject.__init__(self, cr)
        GroupBase.__init__(self, GroupBase.NoLeader)

        self.interface: GroupInterface | None = None
        self.going_text: DirectLabel | None = None

    def announceGenerate(self):
        DistributedObject.announceGenerate(self)
        if self.__localToonInGroup():
            base.localAvatar.getGroupManager().setCurrentGroup(self.getDoId())

        self.render()

    def delete(self):

        # If we are in the group and this group is deleting, send an update to mark us as not ready.
        # This probably means we are leaving the area and are unable to respond to the group sending us to game.
        if self.__localToonInGroup() and base.localAvatar.getGroupManager() is not None:
            base.localAvatar.getGroupManager().updateStatus(GroupGlobals.STATUS_UNREADY)

        DistributedObject.delete(self)
        self.cleanup()

    def __localToonInGroup(self) -> bool:
        return base.localAvatar.getDoId() in self.getMemberIds()

    """
    Methods used for GUI management.
    """

    def render(self):

        # No need to render the group if we aren't in it.
        if not self.__localToonInGroup():
            self.__deleteInterface()
            return

        if self.interface is None:
            self.__makeNewInterface()

        self.interface.updateMembers(self.getMembers())

    def cleanup(self):
        self.__deleteInterface()

    def __makeNewInterface(self):
        self.__deleteInterface()
        self.interface = GroupInterface(self)
        self.going_text = DirectLabel(parent=base.a2dBottomCenter, pos=(0, 0, .3), text='', textMayChange=1, text_scale=.15,
                    text_shadow=(0, 0, 0, 1), text_fg=(.15, .9, .15, 1), text_font=ToontownGlobals.getCompetitionFont())

    def __updateTitleText(self, text: str, color: tuple[float, float, float, float]):
        if self.going_text is None:
            return
        self.going_text['text'] = text
        self.going_text['text_fg'] = color

    def __deleteInterface(self):
        if self.interface is not None:
            self.interface.destroy()
            self.interface = None

        if self.going_text is not None:
            self.going_text.destroy()
            self.going_text = None

    """
    Methods called from the AI over astron.
    """
    def setMembers(self, members: list[list[int, int, int, bool]]):

        formattedMembers: list[GroupMemberStruct] = []
        leader = None

        for entry in members:
            member = GroupMemberStruct.from_struct(entry)
            if member.leader:
                leader = member
            formattedMembers.append(member)

        super().setMembers(formattedMembers)
        self.setLeader(leader.avId if leader is not None else GroupBase.NoLeader)
        self.render()

    def announce(self, message: str):
        if self.__localToonInGroup():
            base.localAvatar.setSystemMessage(0, message, whisperType=WhisperType.WTToontownBoardingGroup)

    def setMinigameZone(self, minigameZone, minigameGameId):

        playground = base.cr.playGame.getPlace()

        # First, freeze the toon. We need to prevent softlocks.
        playground.setState('stopped')

        def __updateText(i):
            if i <= 0:
                self.__updateTitleText('Have fun!', color=(.15, .9, .15, 1))
                return

            self.__updateTitleText(f"Leaving in {i}...", color=(.6, .6, .6, 1))
            taskMgr.remove(self.uniqueName('teleportToMinigameTextUpdate'))
            taskMgr.doMethodLater(1, __updateText, self.uniqueName('teleportToMinigameTextUpdate'), extraArgs=[i-1])

        def __teleportToMinigame(_=None):
            doneStatus = {
                'loader': 'minigame',
                'where': 'minigame',
                'hoodId': playground.loader.hood.id,
                'zoneId': minigameZone,
                'shardId': None,
                'minigameId': minigameGameId,
                'avId': None,
            }
            playground.doneStatus = doneStatus
            playground.fsm.forceTransition('teleportOut', [doneStatus])

        # Next, in 3 seconds we should teleport to where we need to go.
        taskMgr.doMethodLater(3, __teleportToMinigame, self.uniqueName('teleportToMinigame'))
        __updateText(3)