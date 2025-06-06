from toontown.minigame.statuseffects.StatusEffectGlobals import StatusEffect, STATUS_EFFECT_COLORS
from direct.gui.DirectLabel import DirectLabel
from panda3d.core import Point3, Point2, TextNode
from direct.interval.IntervalGlobal import Sequence, Wait, LerpColorScaleInterval, Func
from toontown.toonbase import ToontownGlobals
from direct.distributed.DistributedObject import DistributedObject

class DistributedStatusEffectSystem(DistributedObject):
    def __init__(self, cr):
        DistributedObject.__init__(self, cr)
        self.activeEffectTexts = {}  # objectId -> {statusEffect -> DirectLabel}
        self.effectStacks = {}  # objectId -> {statusEffect -> int}

    def applyStatusEffect(self, objectId, statusEffect):
        effect = StatusEffect.fromAstron(statusEffect)
        if effect is None:
            return
        
        # Get the object from the distributed object cache
        obj = self.cr.getDo(objectId)
        if obj is None:
            return
        
        # Initialize tracking for this object if needed
        if objectId not in self.activeEffectTexts:
            self.activeEffectTexts[objectId] = {}
        
        # Initialize tracking for this object if needed
        if objectId not in self.effectStacks:
            self.effectStacks[objectId] = {}

        if effect in self.effectStacks[objectId]:
            self.effectStacks[objectId][effect] += 1
            self.activeEffectTexts[objectId][effect].setText(f'{effect.name} ({self.effectStacks[objectId][effect]})')
        else:
            self.effectStacks[objectId][effect] = 1
        
        # Don't create duplicate text for the same effect on the same object
        if effect in self.activeEffectTexts[objectId]:
            return
        
        # Get the color for this effect, default to white if not defined
        effectColor = STATUS_EFFECT_COLORS.get(effect, (1.0, 1.0, 1.0, 1.0))
        
        # Calculate height - try to get object bounds for proper positioning
        objHeight = 3.0  # Default height
        if hasattr(obj, 'getHeight'):
            objHeight = obj.getHeight()
        elif hasattr(obj, 'height'):
            objHeight = obj.height
        elif hasattr(obj, 'getBounds'):
            bounds = obj.getBounds()
            if bounds:
                objHeight = bounds.getRadius() * 1.05
        
        # Calculate vertical offset based on how many effects are already on this object
        numExistingEffects = len(self.activeEffectTexts[objectId])
        verticalOffset = objHeight + 2.0 + (numExistingEffects * 1.0)  # Stack effects vertically above object
        
        # Create the status effect text
        effectText = DirectLabel(
            text=effect.name,
            pos=(0, 0, verticalOffset),
            scale=1,
            text_fg=effectColor,
            text_shadow=(0, 0, 0, 0.5),  # Black shadow for readability
            parent=obj,
            text_align=TextNode.ACenter,
            relief=None  # No background
        )
        
        # Make the text always face the camera (billboarding)
        effectText.setBillboardPointEye()
        
        # Store the text so we can remove it later
        self.activeEffectTexts[objectId][effect] = effectText

    def removeStatusEffect(self, objectId, statusEffect):
        effect = StatusEffect.fromAstron(statusEffect)
        if effect is None:
            return
        
        if objectId not in self.effectStacks:
            return
        
        if effect not in self.effectStacks[objectId]:
            return
        
        if objectId not in self.activeEffectTexts:
            return
        
        if effect not in self.activeEffectTexts[objectId]:
            return
        
        self.effectStacks[objectId][effect] -= 1
        if self.effectStacks[objectId][effect] == 0:
            # Remove and cleanup the text
            effectText = self.activeEffectTexts[objectId][effect]
            effectText.destroy()
            del self.activeEffectTexts[objectId][effect]
            del self.effectStacks[objectId][effect]
            
            # Clean up the object entry if no more effects
            if not self.activeEffectTexts[objectId]:
                del self.activeEffectTexts[objectId]
        else:
            self.activeEffectTexts[objectId][effect].setText(f'{effect.name} ({self.effectStacks[objectId][effect]})')

        # Reposition remaining effects to fill the gap
        self._repositionEffectTexts(objectId)
    
    def _repositionEffectTexts(self, objectId):
        """Reposition remaining status effect texts to fill gaps when one is removed"""
        if objectId not in self.activeEffectTexts:
            return
        
        # Get the object to calculate its height (same logic as applyStatusEffect)
        obj = self.cr.getDo(objectId)
        if not obj:
            return
        
        # Calculate height - try to get object bounds for proper positioning
        objHeight = 3.0  # Default height
        if hasattr(obj, 'getHeight'):
            objHeight = obj.getHeight()
        elif hasattr(obj, 'height'):
            objHeight = obj.height
        elif hasattr(obj, 'getBounds'):
            bounds = obj.getBounds()
            if bounds:
                objHeight = bounds.getRadius() * 1.05
        
        effects = list(self.activeEffectTexts[objectId].values())
        for i, effectText in enumerate(effects):
            verticalOffset = objHeight + 2.0 + (i * 1.0)  # Match the spacing from applyStatusEffect
            effectText.setPos(0, 0, verticalOffset)
    
    def cleanup(self):
        """Clean up all status effect texts when the system is destroyed"""
        for objectId in list(self.activeEffectTexts.keys()):
            for effect in list(self.activeEffectTexts[objectId].keys()):
                effectText = self.activeEffectTexts[objectId][effect]
                effectText.destroy()
        self.activeEffectTexts.clear()

    def hasStatusEffect(self, objectId, statusEffect):
        return statusEffect in self.effectStacks.get(objectId, {})