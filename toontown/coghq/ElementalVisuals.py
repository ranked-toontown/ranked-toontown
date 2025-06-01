"""
Elemental Visual Effects System

This module handles all visual effects for elemental objects in the game,
focusing on color tinting with placeholder functions for future particle effects.
"""

from typing import Dict, Optional, Any
from .ElementalSystem import ElementType
from direct.showbase.DirectObject import DirectObject
from direct.task.TaskManagerGlobal import taskMgr
from panda3d.core import *
from direct.interval.IntervalGlobal import LerpColorScaleInterval, Sequence, Wait, Func


class ElementalVisualState:
    """Tracks the visual state of an object to prevent conflicts and accumulation."""
    
    def __init__(self):
        self.current_element = ElementType.NONE
        self.color_interval = None
        self.last_update_time = 0
        self.reference_count = 0  # Track how many effects want this visual state
        self.base_color_scale = (1.0, 1.0, 1.0, 1.0)  # Store base color for additive scaling
        self.elemental_color_scale = (1.0, 1.0, 1.0, 1.0)  # Store elemental color component
    
    def cleanup(self):
        """Clean up all visual effects and intervals."""
        if self.color_interval:
            # Remove the color maintenance task
            taskMgr.remove(self.color_interval)
            self.color_interval = None
        
        self.current_element = ElementType.NONE
        self.reference_count = 0
        self.elemental_color_scale = (1.0, 1.0, 1.0, 1.0)


class ElementalVisualManager(DirectObject):
    """
    Manages visual effects for elemental objects with simple color tinting.
    
    Provides reliable color effects and placeholder functions for future particle systems.
    """
    
    def __init__(self):
        DirectObject.__init__(self)
        self.visual_states: Dict[int, ElementalVisualState] = {}
        self.debounce_delay = 0.05  # Very short debounce for responsiveness
        
    def apply_elemental_visual(self, obj, element_type: int, object_id: int):
        """
        Apply visual effects with proper state management.
        
        Args:
            obj: The object to apply effects to
            element_type: Integer representing the element (0=None, 1=Fire, 2=Water)
            object_id: Unique identifier for state tracking
        """
        current_time = globalClock.getFrameTime()
        
        # Get or create visual state for this object
        if object_id not in self.visual_states:
            self.visual_states[object_id] = ElementalVisualState()
        
        state = self.visual_states[object_id]
        requested_element = ElementType(element_type) if element_type != 0 else ElementType.NONE
        
        # Debounce rapid updates
        if current_time - state.last_update_time < self.debounce_delay:
            if requested_element == state.current_element:
                state.reference_count += 1
            return
        
        state.last_update_time = current_time
        
        # Handle element removal (when element_type is 0 or ElementType.NONE)
        if requested_element == ElementType.NONE:
            # Force remove all visual effects
            self._cleanup_visual_state(state, obj)
            obj.setColorScale(state.base_color_scale)
            state.current_element = ElementType.NONE
            state.reference_count = 0
            return
        
        # If already showing the correct element, just increment reference count
        if state.current_element == requested_element:
            state.reference_count += 1
            return
        
        # Different element requested - clean up current and apply new
        self._cleanup_visual_state(state, obj)
        
        # Apply new visual effects
        if requested_element == ElementType.FIRE:
            self._apply_fire_visual(obj, state)
            state.current_element = ElementType.FIRE
            state.reference_count = 1
        elif requested_element == ElementType.WATER:
            self._apply_water_visual(obj, state)
            state.current_element = ElementType.WATER
            state.reference_count = 1
    
    def remove_elemental_visual(self, object_id: int):
        """Remove visual effects with proper reference counting."""
        if object_id not in self.visual_states:
            return
        
        state = self.visual_states[object_id]
        
        # Decrease reference count
        state.reference_count = max(0, state.reference_count - 1)
        
        # Only clean up if no more references
        if state.reference_count <= 0:
            # Get the object and clear color scale
            obj = self._get_object_from_id(object_id)
            if obj:
                obj.setColorScale(state.base_color_scale)
            
            # Always clean up the state even if object not found
            state.cleanup()
            del self.visual_states[object_id]
    
    def set_elemental_visual_to_element(self, object_id: int, element_type: int, obj=None):
        """Set the visual effect to a specific element, bypassing reference counting."""
        if obj is None:
            obj = self._get_object_from_id(object_id)
        if not obj:
            return
        
        # Get or create visual state for this object
        if object_id not in self.visual_states:
            self.visual_states[object_id] = ElementalVisualState()
        
        state = self.visual_states[object_id]
        requested_element = ElementType(element_type) if element_type != 0 else ElementType.NONE
        
        # If we're removing effects (ElementType.NONE), do a smooth fade out
        if requested_element == ElementType.NONE:
            self._smooth_fade_to_base(state, obj)
            state.current_element = ElementType.NONE
            state.reference_count = 0
            return
        
        # If changing to a different element, clean up current and apply new
        if state.current_element != requested_element:
            self._cleanup_visual_state(state, obj)
            
            # Wait a bit for fade out to complete before applying new effect
            task_name = f'delayedElementalApplication-{id(obj)}'
            def apply_new_element(task):
                if requested_element == ElementType.FIRE:
                    self._apply_fire_visual(obj, state)
                    state.current_element = ElementType.FIRE
                    state.reference_count = 1
                elif requested_element == ElementType.WATER:
                    self._apply_water_visual(obj, state)
                    state.current_element = ElementType.WATER
                    state.reference_count = 1
                return task.done
            
            taskMgr.doMethodLater(0.35, apply_new_element, task_name)
        else:
            # Same element, just maintain it
            state.reference_count = 1
    
    def force_remove_elemental_visual(self, object_id: int):
        """Force remove visual effects regardless of reference count."""
        if object_id not in self.visual_states:
            return
        
        state = self.visual_states[object_id]
        obj = self._get_object_from_id(object_id)
        if obj:
            # Use smooth fade out instead of instant removal
            self._smooth_fade_to_base(state, obj)
        
        # Clean up the state after a delay to allow fade out to complete
        task_name = f'delayedCleanup-{object_id}'
        def delayed_cleanup(task):
            state.cleanup()
            if object_id in self.visual_states:
                del self.visual_states[object_id]
            return task.done
        
        taskMgr.doMethodLater(0.5, delayed_cleanup, task_name)
    
    def cleanup_all_effects(self):
        """Remove all active visual effects."""
        for object_id in list(self.visual_states.keys()):
            state = self.visual_states[object_id]
            obj = self._get_object_from_id(object_id)
            if obj:
                obj.setColorScale(state.base_color_scale)
            state.cleanup()
        
        self.visual_states.clear()
    
    def _get_object_from_id(self, object_id: int):
        """Get object by ID from the distributed object registry."""
        # Try multiple ways to find the object
        
        # Method 1: Try client side first
        try:
            if hasattr(base, 'cr') and base.cr:
                obj = base.cr.getDo(object_id)
                if obj:
                    return obj
        except:
            pass
        
        # Method 2: Try AI side
        try:
            if hasattr(simbase, 'air') and simbase.air:
                obj = simbase.air.getDo(object_id)
                if obj:
                    return obj
        except:
            pass
        
        # Method 3: Try looking in base.cr.doId2do directly
        try:
            if hasattr(base, 'cr') and hasattr(base.cr, 'doId2do'):
                obj = base.cr.doId2do.get(object_id)
                if obj:
                    return obj
        except:
            pass
        
        # Method 4: Try global doId2do if it exists
        try:
            if 'doId2do' in globals():
                obj = doId2do.get(object_id)
                if obj:
                    return obj
        except:
            pass
        
        return None
    
    def _cleanup_visual_state(self, state: ElementalVisualState, obj):
        """Clean up current visual state before applying new effects."""
        if state.color_interval:
            # Remove the color maintenance task
            taskMgr.remove(state.color_interval)
            state.color_interval = None
        
        # Reset to base color scale with smooth fade out
        if obj:
            # Smooth fade out to base color
            current_color = obj.getColorScale()
            fade_out_interval = LerpColorScaleInterval(
                obj, 
                duration=0.3,  # Slightly faster fade out
                colorScale=state.base_color_scale,
                startColorScale=current_color,
                blendType='easeInOut'
            )
            fade_out_interval.start()
            
            state.elemental_color_scale = (1.0, 1.0, 1.0, 1.0)
    
    def _apply_fire_visual(self, obj, state: ElementalVisualState):
        """Apply fire visual effects - COLOR ONLY with smooth glow."""
        # More subtle fire glow - warm orange with less intensity
        fire_tint = (1.15, 0.85, 0.7, 1.0)  # Subtle warm orange glow
        
        # Clean up any existing color interval
        if state.color_interval:
            taskMgr.remove(state.color_interval)
            state.color_interval = None
        
        # Smooth fade in to fire color
        current_color = obj.getColorScale()
        fade_in_interval = LerpColorScaleInterval(
            obj, 
            duration=0.5,  # Half second fade in
            colorScale=fire_tint,
            startColorScale=current_color,
            blendType='easeInOut'
        )
        fade_in_interval.start()
        
        state.elemental_color_scale = fire_tint
        
        # Set up a persistent task to maintain the color after fade in
        task_name = f'maintainFireColor-{id(obj)}'
        def maintain_fire_color(task):
            if obj and not obj.isEmpty():
                # Reapply fire color if it's been changed (but not during transitions)
                current_color = obj.getColorScale()
                if (abs(current_color[0] - fire_tint[0]) > 0.15 or 
                    abs(current_color[1] - fire_tint[1]) > 0.15 or 
                    abs(current_color[2] - fire_tint[2]) > 0.15):
                    # Only reapply if the difference is significant (avoiding interference with other effects)
                    obj.setColorScale(fire_tint)
                return task.cont
            return task.done
        
        # Start maintenance task after fade in completes
        taskMgr.doMethodLater(0.6, maintain_fire_color, task_name)
        state.color_interval = task_name  # Store task name for cleanup
        
        # TODO: Add fire particle effects here when needed
        self._create_fire_particles_placeholder(obj, state)
    
    def _apply_water_visual(self, obj, state: ElementalVisualState):
        """Apply water visual effects - COLOR ONLY with smooth glow."""
        # More subtle water glow - cool blue with less intensity
        water_tint = (0.85, 0.95, 1.1, 1.0)  # Subtle cool blue glow
        
        # Clean up any existing color interval
        if state.color_interval:
            taskMgr.remove(state.color_interval)
            state.color_interval = None
        
        # Smooth fade in to water color
        current_color = obj.getColorScale()
        fade_in_interval = LerpColorScaleInterval(
            obj, 
            duration=0.5,  # Half second fade in
            colorScale=water_tint,
            startColorScale=current_color,
            blendType='easeInOut'
        )
        fade_in_interval.start()
        
        state.elemental_color_scale = water_tint
        
        # Set up a persistent task to maintain the color after fade in
        task_name = f'maintainWaterColor-{id(obj)}'
        def maintain_water_color(task):
            if obj and not obj.isEmpty():
                # Reapply water color if it's been changed (but not during transitions)
                current_color = obj.getColorScale()
                if (abs(current_color[0] - water_tint[0]) > 0.15 or 
                    abs(current_color[1] - water_tint[1]) > 0.15 or 
                    abs(current_color[2] - water_tint[2]) > 0.15):
                    # Only reapply if the difference is significant
                    obj.setColorScale(water_tint)
                return task.cont
            return task.done
        
        # Start maintenance task after fade in completes
        taskMgr.doMethodLater(0.6, maintain_water_color, task_name)
        state.color_interval = task_name  # Store task name for cleanup
        
        # TODO: Add water particle effects here when needed
        self._create_water_particles_placeholder(obj, state)
    
    def _create_fire_particles_placeholder(self, obj, state: ElementalVisualState):
        """Placeholder for fire particle effects - currently does nothing."""
        # Future implementation:
        # - Create fire particle system
        # - Attach to object
        # - Store in state for cleanup
        pass
    
    def _create_water_particles_placeholder(self, obj, state: ElementalVisualState):
        """Placeholder for water particle effects - currently does nothing."""
        # Future implementation:
        # - Create water particle system (bubbles, mist, etc.)
        # - Attach to object
        # - Store in state for cleanup
        pass

    def _smooth_fade_to_base(self, state: ElementalVisualState, obj):
        """Smoothly fade the object back to its base color."""
        if state.color_interval:
            taskMgr.remove(state.color_interval)
            state.color_interval = None
        
        if obj:
            current_color = obj.getColorScale()
            fade_out_interval = LerpColorScaleInterval(
                obj, 
                duration=0.4,  # Smooth fade out
                colorScale=state.base_color_scale,
                startColorScale=current_color,
                blendType='easeInOut'
            )
            fade_out_interval.start()
            
            state.elemental_color_scale = (1.0, 1.0, 1.0, 1.0)


class ElementalVisualFactory:
    """Factory class for creating elemental visual managers."""
    
    @staticmethod
    def create_visual_manager() -> ElementalVisualManager:
        """Create a new ElementalVisualManager instance."""
        return ElementalVisualManager() 