from typing import Dict, List, Optional, Any
from direct.task.TaskManagerGlobal import taskMgr
from direct.showbase.DirectObject import DirectObject
from .ElementalSystem import ElementType, SynergyType
import abc


class StatusEffect(abc.ABC):
    """Abstract base class for all status effects."""
    
    def __init__(self, target_id: int, duration: float, source_element: ElementType):
        self.target_id = target_id
        self.duration = duration
        self.source_element = source_element
        self.start_time = globalClock.getFrameTime()
        self.is_active = True
        self.tick_count = 0
    
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
        # Visual effect could be added here (fire particles, red tint, etc.)
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
            elif hasattr(target, 'b_setBossDamage'):
                # For CFO boss
                new_damage = target.bossDamage + int(self.damage_per_tick)
                target.b_setBossDamage(new_damage, avId=0, objId=0, isGoon=False)
    
    def remove_effect(self, target):
        """Remove the burn effect."""
        # Remove visual effects here
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
        if self.applied and self.original_speed is not None:
            if hasattr(target, 'setSpeed'):
                target.setSpeed(self.original_speed)
            elif hasattr(target, 'attackDelay'):
                target.attackDelay = self.original_speed
    
    def get_effect_name(self) -> str:
        return "Drench"


class ElementalEffectManager:
    """Manages all active elemental effects on targets."""
    
    def __init__(self):
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
                del self._active_effects[target_id]
                continue
            
            # Update each effect
            for effect in effects[:]:  # Use slice copy to avoid modification during iteration
                if effect.is_expired():
                    effect.remove_effect(target)
                    effects.remove(effect)
                else:
                    effect.tick_effect(target)
            
            # Remove target from dict if no effects remain
            if not effects:
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
        
        # Check for synergies with existing effects
        existing_effects = self._active_effects.get(target_id, [])
        self._check_synergies(effect, existing_effects, target)
        
        # Add the new effect
        if target_id not in self._active_effects:
            self._active_effects[target_id] = []
        
        self._active_effects[target_id].append(effect)
        effect.apply_effect(target)
    
    def _check_synergies(self, new_effect: StatusEffect, existing_effects: List[StatusEffect], target):
        """Check for synergies between the new effect and existing effects."""
        from .ElementalSystem import ElementalSystem, SynergyType
        
        # Create a temporary elemental system to check synergies
        elemental_system = ElementalSystem()
        
        for existing_effect in existing_effects[:]:  # Use slice copy
            synergy = elemental_system.check_synergy(new_effect.source_element, existing_effect.source_element)
            
            if synergy and synergy.synergy_type == SynergyType.NEGATIVE:
                # Negative synergy - cancel the existing effect
                if (new_effect.source_element == ElementType.WATER and 
                    existing_effect.source_element == ElementType.FIRE):
                    # Water cancels fire
                    existing_effect.remove_effect(target)
                    existing_effect.cancel()
                elif (new_effect.source_element == ElementType.FIRE and 
                      existing_effect.source_element == ElementType.WATER):
                    # Fire is cancelled by water (don't apply the new fire effect)
                    new_effect.cancel()
    
    def remove_effects_by_type(self, target_id: int, effect_type: type):
        """Remove all effects of a specific type from a target."""
        if target_id not in self._active_effects:
            return
        
        target = self._get_target(target_id)
        if target is None:
            return
        
        effects = self._active_effects[target_id]
        for effect in effects[:]:  # Use slice copy
            if isinstance(effect, effect_type):
                effect.remove_effect(target)
                effects.remove(effect)
        
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