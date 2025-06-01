"""
Elemental Visual Effects System

This module handles all visual effects for elemental objects in the game,
including particle effects, color changes, and animations.
"""

from typing import Dict, Optional, Any
from .ElementalSystem import ElementType
from direct.showbase.DirectObject import DirectObject
from panda3d.core import *
from toontown.battle import BattleParticles
from direct.interval.IntervalGlobal import LerpColorScaleInterval, LerpScaleInterval, Parallel


class ElementalVisualManager(DirectObject):
    """
    Manages visual effects for elemental objects.
    
    Handles particle systems, color scaling, animations, and cleanup
    for all elemental types (Fire, Water, etc.).
    """
    
    def __init__(self):
        DirectObject.__init__(self)
        self.active_effects: Dict[int, Any] = {}  # objectId -> effect container
        
    def apply_elemental_visual(self, obj, element_type: int, object_id: int):
        """
        Apply visual effects to an object based on its element type.
        
        Args:
            obj: The object to apply effects to (e.g., safe)
            element_type: Integer representing the element (0=None, 1=Fire, 2=Water)
            object_id: Unique identifier for cleanup tracking
        """
        # Clean up any existing effects for this object
        self.remove_elemental_visual(object_id)
        
        if element_type == 0:  # NONE
            # Remove any color scaling
            obj.clearColorScale()
            return
        
        if element_type == ElementType.FIRE.value:
            effect_container = self._create_fire_effect(obj)
            self.active_effects[object_id] = effect_container
        elif element_type == ElementType.WATER.value:
            self._apply_water_effect(obj)
            # Water doesn't need container tracking (just color scale)
        
    def remove_elemental_visual(self, object_id: int):
        """Remove all visual effects for a specific object."""
        if object_id in self.active_effects:
            effect_container = self.active_effects[object_id]
            if effect_container and not effect_container.isEmpty():
                # Clean up any stored intervals
                appearance_interval = effect_container.getPythonTag('appearanceInterval')
                if appearance_interval:
                    appearance_interval.finish()
                
                # Remove the effect container and all its children
                effect_container.removeNode()
            
            del self.active_effects[object_id]
    
    def cleanup_all_effects(self):
        """Remove all active visual effects."""
        for object_id in list(self.active_effects.keys()):
            self.remove_elemental_visual(object_id)
    
    def _create_fire_effect(self, obj):
        """Create sophisticated fire particle effects for Fire elemental objects."""
        # Load the battle particles system
        BattleParticles.loadParticles()
        
        # Create a container node for the fire effects
        fire_container = obj.attachNewNode('elementalEffect')
        fire_container.setPos(0, 0, 5)  # Position above object
        fire_container.setScale(0.01, 0.01, 0.01)  # Start very small
        
        # Create large central fire effect
        base_flame_effect = BattleParticles.createParticleEffect(file='firedBaseFlame')
        BattleParticles.setEffectTexture(base_flame_effect, 'fire')
        base_flame_effect.reparentTo(fire_container)
        base_flame_effect.setPos(0, 0, 0)
        base_flame_effect.setScale(12.0, 12.0, 15.0)  # Dramatic large scale
        
        # Store reference for cleanup
        fire_container.setPythonTag('baseFlameEffect', base_flame_effect)
        
        # Start the fire effect
        base_flame_effect.start(fire_container, fire_container)
        
        # Customize particle properties for smooth animation
        self._customize_fire_particles(base_flame_effect)
        
        # Create smooth appearance animation
        self._animate_fire_appearance(obj, fire_container)
        
        return fire_container
    
    def _customize_fire_particles(self, flame_effect):
        """Customize fire particle properties for smooth, dramatic appearance."""
        try:
            particles = flame_effect.getParticlesNamed('particles-1')
            if particles:
                renderer = particles.getRenderer()
                
                # Particles grow from very small to final size
                renderer.setInitialXScale(0.01)
                renderer.setInitialYScale(0.01)
                renderer.setFinalXScale(0.25)
                renderer.setFinalYScale(0.75)
                
                # Enable smooth scaling interpolation
                renderer.setXScaleFlag(1)
                renderer.setYScaleFlag(1)
                
                # Adjust timing for smoother animation
                particles.setBirthRate(0.01)  # More frequent spawning
                particles.factory.setLifespanBase(0.4)  # Longer particle life
                particles.factory.setLifespanSpread(0.1)  # Add randomness
                
                # Improve spawning consistency
                particles.setLitterSize(6)  # Fewer per spawn but more frequent
                particles.setLitterSpread(2)  # Add variation
                
                # Enhance alpha blending (BaseParticleRenderer is available globally)
                renderer.setAlphaMode(BaseParticleRenderer.PRALPHAOUT)
                renderer.setAlphaBlendMethod(BaseParticleRenderer.PPBLENDLINEAR)
                
        except Exception as e:
            print(f"ElementalVisuals: Could not customize fire particles: {e}")
    
    def _animate_fire_appearance(self, obj, fire_container):
        """Create smooth appearance animation for fire effects."""
        try:
            # Object gets fiery orange glow
            glow_interval = LerpColorScaleInterval(
                obj, 1.0,  # 1 second duration
                colorScale=(1.3, 0.7, 0.4, 1.0),  # Fiery orange tint
                startColorScale=(1.0, 1.0, 1.0, 1.0)
            )
            
            # Fire particles scale up smoothly
            scale_interval = LerpScaleInterval(
                fire_container, 1.0,  # 1 second duration
                scale=(1.0, 1.0, 1.0),  # Scale to normal size
                startScale=(0.01, 0.01, 0.01)
            )
            
            # Play animations in parallel
            appearance_interval = Parallel(glow_interval, scale_interval)
            appearance_interval.start()
            
            # Store for cleanup
            fire_container.setPythonTag('appearanceInterval', appearance_interval)
            
        except Exception as e:
            print(f"ElementalVisuals: Could not create fire appearance animation: {e}")
            # Fallback: set to normal immediately
            fire_container.setScale(1.0, 1.0, 1.0)
            obj.setColorScale(1.3, 0.7, 0.4, 1.0)
    
    def _apply_water_effect(self, obj):
        """Apply water elemental visual effects (currently just color tint)."""
        # Soft blue tint for water elements
        obj.setColorScale(0.85, 0.95, 1.0, 1.0)
        
        # TODO: Add water particle effects (bubbles, mist, etc.)
        # Could include:
        # - Bubble particle system
        # - Mist/steam effects  
        # - Water droplet animations
        # - Gentle blue glow animation


class ElementalVisualFactory:
    """Factory class for creating elemental visual managers."""
    
    @staticmethod
    def create_visual_manager() -> ElementalVisualManager:
        """Create a new ElementalVisualManager instance."""
        return ElementalVisualManager() 