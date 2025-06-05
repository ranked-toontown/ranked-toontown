from enum import Enum

class StatusEffect(Enum):
    BURNED = 1
    DRENCHED = 2
    WINDED = 3
    GROUNDED = 4
    EXPLODE = 5
    FROZEN = 6
    SHATTERED = 7

    def toAstron(self):
        return self.value
    
    @classmethod
    def fromAstron(cls, value):
        try:
            return cls(value)
        except ValueError:
            return None

# Status effect display colors (RGBA values)
STATUS_EFFECT_COLORS = {
    StatusEffect.BURNED: (1.0, 0.4, 0.0, 1.0),      # Fiery orange
    StatusEffect.DRENCHED: (0.6, 0.8, 0.9, 1.0),    # Misty blue
    StatusEffect.WINDED: (0.4, 0.8, 0.4, 1.0),      # Windy green
    StatusEffect.GROUNDED: (0.6, 0.4, 0.2, 1.0),    # Earthy brown
    StatusEffect.EXPLODE: (0.8, 0.8, 0.8, 1.0),     # Flashbang gray
    StatusEffect.FROZEN: (0.7, 0.9, 1.0, 1.0),      # Icy blue
    StatusEffect.SHATTERED: (1.0, 1.0, 1.0, 1.0),   # White
}

# Status effects that can be applied to safes (basic elemental effects only)
SAFE_ALLOWED_EFFECTS = {StatusEffect.BURNED, StatusEffect.DRENCHED, StatusEffect.WINDED, StatusEffect.GROUNDED}

SYNERGY_EFFECTS = {
    (StatusEffect.BURNED, StatusEffect.DRENCHED): None,
    (StatusEffect.BURNED, StatusEffect.WINDED): StatusEffect.EXPLODE,
    (StatusEffect.DRENCHED, StatusEffect.WINDED): StatusEffect.FROZEN,
    (StatusEffect.FROZEN, StatusEffect.GROUNDED): StatusEffect.SHATTERED,
}