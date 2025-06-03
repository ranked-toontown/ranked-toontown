from enum import Enum
from typing import Dict, List, Optional, Set
import random


class ElementType(Enum):
    """Enumeration of all available element types."""
    NONE = 0
    FIRE = 1
    WATER = 2
    WIND = 3
    # Future elements can be added here
    # EARTH = 4
    # AIR = 5
    # ICE = 6
    # LIGHTNING = 7


class SynergyType(Enum):
    """Types of synergies between elements."""
    NEUTRAL = 0    # No interaction
    POSITIVE = 1   # Enhances effect
    NEGATIVE = 2   # Cancels/reduces effect


class ElementalSynergy:
    """Defines how two elements interact with each other."""
    
    def __init__(self, element1: ElementType, element2: ElementType, synergy_type: SynergyType, description: str = ""):
        self.element1 = element1
        self.element2 = element2
        self.synergy_type = synergy_type
        self.description = description
    
    def applies_to(self, elem1: ElementType, elem2: ElementType) -> bool:
        """Check if this synergy applies to the given element combination."""
        return (self.element1 == elem1 and self.element2 == elem2) or \
               (self.element1 == elem2 and self.element2 == elem1)


class ElementalProperties:
    """Properties for an elemental safe."""
    
    def __init__(self, element_type: ElementType, duration: float = 10.0, cooldown: float = 5.0):
        self.element_type = element_type
        self.duration = duration  # How long the element lasts
        self.cooldown = cooldown  # Cooldown before it can become elemental again
        self.start_time = 0.0     # When the element was applied
        self.last_elemental_time = 0.0  # When it was last elemental (for cooldown)
    
    def is_active(self, current_time: float) -> bool:
        """Check if the elemental effect is currently active."""
        if self.element_type == ElementType.NONE:
            return False
        return current_time - self.start_time < self.duration
    
    def can_become_elemental(self, current_time: float) -> bool:
        """Check if the safe can become elemental again."""
        return current_time - self.last_elemental_time >= self.cooldown
    
    def apply_element(self, element_type: ElementType, current_time: float):
        """Apply an element to this safe."""
        self.element_type = element_type
        self.start_time = current_time
        if element_type != ElementType.NONE:
            self.last_elemental_time = current_time
    
    def clear_element(self):
        """Remove the elemental effect."""
        self.element_type = ElementType.NONE


class ElementalSystemConfig:
    """Configuration for the elemental system."""
    
    # Chance for a safe to become elemental each cycle (0.0 to 1.0)
    ELEMENTAL_CHANCE = 0.5  # 50% chance instead of 100%
    
    # How often to check for new elemental applications (seconds)
    CYCLE_INTERVAL = 5.0
    
    # How long elemental effects last (seconds)
    EFFECT_DURATION = 10.0
    
    # Cooldown before a safe can become elemental again (seconds)
    ELEMENTAL_COOLDOWN = 5.0
    
    # Available elements that can be randomly assigned
    AVAILABLE_ELEMENTS = [ElementType.FIRE, ElementType.WATER, ElementType.WIND]
    
    # Visual effect colors for each element (R, G, B, A)
    ELEMENT_COLORS = {
        ElementType.FIRE: (1.0, 0.3, 0.1, 0.8),   # Red-orange
        ElementType.WATER: (0.1, 0.5, 1.0, 0.8),  # Blue
        ElementType.WIND: (0.7, 1.0, 0.8, 0.8),   # Light soft green
        ElementType.NONE: (1.0, 1.0, 1.0, 0.0),   # Transparent
    }


class ElementalSynergyManager:
    """Manages elemental synergies and their effects."""
    
    def __init__(self):
        self._synergies: List[ElementalSynergy] = []
        self._setup_default_synergies()
    
    def _setup_default_synergies(self):
        """Set up the default synergies between elements."""
        # Water cancels Fire (negative synergy)
        self._synergies.append(
            ElementalSynergy(
                ElementType.FIRE, 
                ElementType.WATER, 
                SynergyType.NEGATIVE,
                "Water extinguishes fire"
            )
        )
        
        # Wind enhances Fire (positive synergy)
        self._synergies.append(
            ElementalSynergy(
                ElementType.FIRE,
                ElementType.WIND,
                SynergyType.POSITIVE,
                "Wind feeds fire, creating explosion"
            )
        )
        
        # Wind enhances Water (positive synergy)
        self._synergies.append(
            ElementalSynergy(
                ElementType.WATER,
                ElementType.WIND,
                SynergyType.POSITIVE,
                "Wind and water create freezing effect"
            )
        )
    
    def get_synergy(self, element1: ElementType, element2: ElementType) -> Optional[ElementalSynergy]:
        """Get the synergy between two elements, if any."""
        for synergy in self._synergies:
            if synergy.applies_to(element1, element2):
                return synergy
        return None
    
    def add_synergy(self, synergy: ElementalSynergy):
        """Add a new synergy to the manager."""
        self._synergies.append(synergy)


class ElementalSystem:
    """Main system for managing elemental effects on safes."""
    
    def __init__(self):
        self.config = ElementalSystemConfig()
        self.synergy_manager = ElementalSynergyManager()
        self._elemental_safes: Dict[int, ElementalProperties] = {}  # safeId -> properties
        self._enabled = False
    
    def enable(self):
        """Enable the elemental system."""
        self._enabled = True
    
    def disable(self):
        """Disable the elemental system and clear all effects."""
        self._enabled = False
        self._elemental_safes.clear()
    
    def is_enabled(self) -> bool:
        """Check if the elemental system is enabled."""
        return self._enabled
    
    def register_safe(self, safe_id: int):
        """Register a safe with the elemental system."""
        if safe_id not in self._elemental_safes:
            self._elemental_safes[safe_id] = ElementalProperties(ElementType.NONE)
    
    def unregister_safe(self, safe_id: int):
        """Unregister a safe from the elemental system."""
        if safe_id in self._elemental_safes:
            del self._elemental_safes[safe_id]
    
    def get_safe_element(self, safe_id: int) -> ElementType:
        """Get the current element of a safe."""
        properties = self._elemental_safes.get(safe_id)
        if properties and properties.is_active(globalClock.getFrameTime()):
            return properties.element_type
        return ElementType.NONE
    
    def apply_element_to_safe(self, safe_id: int, element_type: ElementType):
        """Apply an element to a specific safe."""
        if not self._enabled:
            return
        
        properties = self._elemental_safes.get(safe_id)
        if properties:
            current_time = globalClock.getFrameTime()
            properties.apply_element(element_type, current_time)
    
    def remove_safe_element(self, safe_id: int):
        """Remove the elemental effect from a specific safe."""
        if not self._enabled:
            return
        
        properties = self._elemental_safes.get(safe_id)
        if properties:
            properties.clear_element()
    
    def update_elemental_cycle(self, safe_objects=None):
        """Update the elemental cycle for all registered safes."""
        if not self._enabled:
            return
        
        current_time = globalClock.getFrameTime()
        
        # Track statistics for this cycle
        expired_count = 0
        applied_count = 0
        skipped_already_elemental = 0
        skipped_cooldown = 0
        skipped_chance = 0
        skipped_invalid_state = 0
        
        for safe_id, properties in self._elemental_safes.items():
            # Clear expired elements first
            if not properties.is_active(current_time):
                if properties.element_type != ElementType.NONE:
                    expired_count += 1
                    print(f"Safe {safe_id} elemental effect ({properties.element_type.name}) expired")
                properties.clear_element()
            
            # Only try to apply new elements to safes that are NOT currently elemental
            # This prevents overriding existing elemental effects
            if properties.element_type != ElementType.NONE:
                # Safe is currently elemental, skip this cycle
                skipped_already_elemental += 1
                continue
            
            if not properties.can_become_elemental(current_time):
                # Safe is on cooldown
                skipped_cooldown += 1
                continue
            
            # Check safe state if safe objects are provided
            if safe_objects is not None:
                safe_obj = safe_objects.get(safe_id)
                if safe_obj and hasattr(safe_obj, 'state'):
                    # Skip safes that are being grabbed or dropped
                    if safe_obj.state in ['Grabbed', 'Dropped']:
                        skipped_invalid_state += 1
                        continue
            
            # Roll for elemental chance
            if random.random() >= self.config.ELEMENTAL_CHANCE:
                # Failed the random chance
                skipped_chance += 1
                continue
            
            # Apply new element
            new_element = random.choice(self.config.AVAILABLE_ELEMENTS)
            properties.apply_element(new_element, current_time)
            applied_count += 1
            print(f"Applied {new_element.name} to safe {safe_id}")
        
        # Summary logging
        if expired_count > 0 or applied_count > 0 or skipped_invalid_state > 0:
            print(f"Elemental Cycle Summary: {applied_count} applied, {expired_count} expired, "
                  f"{skipped_already_elemental} already elemental, {skipped_cooldown} on cooldown, "
                  f"{skipped_chance} failed chance roll, {skipped_invalid_state} invalid state")
    
    def get_all_elemental_safes(self) -> Dict[int, ElementType]:
        """Get all currently elemental safes and their elements."""
        result = {}
        current_time = globalClock.getFrameTime()
        
        for safe_id, properties in self._elemental_safes.items():
            if properties.is_active(current_time):
                result[safe_id] = properties.element_type
        
        return result
    
    def check_synergy(self, element1: ElementType, element2: ElementType) -> Optional[ElementalSynergy]:
        """Check for synergy between two elements."""
        return self.synergy_manager.get_synergy(element1, element2)
    
    def is_safe_currently_elemental(self, safe_id: int) -> bool:
        """Check if a safe is currently elemental (has an active element)."""
        properties = self._elemental_safes.get(safe_id)
        if properties:
            return properties.is_active(globalClock.getFrameTime())
        return False 