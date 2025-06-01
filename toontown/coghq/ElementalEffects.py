from typing import Dict, List, Optional, Any
from direct.task.TaskManagerGlobal import taskMgr
from direct.showbase.DirectObject import DirectObject
from .ElementalSystem import ElementType, SynergyType, ElementalSystem
import abc
from direct.directnotify import DirectNotifyGlobal


class StatusEffect(abc.ABC):
    """Abstract base class for all status effects."""
    
    def __init__(self, target_id: int, duration: float, source_element: ElementType):
        self.target_id = target_id
        self.duration = duration
        self.source_element = source_element
        self.start_time = globalClock.getFrameTime()
        self.is_active = True
        self.tick_count = 0
        self._cancelled = False
    
    @abc.abstractmethod
    def apply_effect(self, target):
        """Apply the initial effect to the target."""
        pass
    
    @abc.abstractmethod
    def tick_effect(self, target):
        """Apply the per-tick effect to the target."""
        pass
    
    @abc.abstractmethod
    def remove_effect(self, target):
        """Remove the effect from the target."""
        pass
    
    @abc.abstractmethod
    def get_effect_name(self) -> str:
        """Get the name of this effect."""
        pass
    
    def is_expired(self) -> bool:
        """Check if this effect has expired."""
        current_time = globalClock.getFrameTime()
        return (current_time - self.start_time) >= self.duration or not self.is_active
    
    def cancel(self):
        """Cancel this effect immediately."""
        self.is_active = False


class BurnEffect(StatusEffect):
    """Fire elemental effect - deals damage over time."""
    
    def __init__(self, target_id: int, total_damage: int = 20, duration: float = 5.0, tick_interval: float = 0.5):
        super().__init__(target_id, duration, ElementType.FIRE)
        self.total_damage = total_damage
        self.tick_interval = tick_interval
        self.damage_per_tick = total_damage / (duration / tick_interval)
        self.last_tick_time = self.start_time
    
    def apply_effect(self, target):
        """Apply the initial burn effect."""
        # Visual effects are now handled by the ElementalEffectManager
        pass
    
    def tick_effect(self, target):
        """Apply damage over time."""
        current_time = globalClock.getFrameTime()
        if current_time - self.last_tick_time >= self.tick_interval:
            self.last_tick_time = current_time
            self.tick_count += 1
            
            # Apply damage
            if hasattr(target, 'takeDamage'):
                target.takeDamage(int(self.damage_per_tick))
            elif hasattr(target, 'setBossDamage'):
                # For CFO boss - handle both client and AI versions
                new_damage = target.bossDamage + int(self.damage_per_tick)
                
                # Check if this is the AI version (which has b_setBossDamage method)
                if hasattr(target, 'b_setBossDamage'):
                    # AI version - use b_setBossDamage with isDOT parameter
                    target.b_setBossDamage(new_damage, avId=0, objId=0, isGoon=False, isDOT=True)
                else:
                    # Client version - use setBossDamage with isDOT parameter
                    target.setBossDamage(new_damage, avId=0, objId=0, isGoon=False, isDOT=True)
    
    def remove_effect(self, target):
        """Remove the burn effect."""
        # Visual effects are now handled by the ElementalEffectManager
        pass
    
    def get_effect_name(self) -> str:
        return "Burn"


class DrenchEffect(StatusEffect):
    """Water elemental effect - slows movement and actions."""
    
    def __init__(self, target_id: int, speed_reduction: float = 0.25, duration: float = 8.0):
        super().__init__(target_id, duration, ElementType.WATER)
        self.speed_reduction = speed_reduction  # 0.25 = 25% speed reduction
        self.original_speed = None
        self.applied = False
    
    def apply_effect(self, target):
        """Apply the initial drench effect."""
        # Visual effects are now handled by the ElementalEffectManager
        
        if hasattr(target, 'setSpeed'):
            # For toons
            self.original_speed = getattr(target, 'speed', 1.0)
            new_speed = self.original_speed * (1.0 - self.speed_reduction)
            target.setSpeed(new_speed)
            self.applied = True
        elif hasattr(target, 'attackDelay'):
            # For CFO boss - slow down attacks
            self.original_speed = getattr(target, 'attackDelay', 1.0)
            new_delay = self.original_speed / (1.0 - self.speed_reduction)  # Increase delay = slower attacks
            target.attackDelay = new_delay
            self.applied = True
    
    def tick_effect(self, target):
        """Drench doesn't have a per-tick effect, just maintains the slow."""
        pass
    
    def remove_effect(self, target):
        """Remove the drench effect and restore original speed."""
        # Visual effects are now handled by the ElementalEffectManager
        
        if self.applied and self.original_speed is not None:
            if hasattr(target, 'setSpeed'):
                target.setSpeed(self.original_speed)
            elif hasattr(target, 'attackDelay'):
                target.attackDelay = self.original_speed
    
    def get_effect_name(self) -> str:
        return "Drench"


class ElementalEffectManager:
    """
    Manages the application and removal of elemental effects.
    """
    
    def __init__(self):
        self.notify = DirectNotifyGlobal.directNotify.newCategory('ElementalEffectManager')
        self._active_effects: Dict[int, List[StatusEffect]] = {}  # target_id -> list of effects
        self._update_task_name = "elementalEffectsUpdate"
        self._enabled = False
    
    def enable(self):
        """Enable the effect manager and start the update task."""
        self._enabled = True
        self._start_update_task()
    
    def disable(self):
        """Disable the effect manager and clean up all effects."""
        self._enabled = False
        self._stop_update_task()
        self._clear_all_effects()
    
    def _start_update_task(self):
        """Start the periodic update task."""
        self._stop_update_task()
        taskMgr.add(self._update_effects, self._update_task_name)
    
    def _stop_update_task(self):
        """Stop the periodic update task."""
        taskMgr.remove(self._update_task_name)
    
    def _update_effects(self, task):
        """Update all active effects."""
        if not self._enabled:
            return task.done
        
        # Process all active effects
        for target_id, effects in list(self._active_effects.items()):
            target = self._get_target(target_id)
            if target is None:
                # Target no longer exists, remove all effects
                self.notify.debug(f"Target {target_id} no longer exists, cleaning up")
                del self._active_effects[target_id]
                continue
            
            effects_removed = False
            
            # Update each effect
            for effect in effects[:]:  # Use slice copy to avoid modification during iteration
                if effect.is_expired():
                    self.notify.debug(f"Effect {effect.get_effect_name()} expired on target {target_id}")
                    effect.remove_effect(target)
                    effects.remove(effect)
                    effects_removed = True
                else:
                    effect.tick_effect(target)
            
            # Update visuals if effects were removed
            if effects_removed:
                self.notify.debug(f"Updating visuals for target {target_id} after effect removal")
                self._update_visual_effects(target_id, target)
            
            # Remove target from dict if no effects remain
            if not effects:
                self.notify.debug(f"No effects remaining for target {target_id}, removing from tracking")
                del self._active_effects[target_id]
        
        return task.cont
    
    def _get_target(self, target_id: int):
        """Get the target object by ID."""
        # Try to get from distributed objects
        try:
            return simbase.air.getDo(target_id)
        except:
            # If simbase.air doesn't exist, try base.cr
            try:
                return base.cr.getDo(target_id)
            except:
                return None
    
    def apply_effect(self, target_id: int, effect: StatusEffect):
        """Apply a new effect to a target."""
        if not self._enabled:
            return
        
        target = self._get_target(target_id)
        if target is None:
            return
        
        # Get the actual effects list (not a copy)
        if target_id not in self._active_effects:
            self._active_effects[target_id] = []
        
        existing_effects = self._active_effects[target_id]
        
        # Check for synergies with existing effects
        cancelled_effects = self._check_synergies(effect, existing_effects, target)
        
        # Don't add the effect if it was cancelled by synergy
        if effect._cancelled:
            self.notify.debug(f"Effect {effect.get_effect_name()} cancelled by synergy")
            # Update visuals since existing effects may have been removed
            self._update_visual_effects(target_id, target)
            return
        
        # Add the new effect to the actual list
        existing_effects.append(effect)
        effect.apply_effect(target)
        
        # Apply visual effects based on the dominant element type
        self._update_visual_effects(target_id, target)
    
    def _check_synergies(self, new_effect: StatusEffect, existing_effects: List[StatusEffect], target):
        """Check for synergies between the new effect and existing effects."""
        
        # Create a temporary elemental system to check synergies
        elemental_system = ElementalSystem()
        effects_removed = []
        
        self.notify.debug(f"Checking synergies for new {new_effect.get_effect_name()} effect against {len(existing_effects)} existing effects")
        
        for existing_effect in existing_effects[:]:  # Use slice copy
            self.notify.debug(f"Checking synergy: {new_effect.source_element} vs {existing_effect.source_element}")
            synergy = elemental_system.check_synergy(new_effect.source_element, existing_effect.source_element)
            
            if synergy and synergy.synergy_type == SynergyType.NEGATIVE:
                self.notify.debug(f"Negative synergy detected: {synergy.synergy_type}")
                # Negative synergy - cancel effects appropriately
                if (new_effect.source_element == ElementType.WATER and 
                    existing_effect.source_element == ElementType.FIRE):
                    # Water cancels fire - remove existing fire effect
                    self.notify.debug("Water cancelling existing fire effect")
                    existing_effect.remove_effect(target)
                    existing_effect.cancel()
                    existing_effects.remove(existing_effect)
                    effects_removed.append(existing_effect)
                    self.notify.debug(f"Water effect cancelled existing fire effect")
                elif (new_effect.source_element == ElementType.FIRE and 
                      existing_effect.source_element == ElementType.WATER):
                    # Fire is cancelled by water - cancel the new fire effect
                    self.notify.debug("Fire being cancelled by existing water effect")
                    new_effect.cancel()
                    self.notify.debug(f"Fire effect cancelled by existing water effect")
            else:
                if synergy:
                    self.notify.debug(f"Non-negative synergy: {synergy.synergy_type}")
                else:
                    self.notify.debug("No synergy found")
        
        self.notify.debug(f"Synergy check complete: {len(effects_removed)} effects removed, new effect cancelled: {new_effect._cancelled}")
        return effects_removed
    
    def remove_effects_by_type(self, target_id: int, effect_type: type):
        """Remove all effects of a specific type from a target."""
        if target_id not in self._active_effects:
            return
        
        target = self._get_target(target_id)
        if target is None:
            return
        
        effects = self._active_effects[target_id]
        effects_removed = False
        
        for effect in effects[:]:  # Use slice copy
            if isinstance(effect, effect_type):
                effect.remove_effect(target)
                effects.remove(effect)
                effects_removed = True
        
        # Update visuals if effects were removed
        if effects_removed:
            self._update_visual_effects(target_id, target)
        
        # Clean up empty lists
        if not effects:
            del self._active_effects[target_id]
    
    def get_effects_on_target(self, target_id: int) -> List[StatusEffect]:
        """Get all active effects on a target."""
        return self._active_effects.get(target_id, []).copy()
    
    def has_effect_type(self, target_id: int, effect_type: type) -> bool:
        """Check if a target has a specific type of effect."""
        effects = self._active_effects.get(target_id, [])
        return any(isinstance(effect, effect_type) for effect in effects)
    
    def _clear_all_effects(self):
        """Clear all active effects."""
        for target_id, effects in self._active_effects.items():
            target = self._get_target(target_id)
            if target:
                for effect in effects:
                    effect.remove_effect(target)
        
        self._active_effects.clear()
    
    def _update_visual_effects(self, target_id: int, target):
        """Update visual effects based on all active effects on the target."""
        effects = self._active_effects.get(target_id, [])
        
        self.notify.debug(f"Updating visual effects for target {target_id}, {len(effects)} effects active")
        
        if not effects:
            # No effects - remove visuals using force removal to ensure cleanup
            self.notify.debug(f"No effects on target {target_id}, removing visuals")
            if hasattr(target, 'd_removeElementalVisualEffect'):
                target.d_removeElementalVisualEffect()
            elif hasattr(target, 'removeElementalVisualEffect'):
                target.removeElementalVisualEffect()
            
            # Also notify visual manager directly if available
            try:
                if hasattr(target, 'elementalVisualManager') and target.elementalVisualManager:
                    target.elementalVisualManager.force_remove_elemental_visual(target_id)
            except:
                pass
            return
        
        # Determine the dominant element type (priority: Fire > Water > None)
        dominant_element = ElementType.NONE
        for effect in effects:
            if effect.source_element == ElementType.FIRE:
                dominant_element = ElementType.FIRE
                break  # Fire has highest priority
            elif effect.source_element == ElementType.WATER and dominant_element == ElementType.NONE:
                dominant_element = ElementType.WATER
        
        self.notify.debug(f"Applying visual effect {dominant_element} to target {target_id}")
        
        # Apply visual effects for the dominant element
        if hasattr(target, 'd_applyElementalVisualEffect'):
            target.d_applyElementalVisualEffect(dominant_element.value)
        elif hasattr(target, 'applyElementalVisualEffect'):
            target.applyElementalVisualEffect(dominant_element.value)


class ElementalEffectFactory:
    """Factory for creating elemental effects based on element types."""
    
    @staticmethod
    def create_effect(element_type: ElementType, target_id: int, **kwargs) -> Optional[StatusEffect]:
        """Create an elemental effect based on the element type."""
        if element_type == ElementType.FIRE:
            return BurnEffect(target_id, **kwargs)
        elif element_type == ElementType.WATER:
            return DrenchEffect(target_id, **kwargs)
        # Add more elements here as needed
        return None 