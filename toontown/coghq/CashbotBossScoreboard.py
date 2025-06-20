import dataclasses

from direct.gui.DirectGui import *
from panda3d.core import *

from direct.showbase.DirectObject import DirectObject
from toontown.coghq import CraneLeagueGlobals
from toontown.suit.Suit import *
from direct.task.Task import Task
from direct.interval.IntervalGlobal import *

from toontown.toon.ToonHead import ToonHead

import random
import math

POINTS_TEXT_SCALE = .09

LABEL_Y_POS = .55

# TEXT COLORS
RED = (1, 0, 0, 1)
GREEN = (0, 1, 0, 1)
GOLD = (1, 235.0 / 255.0, 165.0 / 255.0, 1)
WHITE = (.9, .9, .9, .85)
CYAN = (0, 1, 240.0 / 255.0, 1)


def doGainAnimation(label, amount, old_amount, new_amount, reason='', localAvFlag=False):
    pointText = label.points_text
    reasonFlag = len(reason) > 0  # reason flag is true if there is a reason
    randomRoll = random.randint(1, 20) + 10 if reasonFlag else 5
    textToShow = '+' + str(amount) + ' ' + reason
    popup = OnscreenText(parent=pointText, text=textToShow, style=3, fg=GOLD if reasonFlag else GREEN,
                         align=TextNode.ACenter, scale=.05, pos=(.03, .03), roll=-randomRoll, font=ToontownGlobals.getCompetitionFont())

    def cleanup():
        popup.cleanup()

    def doTextUpdate(n):
        try:
            pointText.setText(str(int(math.ceil(n))))
        except AttributeError:
            pass  # Monkey fix until i find exact cause

    # points with a reason go towards the right to see easier
    rx = random.random() / 5.0 - .1  # -.1-.1
    rz = random.random() / 10.0  # 0-.1
    xOffset = .125+rx if reasonFlag else .01+(rx/5.0)
    zOffset = .02+rz if reasonFlag else .055+(rz/5.0)
    reasonTimeAdd = .85 if reasonFlag else 0
    popupStartColor = CYAN if reasonFlag else GREEN
    popupFadedColor = (CYAN[0], CYAN[1], CYAN[2], 0) if reasonFlag else (GREEN[0], GREEN[1], GREEN[2], 0)

    targetPos = Point3(pointText.getX() + xOffset, 0, pointText.getZ() + zOffset)
    startPos = Point3(popup.getX(), popup.getY(), popup.getZ())
    label.cancel_inc_ival()

    label.inc_ival = Sequence(
        LerpFunctionInterval(doTextUpdate, fromData=old_amount, toData=new_amount, duration=.5, blendType='easeOut')
    )
    label.inc_ival.start()

    Sequence(
        Parallel(
            LerpColorScaleInterval(popup, duration=.95 + reasonTimeAdd, colorScale=popupFadedColor,
                                   startColorScale=popupStartColor, blendType='easeInOut'),
            LerpPosInterval(popup, duration=.95 + reasonTimeAdd, pos=targetPos, startPos=startPos,
                            blendType='easeInOut'),
            Sequence(
                Parallel(
                    LerpScaleInterval(pointText, duration=.25, scale=1 + .2,
                                      startScale=1, blendType='easeInOut'),
                    LerpColorScaleInterval(pointText, duration=.25, colorScale=GREEN, startColorScale=(1, 1, 1, 1),
                                           blendType='easeInOut'),
                ),
                Parallel(
                    LerpScaleInterval(pointText, duration=.25, startScale=1 + .2,
                                      scale=1, blendType='easeInOut'),
                    LerpColorScaleInterval(pointText, duration=.25, startColorScale=GREEN, colorScale=(1, 1, 1, 1),
                                           blendType='easeInOut')
                )

            )
        ),
        Func(cleanup)
    ).start()


def doLossAnimation(label, amount, old_amount, new_amount, reason='', localAvFlag=False):
    pointText = label.points_text
    reasonFlag = True if len(reason) > 0 else False  # reason flag is true if there is a reason
    randomRoll = random.randint(5, 15) + 15 if reasonFlag else 5

    textToShow = str(amount) + ' ' + reason
    popup = OnscreenText(parent=pointText, text=textToShow, style=3, fg=RED, align=TextNode.ACenter, scale=.05,
                         pos=(.03, .03), roll=-randomRoll, font=ToontownGlobals.getCompetitionFont())

    def cleanup():
        popup.cleanup()

    def doTextUpdate(n):
        try:
            pointText.setText(str(int(n)))
        except AttributeError:
            pass  # Monkey fix until i find out exact cause

    rx = random.random() / 5.0 - .1  # -.1-.1
    rz = random.random() / 10.0  # 0-.1
    xOffset = .125 + rx if reasonFlag else .01 + (rx / 5.0)
    zOffset = .02 + rz if reasonFlag else .055 + (rz / 5.0)
    targetPos = Point3(pointText.getX() + xOffset, 0, pointText.getZ() + zOffset)
    startPos = Point3(popup.getX(), popup.getY(), popup.getZ())
    label.cancel_inc_ival()

    label.inc_ival = Sequence(
        LerpFunctionInterval(doTextUpdate, fromData=old_amount, toData=new_amount, duration=.5, blendType='easeOut')
    )
    label.inc_ival.start()
    Sequence(
        Parallel(
            LerpFunc(doTextUpdate, fromData=old_amount, toData=new_amount, duration=.5, blendType='easeInOut'),
            LerpColorScaleInterval(popup, duration=2, colorScale=(1, 0, 0, 0), startColorScale=RED,
                                   blendType='easeInOut'),
            LerpPosInterval(popup, duration=2, pos=targetPos, startPos=startPos, blendType='easeInOut'),
            Sequence(
                Parallel(
                    LerpScaleInterval(pointText, duration=.25, scale=1 - .2,
                                      startScale=1, blendType='easeInOut'),
                    LerpColorScaleInterval(pointText, duration=.25, colorScale=RED, startColorScale=(1, 1, 1, 1),
                                           blendType='easeInOut'),
                ),
                Parallel(
                    LerpScaleInterval(pointText, duration=.25, startScale=1 - .2,
                                      scale=1, blendType='easeInOut'),
                    LerpColorScaleInterval(pointText, duration=.25, startColorScale=RED, colorScale=(1, 1, 1, 1),
                                           blendType='easeInOut')
                )

            )
        ),
        Func(cleanup)
    ).start()


def getScoreboardTextRow(scoreboard_frame, unique_id, default_text='', frame_color=(.5, .5, .5, .75), isToon=False):
    n = TextNode(unique_id)
    n.setText(default_text)
    n.setAlign(TextNode.ALeft)
    n.setFrameColor(frame_color)
    y_margin_addition = .4 if isToon else 0
    n.setFrameAsMargin(0.4, 0.4, 0.2+y_margin_addition, 0.2+y_margin_addition)
    n.setCardColor(.2, .2, .2, .75)
    n.setCardAsMargin(0.38, 0.38, 0.19, 0.19)
    n.setCardDecal(True)
    n.setShadow(0.05, 0.05)
    n.setShadowColor(0, 0, 0, 1)
    n.setTextColor(.7, .7, .7, 1)
    n.setTextScale(1)
    n.setFont(ToontownGlobals.getCompetitionFont())
    p = scoreboard_frame.attachNewNode(n)
    p.setScale(.05)
    return n, p  # Modify n for actual text properties, p for scale/pos


@dataclasses.dataclass
class CachedPointInstance:
    reason: CraneLeagueGlobals.ScoreReason
    amount: int
    callback: object


class CashbotBossScoreboardToonRow(DirectObject):
    INSTANCES = []

    FIRST_PLACE_HEAD_X = -.24
    FIRST_PLACE_HEAD_Y = 0.013
    FIRST_PLACE_TEXT_X = 0

    FRAME_X = .31
    FRAME_Y_FIRST_PLACE = -.12

    PLACE_Y_OFFSET = .125

    # Called when a button on a row is clicked, instance is the actual instance that clicked this
    @classmethod
    def _clicked(cls, instance, _=None):

        # Loop through all instances
        for ins in cls.INSTANCES:
            # Skip the instance that clicked
            if ins is instance:
                continue

            # Another thing was clicked, force stop spectating if they were
            ins.stopSpectating()

        # Spectate!
        instance.attemptSpectateToon()

    def __init__(self, scoreboard_frame, avId, place=0, ruleset=None):

        DirectObject.__init__(self)

        self.ruleset = ruleset

        self.INSTANCES.append(self)

        # 0 based index based on what place they are in, y should be adjusted downwards
        self.place = place
        self.avId = avId
        self.points = 0
        self.roundWins = 0  # Track round wins for this toon
        self.damage, self.stuns, self.stomps = 0, 0, 0
        self.frame = DirectFrame(parent=scoreboard_frame)
        self.toon_head = self.createToonHead(avId, scale=.125)
        self.toon_head_button = DirectButton(parent=self.frame, pos=(self.FIRST_PLACE_HEAD_X, 0, self.FIRST_PLACE_HEAD_Y+.015), scale=.5,
                                             command=CashbotBossScoreboardToonRow._clicked, extraArgs=[self])
        self.toon_head_button.setTransparency(TransparencyAttrib.MAlpha)
        self.toon_head_button.setColorScale(1, 1, 1, 0)
        self.frame.setX(self.FRAME_X)
        self.frame.setZ(self.getYFromPlaceOffset(self.FRAME_Y_FIRST_PLACE))
        self.toon_head.reparentTo(self.frame)
        self.toon_head.setPos(self.FIRST_PLACE_HEAD_X, 0, self.FIRST_PLACE_HEAD_Y)
        self.toon_head.setH(180)
        self.toon_head.startBlink()
        self.points_text = DirectLabel(parent=self.frame, relief=None, text=str(self.points), text_shadow=(0, 0, 0, 1), text_fg=WHITE,
                                        text_align=TextNode.ABoxedCenter, text_scale=.09, pos=(self.FIRST_PLACE_TEXT_X, 0, 0), text_font=ToontownGlobals.getCompetitionFont())
        
        # Add round wins text (positioned between Pts and expandable stats)
        self.round_wins_text = DirectLabel(parent=self.frame, relief=None, text=str(self.roundWins), text_shadow=(0, 0, 0, 1), text_fg=WHITE,
                                           text_align=TextNode.ABoxedCenter, text_scale=.09, pos=(self.FIRST_PLACE_TEXT_X + .15, 0, 0), text_font=ToontownGlobals.getCompetitionFont())
        
        self.combo_text = DirectLabel(parent=self.frame, relief=None, text='x' + '0', text_shadow=(0, 0, 0, 1), text_fg=CYAN, text_align=TextNode.ACenter,
                                       text_scale=.055, pos=(self.FIRST_PLACE_HEAD_X + .1, 0, +.055), text_font=ToontownGlobals.getCompetitionFont())
        self.sad_text = DirectLabel(parent=self.frame, relief=None, text='SAD!', text_shadow=(0, 0, 0, 1), text_fg=RED, text_align=TextNode.ACenter,
                                     text_scale=.065, pos=(self.FIRST_PLACE_HEAD_X, 0, 0), hpr=(0, 0, -15), text_font=ToontownGlobals.getCompetitionFont())

        # Adjust extra stats position to make room for Wins column
        self.extra_stats_text = DirectLabel(parent=self.frame , relief=None, text='', text_shadow=(0, 0, 0, 1), text_fg=WHITE, text_align=TextNode.ABoxedCenter, text_scale=.09, pos=(self.FIRST_PLACE_TEXT_X+.62, 0, 0), text_font=ToontownGlobals.getCompetitionFont())


        self.combo_text.hide()
        self.sad_text.hide()
        if self.avId == base.localAvatar.doId:
            self.points_text['text_fg'] = GOLD
            self.round_wins_text['text_fg'] = GOLD
            self.extra_stats_text['text_fg'] = GOLD

        self.extra_stats_text.hide()
        # Round wins are always visible in best-of matches, will be hidden in single round matches

        self.sadSecondsLeft = -1

        self.isBeingSpectated = False

        # Set to true to actually handle spectate click events.
        self.allowSpectating = False

        self.inc_ival = None

        self._doLaterPointGains: list[CachedPointInstance] = []


    def enableSpectating(self):
        self.allowSpectating = True

    def disableSpectating(self):
        self.stopSpectating()
        self.allowSpectating = False

    def attemptSpectateToon(self):
        """
        Attempts to spectate this toon.

        There are multiple conditions where this method will do nothing:
        - The toon is not valid. (Not contained in the client repository)
        - the spectating mode is not enabled. Call self.enableSpectating() first.
        """

        # Is spectating enabled?
        if not self.allowSpectating:
            return

        # Toon exists?
        t = base.cr.doId2do.get(self.avId)
        if not t:
            return

        # Already spectating?
        if self.isBeingSpectated:
            self.stopSpectating()
            return

        # Spectate them
        self.__change_camera_angle(t)
        self.isBeingSpectated = True

        # Listen for any events where we should change the camera angle based on what the toon is doing that we are
        # spectating.
        self.accept('crane-enter-exit-%s' % self.avId, self.__change_camera_angle)

    def stopSpectating(self):

        if not self.isBeingSpectated:
            return

        localAvatar.attachCamera()
        localAvatar.orbitalCamera.start()
        localAvatar.setCameraFov(ToontownGlobals.BossBattleCameraFov)
        base.localAvatar.startUpdateSmartCamera()
        self.isBeingSpectated = False
        # Not spectating anymore, no need to watch for crane events any more
        self.ignore('crane-enter-exit-%s' % self.avId)

    def __change_camera_angle(self, toon, crane=None, _=None):

        base.localAvatar.stopUpdateSmartCamera()
        base.camera.reparentTo(render)
        # if crane is not None, then parent the camera to the crane, otherwise the toon
        if crane is None:

            # Fallback, if toon does not exist then just exit spectate
            if not toon:
                self.stopSpectating()
                return

            base.camera.reparentTo(toon)
            base.camera.setY(-12)
            base.camera.setZ(5)
            base.camera.setP(-5)
        else:
            base.camera.reparentTo(crane.hinge)
            camera.setPosHpr(0, -20, -5, 0, -20, 0)

    def getYFromPlaceOffset(self, y):
        return y - (self.PLACE_Y_OFFSET * self.place)

    def createToonHead(self, avId, scale=.15):
        head = ToonHead()
        av = base.cr.doId2do[avId]

        head.setupHead(av.style, forGui=1)

        head.setupToonHeadHat(av.getHat(), av.style.head)
        head.setupToonHeadGlasses(av.getGlasses(), av.style.head)

        head.fitAndCenterHead(scale, forGui=1)
        return head

    def cancel_inc_ival(self):
        if self.inc_ival:
            self.inc_ival.finish()

        self.inc_ival = None

    def addScore(self, amount, reason: CraneLeagueGlobals.ScoreReason, callback):

        # Check if the reason wants a delay
        if reason.want_delay():
            self._doLaterPointGains.append(CachedPointInstance(reason, amount, callback))
            # If this is the only thing queued up, start a new task
            if len(self._doLaterPointGains) == 1:
                taskMgr.doMethodLater(.5, self.__process_queued_points, f'queued-points-{self.avId}')
            return

        self.__addScore(amount, reason, callback)

    def __addScore(self, amount, reason, callback, task=None):
        # First update the amount
        old = self.points
        self.points += amount

        # find the difference
        diff = self.points - old

        # if we lost points make a red popup, if we gained green popup
        if diff > 0:
            doGainAnimation(self, diff, old, self.points, localAvFlag=self.avId == base.localAvatar.doId, reason=reason.value)
        elif diff < 0:
            doLossAnimation(self, diff, old, self.points, localAvFlag=self.avId == base.localAvatar.doId, reason=reason.value)

        # This is temporary until we bind the scoreboard to display the counts of certain "events"
        if reason == CraneLeagueGlobals.ScoreReason.GOON_STOMP:
            self.addStomp()
        elif reason == CraneLeagueGlobals.ScoreReason.DEFAULT:
            self.addDamage(amount)
        elif reason in (CraneLeagueGlobals.ScoreReason.STUN, CraneLeagueGlobals.ScoreReason.SIDE_STUN):
            self.addStun()

        callback()

    def __process_queued_points(self, task):

        if len(self._doLaterPointGains) <= 0:
            return task.done

        next = self._doLaterPointGains.pop(0)
        self.__addScore(next.amount, next.reason, next.callback)

        if len(self._doLaterPointGains) > 0:
            return task.again

        return task.done

    def flushQueuedPoints(self):
        taskMgr.remove(f'queued-points-{self.avId}')
        for points in self._doLaterPointGains:
            self.__addScore(points.amount, points.reason, points.callback)
        self._doLaterPointGains.clear()

    def updatePosition(self):
        # Move to new position based on place
        oldPos = Point3(self.frame.getX(), self.frame.getY(), self.frame.getZ())
        newPos = Point3(self.frame.getX(), self.frame.getY(), self.getYFromPlaceOffset(self.FRAME_Y_FIRST_PLACE))
        LerpPosInterval(self.frame, duration=.5, pos=newPos, startPos=oldPos, blendType='easeOut').start()

    def updateExtraStatsLabel(self):
        s = '%-7s %-7s %-7s' % (self.damage, self.stuns, self.stomps)
        self.extra_stats_text.setText(s)

    def addDamage(self, n):
        self.damage += n
        self.updateExtraStatsLabel()

    def addStun(self):
        self.stuns += 1
        self.updateExtraStatsLabel()

    def addStomp(self):
        self.stomps += 1
        self.updateExtraStatsLabel()

    def updateRoundWins(self, wins):
        """Update the round wins display for this toon"""
        self.roundWins = wins
        self.round_wins_text.setText(str(self.roundWins))

    def expand(self):
        self.updateExtraStatsLabel()
        self.extra_stats_text.show()

    def collapse(self):
        self.extra_stats_text.hide()

    def reset(self):
        if self.isBeingSpectated:
            self.stopSpectating()
        self.points = 0
        self.roundWins = 0
        self.damage = 0
        self.stuns = 0
        self.stomps = 0
        self.updateExtraStatsLabel()
        self.points_text.setText('0')
        self.round_wins_text.setText('0')
        self.combo_text.setText('COMBO x0')
        self.combo_text.hide()
        taskMgr.remove('sadtimer-' + str(self.avId))
        self.sad_text.hide()
        self.sad_text.setText('SAD!')
        self.cancel_inc_ival()

    def cleanup(self):
        self.flushQueuedPoints()
        if self.isBeingSpectated:
            self.stopSpectating()
        self.cancel_inc_ival()
        del self.inc_ival
        self.toon_head.cleanup()
        self.toon_head.removeNode()
        del self.toon_head
        self.points_text.destroy()
        self.points_text.removeNode()
        del self.points_text
        self.round_wins_text.destroy()
        self.round_wins_text.removeNode()
        del self.round_wins_text
        self.combo_text.destroy()
        self.combo_text.removeNode()
        del self.combo_text
        taskMgr.remove('sadtimer-' + str(self.avId))
        self.sad_text.destroy()
        self.sad_text.removeNode()
        del self.sad_text
        self.toon_head_button.destroy()
        self.toon_head_button.removeNode()
        del self.toon_head_button
        self.extra_stats_text.destroy()
        self.extra_stats_text.removeNode()
        del self.extra_stats_text
        del self.ruleset
        self.frame.destroy()
        self.frame.removeNode()
        del self.frame
        self.INSTANCES.remove(self)
        self.ignoreAll()

    def show(self):
        self.points_text.show()
        self.round_wins_text.show()
        self.toon_head.show()

    def hide(self):
        self.extra_stats_text.hide()
        self.points_text.hide()
        self.round_wins_text.hide()
        self.toon_head.hide()
        self.combo_text.hide()
        self.sad_text.hide()

    def toonDied(self):
        self.toon_head.sadEyes()
        self.sad_text.show()
        self.sadSecondsLeft = self.ruleset.REVIVE_TOONS_TIME

        if self.ruleset.REVIVE_TOONS_UPON_DEATH:
            taskMgr.remove('sadtimer-' + str(self.avId))
            taskMgr.add(self.__updateSadTimeLeft, 'sadtimer-' + str(self.avId))

    def toonRevived(self):
        self.toon_head.normalEyes()
        self.sad_text.hide()

    def __updateSadTimeLeft(self, task):

        if self.sadSecondsLeft < 0:
            return Task.done

        self.sad_text.setText(str(self.sadSecondsLeft))
        self.sadSecondsLeft -= 1
        task.delayTime = 1
        return Task.again


class CashbotBossScoreboard(DirectObject):

    def __init__(self, ruleset=None):
        DirectObject.__init__(self)

        self.ruleset = ruleset
        self.frame = DirectFrame(parent=base.a2dLeftCenter)
        self.frame.setPos(.2, 0, .5)

        self.default_row, self.default_row_path = getScoreboardTextRow(self.frame, 'master-row', default_text='%-10s %-7s\0' % ('Toon', 'Pts'))
        self.default_row_path.setScale(.06)

        self.rows = {}  # maps avId -> ScoreboardToonRow object
        self.accept('f1', self._consider_expand)

        self.is_expanded = False

        self.expand_tip = OnscreenText(parent=self.frame, text="Press F1 to show more stats", style=3, fg=WHITE, align=TextNode.ACenter, scale=.05, pos=(0.22, 0.1), font=ToontownGlobals.getCompetitionFont())
        self.expand_tip.hide()

        # Round tracking
        self.currentRound = 1
        self.bestOfValue = 1
        self.roundWins = {}
        self.roundInfoText = OnscreenText(parent=self.frame, text="", style=3, fg=WHITE, align=TextNode.ACenter, scale=.06, pos=(0.22, 0.65), font=ToontownGlobals.getCompetitionFont())
        self.roundInfoText.hide()

    def set_ruleset(self, ruleset):
        self.ruleset = ruleset
        for r in list(self.rows.values()):
            r.ruleset = ruleset

    def setRoundInfo(self, currentRound, roundWins, bestOfValue):
        """Update round information display"""
        self.currentRound = currentRound
        self.bestOfValue = bestOfValue
        
        # Convert roundWins list back to dict
        self.roundWins = {}
        for i, avId in enumerate(self.getToons()):
            if i < len(roundWins):
                self.roundWins[avId] = roundWins[i]
        
        # Update display
        if self.bestOfValue > 1:
            winsNeeded = (self.bestOfValue + 1) // 2
            roundText = f"Round {self.currentRound} (Best of {self.bestOfValue} - {winsNeeded} wins needed)"
            self.roundInfoText['text'] = roundText
            self.roundInfoText.show()
            
            # Update individual row displays with round wins using the new method
            for avId, row in self.rows.items():
                wins = self.roundWins.get(avId, 0)
                row.updateRoundWins(wins)
                row.round_wins_text.show()  # Make sure Wins column is visible
        else:
            self.roundInfoText.hide()
            # Hide round wins displays for single round matches
            for row in self.rows.values():
                row.round_wins_text.hide()

    def _consider_expand(self):

        if self.is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        self.is_expanded = True
        self.default_row.setText('%-10s %-9s %-6s %-7s %-7s %-8s\0' % ('Toon', 'Pts', 'Wins', 'Dmg', 'Stuns', 'Stomps'))
        for r in list(self.rows.values()):
            r.expand()

    def collapse(self):
        self.is_expanded = False
        self.default_row.setText('%-10s %-7s %-6s\0' % ('Toon', 'Pts', 'Wins'))
        for r in list(self.rows.values()):
            r.collapse()

    def addToon(self, avId):
        if avId not in self.rows and avId in base.cr.doId2do:
            self.rows[avId] = CashbotBossScoreboardToonRow(self.frame, avId, len(self.rows), ruleset=self.ruleset)
            
            # Set initial visibility of Wins column based on current best-of setting
            if self.bestOfValue > 1:
                self.rows[avId].round_wins_text.show()
            else:
                self.rows[avId].round_wins_text.hide()
                
        self.show()

    def clearToons(self):
        for row in list(self.rows.values()):
            row.cleanup()
            del self.rows[row.avId]
        self.hide()

    def addScore(self, avId, amount, reason: CraneLeagueGlobals.ScoreReason = CraneLeagueGlobals.ScoreReason.DEFAULT):
        """
        Adds score for a toon. Does additional checking and also will delay "special" point reasons if many are being
        received at once.
        """
        # If it is 0 (could be set by developer) don't do anything
        if amount == 0:
            return

        # Go ahead and add the score
        if avId in self.rows:
            self.rows[avId].addScore(amount, reason=reason, callback=self.updatePlacements)

    def updatePlacements(self):
        # make a list of all the objects
        rows = [r for r in list(self.rows.values())]
        # sort it based on how many points they have in descending order
        rows.sort(key=lambda x: x.points, reverse=True)
        # set place
        i = 0
        for r in rows:
            r.place = i
            r.updatePosition()
            i += 1

    def getToons(self):
        return [avId for avId in list(self.rows.keys())]

    def cleanup(self):
        self.clearToons()
        del self.default_row
        self.default_row_path.removeNode()
        del self.default_row_path
        self.roundInfoText.cleanup()
        self.roundInfoText.removeNode()
        del self.roundInfoText
        self.frame.destroy()
        self.frame.removeNode()
        del self.frame
        self.ignoreAll()
        taskMgr.remove('expand-tip')

    def hide_tip_later(self):
        taskMgr.remove('expand-tip')
        taskMgr.doMethodLater(5.0, self.__hide_tip, 'expand-tip')

    def __hide_tip(self, _=None):
        taskMgr.remove('expand-tip')
        LerpColorScaleInterval(self.expand_tip, 1.0, colorScale=(1, 1, 1, 0), startColorScale=(1, 1, 1, 1), blendType='easeInOut').start()

    def reset(self):
        self.expand_tip.show()
        self.expand_tip.setColorScale(1, 1, 1, 1)
        self.hide_tip_later()
        taskMgr.remove('expand-tip')
        for row in list(self.rows.values()):
            row.reset()

        self.updatePlacements()
        self.collapse()

    def show(self):
        self.expand_tip.show()
        self.expand_tip.setColorScale(1, 1, 1, 1)
        self.hide_tip_later()
        self.default_row_path.show()
        for row in list(self.rows.values()):
            row.show()

        self.collapse()

    def hide(self):
        self.expand_tip.hide()
        self.default_row_path.hide()
        for row in list(self.rows.values()):
            row.hide()

    # updates combo text
    def setCombo(self, avId, amount):

        row = self.rows.get(avId)
        if not row:
            return

        row.combo_text.setText('x' + str(amount))

        if amount < 2:
            row.combo_text.hide()
            return

        row.combo_text['text_fg'] = CYAN
        row.combo_text.show()

        Parallel(
            Sequence(
                LerpScaleInterval(row.combo_text, duration=.25, scale=1.07, startScale=1, blendType='easeInOut'),
                LerpScaleInterval(row.combo_text, duration=.25, startScale=1.07, scale=1, blendType='easeInOut')
            ),
            LerpColorScaleInterval(row.combo_text, duration=self.ruleset.COMBO_DURATION, colorScale=(1, 1, 1, 0),
                                   startColorScale=(1, 1, 1, 1))
        ).start()

    def toonDied(self, avId):
        row = self.rows.get(avId)
        if not row:
            return

        row.toonDied()

    def toonRevived(self, avId):
        row = self.rows.get(avId)
        if not row:
            return

        row.toonRevived()

    def addDamage(self, avId, n):
        row = self.rows.get(avId)
        if row:
            row.addDamage(n)

    def addStun(self, avId):
        row = self.rows.get(avId)
        if row:
            row.addStun()

    def addStomp(self, avId):
        row = self.rows.get(avId)
        if row:
            row.addStomp()

    def enableSpectating(self):
        """
        Allows this scoreboard to be clicked to spectate toons.
        """
        for row in self.rows.values():
            row.enableSpectating()

        if len(self.rows) > 0:
            firstRow = list(self.rows.values())[0]
            firstRow.attemptSpectateToon()

    def disableSpectating(self):
        """
        Disallows this scoreboard to be clicked to spectate toons.
        """
        for row in self.rows.values():
            row.disableSpectating()

    def finish(self):
        for row in self.rows.values():
            row.flushQueuedPoints()
