"""
Elemental Visual Effects System - Foolproof Color Management

This module provides bulletproof color tinting using proper Panda3D patterns,
state management, and cleanup procedures. Based on comprehensive analysis
of Panda3D color manipulation throughout the Toontown codebase.
"""

from typing import Dict, Optional, Any, Tuple
from .ElementalSystem import ElementType
from direct.showbase.DirectObject import DirectObject
from direct.task.TaskManagerGlobal import taskMgr
from direct.directnotify import DirectNotifyGlobal
from panda3d.core import *
from direct.interval.IntervalGlobal import LerpColorScaleInterval, Sequence, Wait, Func


class ColorState:
    """
    Tracks complete color state for an object to enable foolproof restoration.
    
    This follows the pattern used in battle movies and other Toontown systems
    for reliable color state management.
    """
    
    def __init__(self, node_path):
        """Initialize color state by capturing current state."""
        self.node_path = node_path
        self.capture_base_state()
        self.elemental_active = False
        self.elemental_type = ElementType.NONE
        self.active_interval = None
        self.maintenance_task = None
        
    def capture_base_state(self):
        """Capture the base color state of the object."""
        if not self.node_path or self.node_path.isEmpty():
            self.base_color_scale = (1.0, 1.0, 1.0, 1.0)
            self.base_transparency = False
            return
            
        # Capture current color scale
        current_scale = self.node_path.getColorScale()
        self.base_color_scale = (current_scale[0], current_scale[1], current_scale[2], current_scale[3])
        
        # Capture transparency state
        self.base_transparency = self.node_path.hasTransparency()
        
    def is_valid(self):
        """Check if the node path is still valid."""
        return self.node_path and not self.node_path.isEmpty()
    
    def cleanup(self):
        """Clean up all intervals and tasks."""
        if self.active_interval:
            self.active_interval.finish()
            self.active_interval = None
            
        if self.maintenance_task:
            taskMgr.remove(self.maintenance_task)
            self.maintenance_task = None


class ElementalColorManager(DirectObject):
    """
    Foolproof color management system for elemental effects.
    
    Key design principles:
    1. Always capture and restore base state
    2. Use proper Panda3D color scaling (multiplicative)
    3. Handle transparency correctly
    4. Prevent color accumulation
    5. Provide reliable cleanup
    """
    
    # Elemental color definitions (following Panda3D 0.0-1.0 range)
    ELEMENTAL_COLORS = {
        ElementType.FIRE: (1.4, 0.7, 0.4, 1.0),     # Warm orange glow - more intense
        ElementType.WATER: (0.7, 0.9, 1.4, 1.0),    # Cool blue glow - more intense
        ElementType.NONE: (1.0, 1.0, 1.0, 1.0),     # Neutral/base color
    }
    
    # Animation timing
    FADE_IN_TIME = 0.3    # Fast fade in for responsiveness
    FADE_OUT_TIME = 0.4   # Slightly slower fade out for smoothness
    
    def __init__(self):
        DirectObject.__init__(self)
        self.color_states: Dict[int, ColorState] = {}
        self.notify = DirectNotifyGlobal.directNotify.newCategory('ElementalColorManager')
        
    def apply_elemental_color(self, object_id: int, element_type: ElementType, node_path=None):
        """
        Apply elemental color tinting with proper state management.
        
        Args:
            object_id: Unique identifier for the object
            element_type: The element type to apply
            node_path: The NodePath to apply effects to (optional, will auto-detect)
        """
        if not node_path:
            node_path = self._get_node_path(object_id)
            
        if not node_path or node_path.isEmpty():
            self.notify.warning(f"Cannot apply color to object {object_id}: invalid node path")
            return False
            
        # Get or create color state
        if object_id not in self.color_states:
            self.color_states[object_id] = ColorState(node_path)
        
        color_state = self.color_states[object_id]
        
        # If requesting the same element that's already active, do nothing
        if color_state.elemental_active and color_state.elemental_type == element_type:
            self.notify.debug(f"Element {element_type} already active on object {object_id}")
            return True
            
        # Clean up any existing effects
        color_state.cleanup()
        
        # Handle removal (ElementType.NONE)
        if element_type == ElementType.NONE:
            return self._remove_elemental_color(object_id, color_state)
        
        # Apply new elemental color
        return self._apply_element_color(object_id, element_type, color_state)
    
    def _apply_element_color(self, object_id: int, element_type: ElementType, color_state: ColorState):
        """Apply elemental color with smooth animation."""
        if not color_state.is_valid():
            return False
            
        target_color = self.ELEMENTAL_COLORS[element_type]
        node_path = color_state.node_path
        
        # Set up transparency if needed (when color has alpha < 1 or values > 1 for glow effect)
        needs_transparency = (target_color[3] < 1.0 or 
                            max(target_color[:3]) > 1.0)
        
        if needs_transparency and not color_state.base_transparency:
            node_path.setTransparency(TransparencyAttrib.MAlpha)
        
        # Create smooth fade to elemental color
        current_color = node_path.getColorScale()
        
        fade_interval = LerpColorScaleInterval(
            node_path,
            duration=self.FADE_IN_TIME,
            colorScale=target_color,
            startColorScale=current_color,
            blendType='easeOut'
        )
        
        # Set up maintenance task to ensure color persistence
        def maintain_color():
            """Maintain elemental color against external changes."""
            if color_state.is_valid() and color_state.elemental_active:
                # Check if color has been externally modified
                current = color_state.node_path.getColorScale()
                expected = self.ELEMENTAL_COLORS[color_state.elemental_type]
                
                # Allow small tolerance for floating point errors
                tolerance = 0.01
                if (abs(current[0] - expected[0]) > tolerance or
                    abs(current[1] - expected[1]) > tolerance or
                    abs(current[2] - expected[2]) > tolerance or
                    abs(current[3] - expected[3]) > tolerance):
                    
                    self.notify.debug(f"Restoring elemental color on object {object_id}")
                    color_state.node_path.setColorScale(expected)
                    
        # Start maintenance after fade completes
        def start_maintenance():
            if color_state.elemental_active:
                task_name = f'maintain_elemental_color_{object_id}'
                color_state.maintenance_task = task_name
                taskMgr.doMethodLater(0.1, lambda task: maintain_color() or task.again, 
                                    task_name)
        
        # Complete sequence
        complete_sequence = Sequence(
            fade_interval,
            Func(start_maintenance),
            name=f'elemental_color_apply_{object_id}'
        )
        
        # Update state and start animation
        color_state.elemental_active = True
        color_state.elemental_type = element_type
        color_state.active_interval = complete_sequence
        
        complete_sequence.start()
        
        self.notify.debug(f"Applied {element_type} color to object {object_id}")
        return True
    
    def _remove_elemental_color(self, object_id: int, color_state: ColorState):
        """Remove elemental color and restore base state."""
        if not color_state.is_valid():
            # Clean up the state even if node path is invalid
            if object_id in self.color_states:
                del self.color_states[object_id]
            return True
            
        node_path = color_state.node_path
        current_color = node_path.getColorScale()
        target_color = color_state.base_color_scale
        
        # Create smooth fade back to base color
        fade_interval = LerpColorScaleInterval(
            node_path,
            duration=self.FADE_OUT_TIME,
            colorScale=target_color,
            startColorScale=current_color,
            blendType='easeIn'
        )
        
        def cleanup_after_fade():
            """Clean up transparency and state after fade completes."""
            if color_state.is_valid():
                # Restore transparency state
                if not color_state.base_transparency:
                    node_path.clearTransparency()
                    
                # Ensure we're at exact base color (fix floating point drift)
                node_path.setColorScale(color_state.base_color_scale)
            
            # Clean up state
            color_state.elemental_active = False
            color_state.elemental_type = ElementType.NONE
            
        complete_sequence = Sequence(
            fade_interval,
            Func(cleanup_after_fade),
            name=f'elemental_color_remove_{object_id}'
        )
        
        color_state.active_interval = complete_sequence
        complete_sequence.start()
        
        self.notify.debug(f"Removed elemental color from object {object_id}")
        return True
    
    def force_remove_elemental_color(self, object_id: int):
        """
        Immediately remove elemental color without animation.
        Used for emergency cleanup or when object is being destroyed.
        """
        if object_id not in self.color_states:
            return
            
        color_state = self.color_states[object_id]
        color_state.cleanup()
        
        if color_state.is_valid():
            # Immediate restoration
            color_state.node_path.setColorScale(color_state.base_color_scale)
            
            if not color_state.base_transparency:
                color_state.node_path.clearTransparency()
        
        # Clean up state
        color_state.elemental_active = False
        color_state.elemental_type = ElementType.NONE
        del self.color_states[object_id]
        
        self.notify.debug(f"Force removed elemental color from object {object_id}")
    
    def get_elemental_color(self, object_id: int) -> ElementType:
        """Get the current elemental color type for an object."""
        if object_id in self.color_states:
            return self.color_states[object_id].elemental_type
        return ElementType.NONE
    
    def is_elemental_active(self, object_id: int) -> bool:
        """Check if an object has active elemental coloring."""
        if object_id in self.color_states:
            return self.color_states[object_id].elemental_active
        return False
    
    def cleanup_all_effects(self):
        """Clean up all active elemental effects."""
        self.notify.debug("Cleaning up all elemental color effects")
        
        for object_id in list(self.color_states.keys()):
            self.force_remove_elemental_color(object_id)
    
    def _get_node_path(self, object_id: int):
        """Get NodePath for an object by ID."""
        # Try multiple methods to find the object
        
        # Method 1: Client side
        try:
            if hasattr(base, 'cr') and base.cr:
                obj = base.cr.getDo(object_id)
                if obj and hasattr(obj, 'getNodePath'):
                    return obj.getNodePath()
                elif obj:
                    return obj  # Object might be a NodePath itself
        except:
            pass
        
        # Method 2: AI side
        try:
            if hasattr(simbase, 'air') and simbase.air:
                obj = simbase.air.getDo(object_id)
                if obj and hasattr(obj, 'getNodePath'):
                    return obj.getNodePath()
                elif obj:
                    return obj
        except:
            pass
        
        return None
    
    def destroy(self):
        """Clean up the color manager."""
        self.cleanup_all_effects()
        DirectObject.destroy(self)


class ElementalVisualManager:
    """
    Simplified visual manager that delegates to the color system.
    Maintains compatibility with existing elemental system.
    """
    
    def __init__(self):
        self.color_manager = ElementalColorManager()
    
    def apply_elemental_visual(self, obj, element_type: int, object_id: int):
        """Apply elemental visual effects (legacy interface)."""
        element_enum = ElementType(element_type) if element_type != 0 else ElementType.NONE
        return self.color_manager.apply_elemental_color(object_id, element_enum, obj)
    
    def set_elemental_visual_to_element(self, object_id: int, element_type: int, obj=None):
        """Set elemental visual to specific element (legacy interface)."""
        element_enum = ElementType(element_type) if element_type != 0 else ElementType.NONE
        return self.color_manager.apply_elemental_color(object_id, element_enum, obj)
    
    def remove_elemental_visual(self, object_id: int):
        """Remove elemental visual effects."""
        return self.color_manager.apply_elemental_color(object_id, ElementType.NONE)
    
    def force_remove_elemental_visual(self, object_id: int):
        """Force remove elemental visual effects."""
        self.color_manager.force_remove_elemental_color(object_id)
    
    def cleanup_all_effects(self):
        """Clean up all effects."""
        self.color_manager.cleanup_all_effects()


class ElementalVisualFactory:
    """Factory for creating visual managers."""
    
    @staticmethod
    def create_visual_manager() -> ElementalVisualManager:
        """Create a new elemental visual manager."""
        return ElementalVisualManager() 