from __future__ import annotations
from toontown.minigame.statuseffects.StatusEffectGlobals import StatusEffect
from direct.distributed.DistributedObjectAI import DistributedObjectAI
from toontown.minigame.statuseffects.CraneGameEventContext import CraneGameBossHitContext

class DistributedStatusEffectSystemAI(DistributedObjectAI):
    def __init__(self, game, air, *statusEffects: StatusEffect):
        DistributedObjectAI.__init__(self, air)
        self.game = game
        self.statusEffects = list(statusEffects)
        self.objectsWithStatusEffects = {}

    # DO Methods to apply status effects to targets
    def b_applyStatusEffect(self, objectId, statusEffect):
        if not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        self.applyStatusEffect(objectId, statusEffect)
        self.d_applyStatusEffect(objectId, statusEffect)

    def d_applyStatusEffect(self, objectId, statusEffect):
        self.sendUpdate("applyStatusEffect", [objectId, statusEffect.toAstron()])

    def applyStatusEffect(self, objectId, statusEffect):
        currentStatusEffects = self.objectsWithStatusEffects.get(objectId, [])
        currentStatusEffects.append(statusEffect)
        self.objectsWithStatusEffects[objectId] = currentStatusEffects
        self.notify.warning(f'Applied status effect {statusEffect}. All status effects: {self.objectsWithStatusEffects[objectId]}')

    # DO Methods to remove status effects from targets
    def b_removeStatusEffect(self, objectId, statusEffect):
        if not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        self.removeStatusEffect(objectId, statusEffect)
        self.d_removeStatusEffect(objectId, statusEffect)
    
    def d_removeStatusEffect(self, objectId, statusEffect):
        self.sendUpdate("removeStatusEffect", [objectId, statusEffect.toAstron()])

    def removeStatusEffect(self, objectId, statusEffect):
        currentStatusEffects = self.objectsWithStatusEffects.get(objectId, [])
        if statusEffect in currentStatusEffects:
            currentStatusEffects.remove(statusEffect)
            self.objectsWithStatusEffects[objectId] = currentStatusEffects
            if len(currentStatusEffects) == 0:
                del self.objectsWithStatusEffects[objectId]

    # DO Methods to check if objects have status effects
    def hasStatusEffect(self, objectId, statusEffect):
        if not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        return statusEffect in self.objectsWithStatusEffects.get(objectId, [])

    def removeAllStatusEffects(self, objectId):
        if not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        for statusEffect in self.objectsWithStatusEffects.get(objectId, []):
            self.b_removeStatusEffect(objectId, statusEffect)

    def isObjectStatusEffected(self, objectId):
        if not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        return len(self.objectsWithStatusEffects.get(objectId, [])) > 0
    
    def getStatusEffects(self, objectId):
        if not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        return self.objectsWithStatusEffects.get(objectId, [])