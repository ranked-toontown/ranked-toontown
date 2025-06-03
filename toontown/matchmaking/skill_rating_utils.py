def interpolate_number(left: int, right: int, t: float) -> int:
    t = max(0.0, min(t, 1.0))  # Clamp t to 0-1
    return int(round(left + (right - left) * t))