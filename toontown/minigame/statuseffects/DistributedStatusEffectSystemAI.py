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
        self.effectAppliedBy = {}  # Maps (objectId, statusEffect) -> avId who applied it

    # DO Methods to apply status effects to targets
    def b_applyStatusEffect(self, objectId, statusEffect, appliedByAvId=None):
        if not hasattr(self, 'game') or not self.game or not hasattr(self.game, 'ruleset') or not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        self.applyStatusEffect(objectId, statusEffect, appliedByAvId)
        self.d_applyStatusEffect(objectId, statusEffect)

    def d_applyStatusEffect(self, objectId, statusEffect):
        self.sendUpdate("applyStatusEffect", [objectId, statusEffect.toAstron()])

    def applyStatusEffect(self, objectId, statusEffect, appliedByAvId=None):
        currentStatusEffects = self.objectsWithStatusEffects.get(objectId, [])
        currentStatusEffects.append(statusEffect)
        self.objectsWithStatusEffects[objectId] = currentStatusEffects
        
        # Track who applied this effect
        if appliedByAvId is not None:
            self.effectAppliedBy[(objectId, statusEffect)] = appliedByAvId
        
        # Notify the object if it has status effect handling methods
        obj = self.air.getDo(objectId)
        if obj and hasattr(obj, 'onStatusEffectApplied'):
            obj.onStatusEffectApplied(statusEffect, appliedByAvId)
        
        self.notify.warning(f'Applied status effect {statusEffect}. All status effects: {self.objectsWithStatusEffects[objectId]}')

    # DO Methods to remove status effects from targets
    def b_removeStatusEffect(self, objectId, statusEffect):
        if not hasattr(self, 'game') or not self.game or not hasattr(self.game, 'ruleset') or not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
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
            
            # Clean up the appliedBy tracking
            effectKey = (objectId, statusEffect)
            if effectKey in self.effectAppliedBy:
                del self.effectAppliedBy[effectKey]
            
            # Notify the object if it has status effect handling methods
            obj = self.air.getDo(objectId)
            if obj and hasattr(obj, 'onStatusEffectRemoved'):
                obj.onStatusEffectRemoved(statusEffect)

    # DO Methods to check if objects have status effects
    def hasStatusEffect(self, objectId, statusEffect):
        if not hasattr(self, 'game') or not self.game or not hasattr(self.game, 'ruleset') or not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return False
        return statusEffect in self.objectsWithStatusEffects.get(objectId, [])

    def removeAllStatusEffects(self, objectId):
        if not hasattr(self, 'game') or not self.game or not hasattr(self.game, 'ruleset') or not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return
        for statusEffect in self.objectsWithStatusEffects.get(objectId, []):
            self.b_removeStatusEffect(objectId, statusEffect)

    def isObjectStatusEffected(self, objectId):
        if not hasattr(self, 'game') or not self.game or not hasattr(self.game, 'ruleset') or not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return False
        return len(self.objectsWithStatusEffects.get(objectId, [])) > 0
    
    def getStatusEffects(self, objectId):
        if not hasattr(self, 'game') or not self.game or not hasattr(self.game, 'ruleset') or not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return []
        return self.objectsWithStatusEffects.get(objectId, [])
    
    def getEffectAppliedBy(self, objectId, statusEffect):
        """Get the avId of the player who applied this status effect"""
        if not hasattr(self, 'game') or not self.game or not hasattr(self.game, 'ruleset') or not self.game.ruleset.WANT_ELEMENTAL_MASTERY_MODE:
            return None
        return self.effectAppliedBy.get((objectId, statusEffect))

    def cleanup(self):
        """Clean up all status effect tracking to prevent memory leaks"""
        # Clear all tracking dictionaries
        self.objectsWithStatusEffects.clear()
        self.effectAppliedBy.clear()
        
        # Break circular reference to game
        if hasattr(self, 'game'):
            self.game = None

    def delete(self):
        # Clean up all tracking before deletion
        self.cleanup()
        DistributedObjectAI.delete(self)