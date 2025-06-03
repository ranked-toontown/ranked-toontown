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
        self._cancelled = True


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
                
                # Check if this is the AI version (which has d_setBossDamage method)
                if hasattr(target, 'd_setBossDamage'):
                    # AI version - call d_setBossDamage and setBossDamage separately to avoid recursion
                    target.d_setBossDamage(new_damage, avId=0, objId=0, isGoon=False, isDOT=True)
                    target.setBossDamage(new_damage)
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
    
    def __init__(self, target_id: int, speed_reduction: float = 0.25, duration: float = 5.0):
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


class WindedEffect(StatusEffect):
    """Wind elemental effect - passive effect that enables synergies."""
    
    def __init__(self, target_id: int, duration: float = 8.0):
        super().__init__(target_id, duration, ElementType.WIND)
    
    def apply_effect(self, target):
        """Apply the initial winded effect (passive)."""
        # Apply visual effects with wind color
        if hasattr(target, 'd_applyElementalVisualEffect'):
            target.d_applyElementalVisualEffect(ElementType.WIND.value)
        elif hasattr(target, 'applyElementalVisualEffect'):
            target.applyElementalVisualEffect(ElementType.WIND.value)
    
    def tick_effect(self, target):
        """Winded doesn't have a per-tick effect, just enables synergies."""
        pass
    
    def remove_effect(self, target):
        """Remove the winded effect."""
        # Remove visual effects
        if hasattr(target, 'd_removeElementalVisualEffect'):
            target.d_removeElementalVisualEffect()
        elif hasattr(target, 'removeElementalVisualEffect'):
            target.removeElementalVisualEffect()
    
    def get_effect_name(self) -> str:
        return "Winded"


class FreezeEffect(StatusEffect):
    """Freeze effect - created from Wind + Water synergy."""
    
    # Use a high value that won't conflict with normal element types (0-3)
    FREEZE_VISUAL_VALUE = 100
    
    def __init__(self, target_id: int, duration: float = 6.0):  # Changed to 6 seconds
        super().__init__(target_id, duration, ElementType.WATER)  # Use WATER as source for visual
        self.has_ended_stun = False
        self.original_attack_code = None
        self.notify = DirectNotifyGlobal.directNotify.newCategory('FreezeEffect')
    
    def apply_effect(self, target):
        """Apply the initial freeze effect and clear conflicting effects."""
        # Store original attack code and set to frozen
        if hasattr(target, 'attackCode') and hasattr(target, 'b_setAttackCode'):
            # For CFO boss - store current state and set to frozen
            from toontown.toonbase import ToontownGlobals
            self.original_attack_code = target.attackCode
            
            # End any active stun immediately (check for all stun states)
            if target.attackCode in ToontownGlobals.BossCogDizzyStates:
                self.has_ended_stun = True
                self.notify.info(f"Freeze ending stun state: {target.attackCode}")
            
            # Set to frozen state
            target.b_setAttackCode(ToontownGlobals.BossCogFrozen)
        
        # Clear conflicting elemental effects (Drench and Winded)
        self._clear_conflicting_effects(target)
        
        # Apply visual effects - try visual manager first (client side), then distributed calls (AI side)
        try:
            if hasattr(target, 'elementalVisualManager') and target.elementalVisualManager:
                # Client side - use visual manager with special effect
                target.elementalVisualManager.apply_special_effect(
                    target.doId if hasattr(target, 'doId') else self.target_id, 
                    'FREEZE', 
                    target
                )
            elif hasattr(target, 'd_applyElementalVisualEffect'):
                # AI side - use distributed call with special value
                target.d_applyElementalVisualEffect(self.FREEZE_VISUAL_VALUE)
            elif hasattr(target, 'applyElementalVisualEffect'):
                # Direct call
                target.applyElementalVisualEffect(self.FREEZE_VISUAL_VALUE)
        except Exception as e:
            self.notify.warning(f"Failed to apply freeze visual effect: {e}")
    
    def _clear_conflicting_effects(self, target):
        """Clear Drench and Winded effects that conflict with Freeze."""
        # Get the elemental effect manager from the target or game
        effect_manager = None
        target_id = target.doId if hasattr(target, 'doId') else self.target_id
        
        # Try to get effect manager from various sources
        if hasattr(target, 'game') and hasattr(target.game, 'elementalEffectManager'):
            effect_manager = target.game.elementalEffectManager
        elif hasattr(target, 'elementalEffectManager'):
            effect_manager = target.elementalEffectManager
        
        if effect_manager:
            # Remove Drench and Winded effects
            effect_manager.remove_effects_by_type(target_id, DrenchEffect)
            effect_manager.remove_effects_by_type(target_id, WindedEffect)
            self.notify.info("Freeze cleared conflicting Drench and Winded effects")
    
    def tick_effect(self, target):
        """Freeze doesn't have a per-tick effect."""
        pass
    
    def remove_effect(self, target):
        """Remove the freeze effect and restore original state."""
        # Restore original attack code, but never restore to a stun state
        if hasattr(target, 'attackCode') and hasattr(target, 'b_setAttackCode') and self.original_attack_code is not None:
            from toontown.toonbase import ToontownGlobals
            # Only restore if still frozen (prevents conflicts with other effects)
            if target.attackCode == ToontownGlobals.BossCogFrozen:
                # Never restore to a stun state - always go to no attack
                if self.original_attack_code in ToontownGlobals.BossCogDizzyStates:
                    target.b_setAttackCode(ToontownGlobals.BossCogNoAttack)
                    self.notify.info("Freeze ended - not restoring stun state, using BossCogNoAttack instead")
                else:
                    target.b_setAttackCode(self.original_attack_code)
                    self.notify.info(f"Freeze ended - restored original attack code: {self.original_attack_code}")
        
        # Remove visual effects - try visual manager first, then distributed calls
        try:
            if hasattr(target, 'elementalVisualManager') and target.elementalVisualManager:
                # Client side - use visual manager
                target.elementalVisualManager.remove_elemental_visual(
                    target.doId if hasattr(target, 'doId') else self.target_id
                )
            elif hasattr(target, 'd_removeElementalVisualEffect'):
                # AI side - use distributed call
                target.d_removeElementalVisualEffect()
            elif hasattr(target, 'removeElementalVisualEffect'):
                # Direct call
                target.removeElementalVisualEffect()
        except Exception as e:
            self.notify.warning(f"Failed to remove freeze visual effect: {e}")
    
    def get_effect_name(self) -> str:
        return "Freeze"


class ShatteredEffect(StatusEffect):
    """Shattered effect - 25% damage vulnerability."""
    
    # Use a high value that won't conflict with normal element types (0-3)
    SHATTERED_VISUAL_VALUE = 101
    
    def __init__(self, target_id: int, duration: float = 10.0):  # Increased to 10 seconds
        super().__init__(target_id, duration, ElementType.WATER)  # Use WATER as source for visual
        self.damage_multiplier = 1.25  # 25% more damage
        self.notify = DirectNotifyGlobal.directNotify.newCategory('ShatteredEffect')
    
    def apply_effect(self, target):
        """Apply the initial shattered effect and clear all conflicting effects."""
        # Clear ALL conflicting elemental effects before applying shatter
        self._clear_all_effects(target)
        
        # Apply visual effects - try visual manager first (client side), then distributed calls (AI side)
        try:
            if hasattr(target, 'elementalVisualManager') and target.elementalVisualManager:
                # Client side - use visual manager with special effect
                target.elementalVisualManager.apply_special_effect(
                    target.doId if hasattr(target, 'doId') else self.target_id, 
                    'SHATTERED', 
                    target
                )
            elif hasattr(target, 'd_applyElementalVisualEffect'):
                # AI side - use distributed call with special value
                target.d_applyElementalVisualEffect(self.SHATTERED_VISUAL_VALUE)
            elif hasattr(target, 'applyElementalVisualEffect'):
                # Direct call
                target.applyElementalVisualEffect(self.SHATTERED_VISUAL_VALUE)
        except Exception as e:
            self.notify.warning(f"Failed to apply shattered visual effect: {e}")
    
    def _clear_all_effects(self, target):
        """Clear all elemental effects that conflict with Shatter."""
        # Get the elemental effect manager from the target or game
        effect_manager = None
        target_id = target.doId if hasattr(target, 'doId') else self.target_id
        
        # Try to get effect manager from various sources
        if hasattr(target, 'game') and hasattr(target.game, 'elementalEffectManager'):
            effect_manager = target.game.elementalEffectManager
        elif hasattr(target, 'elementalEffectManager'):
            effect_manager = target.elementalEffectManager
        
        if effect_manager:
            # Remove all other elemental effects (Drench, Winded, Freeze)
            effect_manager.remove_effects_by_type(target_id, DrenchEffect)
            effect_manager.remove_effects_by_type(target_id, WindedEffect) 
            effect_manager.remove_effects_by_type(target_id, FreezeEffect)
            self.notify.info("Shattered cleared all conflicting elemental effects")
    
    def tick_effect(self, target):
        """Shattered doesn't have a per-tick effect."""
        pass
    
    def remove_effect(self, target):
        """Remove the shattered effect."""
        # Remove visual effects - try visual manager first, then distributed calls
        try:
            if hasattr(target, 'elementalVisualManager') and target.elementalVisualManager:
                # Client side - use visual manager
                target.elementalVisualManager.remove_elemental_visual(
                    target.doId if hasattr(target, 'doId') else self.target_id
                )
            elif hasattr(target, 'd_removeElementalVisualEffect'):
                # AI side - use distributed call
                target.d_removeElementalVisualEffect()
            elif hasattr(target, 'removeElementalVisualEffect'):
                # Direct call
                target.removeElementalVisualEffect()
        except Exception as e:
            self.notify.warning(f"Failed to remove shattered visual effect: {e}")
    
    def get_effect_name(self) -> str:
        return "Shattered"


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
        
        # Check for synergies with existing effects BEFORE applying anything
        cancelled_effects = self._check_synergies(effect, existing_effects, target)
        
        # Don't add the effect if it was cancelled by synergy
        if effect._cancelled:
            self.notify.debug(f"Effect {effect.get_effect_name()} cancelled by synergy - no visual effects applied")
            # Only update visuals if existing effects were removed
            if cancelled_effects:
                self._update_visual_effects(target_id, target)
            return
        
        # Add the new effect to the actual list only after synergy check passes
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
        
        # Special case: Fire/Burn should override Freeze immediately
        if isinstance(new_effect, BurnEffect):
            # Remove any freeze effects
            for existing_effect in existing_effects[:]:
                if isinstance(existing_effect, FreezeEffect):
                    self.notify.debug("Fire effect overriding existing freeze effect")
                    existing_effect.remove_effect(target)
                    existing_effect.cancel()
                    existing_effects.remove(existing_effect)
                    effects_removed.append(existing_effect)
        
        for existing_effect in existing_effects[:]:  # Use slice copy
            self.notify.debug(f"Checking synergy: {new_effect.source_element} vs {existing_effect.source_element}")
            synergy = elemental_system.check_synergy(new_effect.source_element, existing_effect.source_element)
            
            if synergy:
                if synergy.synergy_type == SynergyType.NEGATIVE:
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
                
                elif synergy.synergy_type == SynergyType.POSITIVE:
                    self.notify.debug(f"Positive synergy detected: {synergy.synergy_type}")
                    # Handle Wind + Fire synergy (explosion)
                    if ((new_effect.source_element == ElementType.WIND and existing_effect.source_element == ElementType.FIRE) or
                        (new_effect.source_element == ElementType.FIRE and existing_effect.source_element == ElementType.WIND)):
                        self.notify.debug("Wind + Fire synergy detected - scheduling explosion")
                        self._schedule_wind_fire_explosion(target, new_effect, existing_effect, existing_effects, effects_removed)
                    
                    # Handle Wind + Water synergy (freeze)
                    elif ((new_effect.source_element == ElementType.WIND and existing_effect.source_element == ElementType.WATER) or
                          (new_effect.source_element == ElementType.WATER and existing_effect.source_element == ElementType.WIND)):
                        self.notify.debug("Wind + Water synergy detected - scheduling freeze")
                        self._schedule_wind_water_freeze(target, new_effect, existing_effect, existing_effects, effects_removed)
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
        
        # Check for special effects that handle their own visuals
        has_special_effect = False
        for effect in effects:
            if isinstance(effect, (FreezeEffect, WindedEffect, ShatteredEffect)):
                has_special_effect = True
                break
        
        # If we have special effects, don't override their visuals
        if has_special_effect:
            self.notify.debug(f"Target {target_id} has special effects managing their own visuals")
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

    def _schedule_wind_fire_explosion(self, target, new_effect, existing_effect, existing_effects, effects_removed):
        """Schedule a Wind + Fire explosion after 0.5 seconds."""
        from direct.task.TaskManagerGlobal import taskMgr
        
        # Determine which effect is burn and which is winded
        burn_effect = new_effect if isinstance(new_effect, BurnEffect) else existing_effect
        wind_effect = new_effect if isinstance(new_effect, WindedEffect) else existing_effect
        
        # Get the avatars who inflicted each effect for credit
        burn_inflicter = burn_effect.target_id if hasattr(burn_effect, 'inflicter_id') else 0
        wind_inflicter = wind_effect.target_id if hasattr(wind_effect, 'inflicter_id') else 0
        
        def trigger_explosion():
            if not target:
                return
            
            # Calculate remaining DoT damage from burn effect
            remaining_ticks = max(0, (burn_effect.duration - (globalClock.getFrameTime() - burn_effect.start_time)) / burn_effect.tick_interval)
            remaining_damage = int(remaining_ticks * burn_effect.damage_per_tick)
            
            # Deal remaining DoT damage instantly (credited to burn inflicter)
            if remaining_damage > 0:
                self._apply_damage_to_target(target, remaining_damage, burn_inflicter, is_dot=True)
            
            # Deal explosion damage (credited to wind inflicter)
            explosion_damage = 35
            self._apply_damage_to_target(target, explosion_damage, wind_inflicter, is_dot=False)
            
            # Remove both effects
            if burn_effect in existing_effects:
                burn_effect.remove_effect(target)
                burn_effect.cancel()
                existing_effects.remove(burn_effect)
                effects_removed.append(burn_effect)
            
            if wind_effect in existing_effects:
                wind_effect.remove_effect(target)
                wind_effect.cancel()
                existing_effects.remove(wind_effect)
                effects_removed.append(wind_effect)
            
            # Update visuals
            self._update_visual_effects(target.doId if hasattr(target, 'doId') else 0, target)
            
            self.notify.info(f"Wind + Fire explosion: {remaining_damage} DoT + {explosion_damage} explosion damage")
        
        # Schedule the explosion for 0.5 seconds later
        task_name = f"wind_fire_explosion_{target.doId if hasattr(target, 'doId') else 'unknown'}"
        taskMgr.doMethodLater(0.5, lambda task: trigger_explosion(), task_name)

    def _schedule_wind_water_freeze(self, target, new_effect, existing_effect, existing_effects, effects_removed):
        """Schedule a Wind + Water freeze after 0.5 seconds."""
        from direct.task.TaskManagerGlobal import taskMgr
        
        # Determine which effect is drench and which is winded
        drench_effect = new_effect if isinstance(new_effect, DrenchEffect) else existing_effect
        wind_effect = new_effect if isinstance(new_effect, WindedEffect) else existing_effect
        
        def trigger_freeze():
            if not target:
                return
            
            # Remove both triggering effects
            if drench_effect in existing_effects:
                drench_effect.remove_effect(target)
                drench_effect.cancel()
                existing_effects.remove(drench_effect)
                effects_removed.append(drench_effect)
            
            if wind_effect in existing_effects:
                wind_effect.remove_effect(target)
                wind_effect.cancel()
                existing_effects.remove(wind_effect)
                effects_removed.append(wind_effect)
            
            # Apply freeze effect
            freeze_effect = FreezeEffect(target.doId if hasattr(target, 'doId') else 0)
            freeze_effect.apply_effect(target)
            existing_effects.append(freeze_effect)
            
            # Update visuals
            self._update_visual_effects(target.doId if hasattr(target, 'doId') else 0, target)
            
            self.notify.info("Wind + Water freeze applied")
        
        # Schedule the freeze for 0.5 seconds later
        task_name = f"wind_water_freeze_{target.doId if hasattr(target, 'doId') else 'unknown'}"
        taskMgr.doMethodLater(0.5, lambda task: trigger_freeze(), task_name)

    def _apply_damage_to_target(self, target, damage, inflicter_id, is_dot=False):
        """Helper method to apply damage to a target with proper credit attribution."""
        
        target_id = target.doId if hasattr(target, 'doId') else 0
        
        # Check if target is frozen and apply shattered logic
        if self.has_active_effect(target_id, FreezeEffect):
            freeze_effect = self.get_active_effect(target_id, FreezeEffect)
            if freeze_effect and not hasattr(freeze_effect, '_has_triggered_shatter'):
                # This is the first hit on a frozen target - apply 50% bonus damage and trigger shattered
                damage = int(damage * 1.5)  # 50% more damage
                freeze_effect._has_triggered_shatter = True
                
                # Remove freeze effect properly
                if target_id in self._active_effects:
                    effects = self._active_effects[target_id]
                    if freeze_effect in effects:
                        freeze_effect.remove_effect(target)
                        freeze_effect.cancel()
                        effects.remove(freeze_effect)
                
                # Apply shattered effect
                shattered_effect = ShatteredEffect(target_id)
                shattered_effect.apply_effect(target)
                self._active_effects[target_id].append(shattered_effect)
                
                # Update visuals
                self._update_visual_effects(target_id, target)
                
                self.notify.info(f"Frozen target hit - applied {damage} damage (50% bonus) and Shattered effect")
        
        # Check if target is shattered and apply damage vulnerability
        elif self.has_active_effect(target_id, ShatteredEffect):
            shattered_effect = self.get_active_effect(target_id, ShatteredEffect)
            if shattered_effect:
                damage = int(damage * shattered_effect.damage_multiplier)  # 25% more damage
                self.notify.info(f"Shattered target hit - applied {damage} damage (25% vulnerability bonus)")
        
        if hasattr(target, 'setBossDamage'):
            # For CFO boss - handle both client and AI versions
            new_damage = target.bossDamage + damage
            
            # Check if this is the AI version (which has d_setBossDamage method)
            if hasattr(target, 'd_setBossDamage'):
                # AI version - call d_setBossDamage and setBossDamage separately to avoid recursion
                target.d_setBossDamage(new_damage, avId=inflicter_id, objId=0, isGoon=False, isDOT=is_dot)
                target.setBossDamage(new_damage)
            else:
                # Client version - use setBossDamage
                target.setBossDamage(new_damage, avId=inflicter_id, objId=0, isGoon=False, isDOT=is_dot)
        elif hasattr(target, 'takeDamage'):
            # For other targets
            target.takeDamage(damage)

    def has_active_effect(self, target_id: int, effect_class) -> bool:
        """Check if a target has an active effect of a specific type."""
        if target_id not in self._active_effects:
            return False
        
        for effect in self._active_effects[target_id]:
            if isinstance(effect, effect_class) and not effect._cancelled:
                return True
        return False

    def get_active_effect(self, target_id: int, effect_class):
        """Get the active effect of a specific type for a target."""
        if target_id not in self._active_effects:
            return None
        
        for effect in self._active_effects[target_id]:
            if isinstance(effect, effect_class) and not effect._cancelled:
                return effect
        return None


class ElementalEffectFactory:
    """Factory for creating elemental effects based on element types."""
    
    @staticmethod
    def create_effect(element_type: ElementType, target_id: int, **kwargs) -> Optional[StatusEffect]:
        """Create an elemental effect based on the element type."""
        if element_type == ElementType.FIRE:
            return BurnEffect(target_id, **kwargs)
        elif element_type == ElementType.WATER:
            return DrenchEffect(target_id, **kwargs)
        elif element_type == ElementType.WIND:
            return WindedEffect(target_id, **kwargs)
        # Add more elements here as needed
        return None 