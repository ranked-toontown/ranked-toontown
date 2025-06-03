from typing import Any

from direct.gui.DirectButton import DirectButton
from direct.gui.DirectFrame import DirectFrame
from direct.gui.DirectLabel import DirectLabel
from panda3d.core import TextNode

from toontown.archipelago.util.global_text_properties import get_raw_formatted_string, MinimalJsonMessagePart
from toontown.matchmaking.rank import Rank
from toontown.matchmaking.skill_profile_keys import SkillProfileKey
from toontown.shtiker.ShtikerPage import ShtikerPage
from toontown.toonbase import TTLocalizer, ToontownGlobals

class LeaderboardRow(DirectFrame):
    def __init__(self, parent, **kwargs):
        DirectFrame.__init__(self, parent, **kwargs)
        self.ranking: DirectLabel = DirectLabel(parent=self, relief=None, pos=(-15, 0, 0), text='#1', text_font=ToontownGlobals.getCompetitionFont(), text_align=TextNode.A_left)
        self.player_name: DirectLabel = DirectLabel(parent=self, relief=None, pos=(-12, 0, 0), text='name goes here', text_font=ToontownGlobals.getCompetitionFont(), text_align=TextNode.A_left)
        self.skill_rating: DirectLabel = DirectLabel(parent=self, relief=None, pos=(1, 0, 0), text='Plastic II (0000)', text_font=ToontownGlobals.getCompetitionFont(), text_align=TextNode.A_left)
        self.win_rate: DirectLabel = DirectLabel(parent=self, relief=None, pos=(12, 0, 0), text='69W-69L', text_font=ToontownGlobals.getCompetitionFont(), text_align=TextNode.A_left)

    def update(self, ranking: int, player_name: str, skill_rating: int, wins: int, games: int):
        self.setColorScale(1, 1, 1, 1)
        self.ranking['text'] = f"#{ranking}"
        name = player_name
        if len(name) >= 20:
            name = name[:20] + "..."
        self.player_name['text'] = name

        rank = Rank.get_from_skill_rating(skill_rating)
        sr_str = get_raw_formatted_string([MinimalJsonMessagePart(message=f"({skill_rating})", color='gray')])
        self.skill_rating['text'] = f"{rank.colored()} {sr_str}"
        losses = games - wins
        self.win_rate['text'] = f"{wins}W-{losses}L"

    def loading(self):
        self.setColorScale(.5, .5, .5, 1)
        self.ranking['text'] = f"#?"
        self.player_name['text'] = f"Loading..."
        self.skill_rating['text'] = f""
        self.win_rate['text'] = f""

    def empty(self):
        self.setColorScale(.5, .5, .5, 1)
        self.ranking['text'] = f"#?"
        self.player_name['text'] = f"Nobody yet!"
        self.skill_rating['text'] = f""
        self.win_rate['text'] = f""

    def destroy(self):
        super().destroy()
        self.ranking.destroy()
        self.player_name.destroy()
        self.skill_rating.destroy()
        self.win_rate.destroy()


class LeaderboardPage(ShtikerPage):

    PLAYER_ROW_AMOUNT = 10
    ROW_Y_OFFSET = -.075

    def __init__(self):
        super().__init__()
        self.title: DirectLabel | None = None
        self.rows: list[LeaderboardRow] = []
        self.current_mode: SkillProfileKey = SkillProfileKey.CRANING_SOLOS
        self._mode_previous_button: DirectButton | None = None
        self._mode_next_button: DirectButton | None = None
        self._mode_label: DirectLabel | None = None
        self._top_ranking: int = 1  # Used to query which ranks we want to start displaying.

    def load(self):
        ShtikerPage.load(self)

        gui = loader.loadModel('phase_3/models/gui/create_a_toon_gui')
        arrows = (gui.find('**/CrtATn_R_Arrow_UP'),
                  gui.find('**/CrtATn_R_Arrow_DN'),
                  gui.find('**/CrtATn_R_Arrow_RLVR'),
                  gui.find('**/CrtATn_R_Arrow_UP'))

        self.title = DirectLabel(parent=self, relief=None, text=TTLocalizer.LeaderboardPageTitle, text_scale=0.12, textMayChange=1, pos=(0, 0, 0.62), text_font=ToontownGlobals.getCompetitionFont())
        self._mode_previous_button = DirectButton(
                parent=self, relief=None, pos=(-.55, 0, .45),
                text="Previous",
                scale=.5,
                text_scale=0.06,
                text_align=TextNode.ACenter,
                image=arrows,
                image_scale=(-1, 1, 1),
                command=lambda: self.__change_gamemode(-1)
        )
        self._mode_next_button = DirectButton(
                parent=self, relief=None, pos=(.55, 0, .45),
                text="Next",
                scale=.5,
                text_scale=0.06,
                text_align=TextNode.ACenter,
                image=arrows,
                image_scale=(1, 1, 1),
                command=lambda: self.__change_gamemode(1)
        )
        self._mode_label = DirectLabel(parent=self, relief=None, text="No Mode Selected", text_scale=0.09,
                                       textMayChange=1, pos=(0, 0, 0.43), text_align=TextNode.ACenter,
                                       text_font=ToontownGlobals.getCompetitionFont())

        for i in range(LeaderboardPage.PLAYER_ROW_AMOUNT):
            self.rows.append(LeaderboardRow(parent=self, pos=(0, 0, i * LeaderboardPage.ROW_Y_OFFSET + .3), scale=.055))

        gui.removeNode()

    def enter(self):
        super().enter()
        self.__set_gamemode(SkillProfileKey.CRANING_SOLOS)

    def exit(self):
        super().exit()
        base.cr.leaderboardManager.clearRankingsCache()
        self.ignore('leaderboard-ranking-response')

    def unload(self):
        if self.title is not None:
            self.title.destroy()
        self.title = None
        for row in self.rows:
            row.destroy()

        self._mode_label.destroy()
        self._mode_previous_button.destroy()
        self._mode_next_button.destroy()

    def __change_gamemode(self, delta: int):

        # Update the member by doing some indexing math.
        modes = list(SkillProfileKey)
        index = modes.index(self.current_mode)
        new_mode = modes[(index + delta) % len(modes)]

        # Update to new mode.
        self.__set_gamemode(new_mode)

    def __set_gamemode(self, gamemode: SkillProfileKey):

        self.ignore('leaderboard-ranking-response')
        self.acceptOnce('leaderboard-ranking-response', self.__handle_rankings_update)

        self.current_mode = gamemode

        # Update required UI elements.
        self._mode_label['text'] = gamemode.name.replace('_', ' ').title()
        for row in self.rows:
            row.loading()

        # Attempts to see if anything is already cached for what we are currently querying. If not, UD will be contacted
        # and we will update later.
        results = base.cr.leaderboardManager.getRankings(self.current_mode, self._top_ranking, 10)

        # Did we already have it cached?
        if len(results) == 10:
            self.__handle_rankings_update(self.current_mode.value, results)

    def __handle_rankings_update(self, key: str, results: list[Any]):
        """
        If we are running this method, it means we requested data from UD and didn't cancel it yet. So we can assume
        that we are still viewing the page that is relevant to the data receieved.
        """

        self.notify.debug(f"Applying {key} update using results {results}")
        # Empty all rows just in case we don't have data.
        for row in self.rows:
            row.empty()

        # Assign data to rows if it exists.
        for i, row in enumerate(self.rows):
            if i >= len(results):
                continue
            ranking, name, sr, wins, games = results[i]
            row.update(ranking, name, sr, wins, games)