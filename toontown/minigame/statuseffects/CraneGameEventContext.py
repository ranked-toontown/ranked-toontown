from __future__ import annotations
import typing
if typing.TYPE_CHECKING:
    from toontown.minigame.craning import DistributedCraneGameAI
    from toontown.coghq import DistributedCashbotBossCraneAI
    from toontown.coghq import DistributedCashbotBossObjectAI
    from toontown.suit import DistributedCashbotBossStrippedAI
    from toontown.toon.DistributedToonAI import DistributedToonAI

from dataclasses import dataclass

@dataclass
class CraneGameBossHitContext:
    game: DistributedCraneGameAI.DistributedCraneGameAI
    boss: DistributedCashbotBossStrippedAI.DistributedCashbotBossStrippedAI
    crane: DistributedCashbotBossCraneAI.DistributedCashbotBossCraneAI
    object: DistributedCashbotBossObjectAI.DistributedCashbotBossObjectAI
    avatar: DistributedToonAI.DistributedToonAI
    impact: float
