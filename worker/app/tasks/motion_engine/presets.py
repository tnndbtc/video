"""
Motion Preset Definitions for Ken Burns Style Animation

Defines reusable motion presets with zoom and pan parameters
for animating still images into video clips.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class MotionPreset:
    """
    Defines a Ken Burns style motion preset.

    Attributes:
        name: Preset identifier
        start_zoom: Initial zoom level (1.0 = 100%)
        end_zoom: Final zoom level
        pan_start_x: Start X position (0.0-1.0 relative)
        pan_start_y: Start Y position (0.0-1.0 relative)
        pan_end_x: End X position (0.0-1.0 relative)
        pan_end_y: End Y position (0.0-1.0 relative)
        easing: Animation easing function (linear, ease_in, ease_out)
        description: Human-readable description
    """

    name: str
    start_zoom: float
    end_zoom: float
    pan_start_x: float
    pan_start_y: float
    pan_end_x: float
    pan_end_y: float
    easing: str = "linear"
    description: str = ""

    def validate(self) -> bool:
        """Validate preset parameters are within valid ranges."""
        if not (0.5 <= self.start_zoom <= 2.0):
            return False
        if not (0.5 <= self.end_zoom <= 2.0):
            return False
        if not (0.0 <= self.pan_start_x <= 1.0):
            return False
        if not (0.0 <= self.pan_start_y <= 1.0):
            return False
        if not (0.0 <= self.pan_end_x <= 1.0):
            return False
        if not (0.0 <= self.pan_end_y <= 1.0):
            return False
        if self.easing not in ("linear", "ease_in", "ease_out", "ease_in_out"):
            return False
        return True

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "start_zoom": self.start_zoom,
            "end_zoom": self.end_zoom,
            "pan_start_x": self.pan_start_x,
            "pan_start_y": self.pan_start_y,
            "pan_end_x": self.pan_end_x,
            "pan_end_y": self.pan_end_y,
            "easing": self.easing,
            "description": self.description,
        }


# =============================================================================
# Preset Library
# =============================================================================

PRESET_LIBRARY: Dict[str, MotionPreset] = {
    "slow_zoom_in": MotionPreset(
        name="slow_zoom_in",
        start_zoom=1.0,
        end_zoom=1.15,
        pan_start_x=0.5,
        pan_start_y=0.5,
        pan_end_x=0.5,
        pan_end_y=0.5,
        easing="linear",
        description="Gentle zoom in, centered",
    ),
    "slow_zoom_out": MotionPreset(
        name="slow_zoom_out",
        start_zoom=1.15,
        end_zoom=1.0,
        pan_start_x=0.5,
        pan_start_y=0.5,
        pan_end_x=0.5,
        pan_end_y=0.5,
        easing="linear",
        description="Gentle zoom out, centered",
    ),
    "pan_left": MotionPreset(
        name="pan_left",
        start_zoom=1.1,
        end_zoom=1.1,
        pan_start_x=0.0,
        pan_start_y=0.5,
        pan_end_x=1.0,
        pan_end_y=0.5,
        easing="linear",
        description="Horizontal pan left to right",
    ),
    "pan_right": MotionPreset(
        name="pan_right",
        start_zoom=1.1,
        end_zoom=1.1,
        pan_start_x=1.0,
        pan_start_y=0.5,
        pan_end_x=0.0,
        pan_end_y=0.5,
        easing="linear",
        description="Horizontal pan right to left",
    ),
    "diagonal_push": MotionPreset(
        name="diagonal_push",
        start_zoom=1.05,
        end_zoom=1.15,
        pan_start_x=0.0,
        pan_start_y=1.0,
        pan_end_x=1.0,
        pan_end_y=0.0,
        easing="linear",
        description="Diagonal motion from bottom-left to top-right",
    ),
    "subtle_drift": MotionPreset(
        name="subtle_drift",
        start_zoom=1.05,
        end_zoom=1.08,
        pan_start_x=0.4,
        pan_start_y=0.5,
        pan_end_x=0.6,
        pan_end_y=0.5,
        easing="ease_in_out",
        description="Subtle floating motion",
    ),
}


def get_preset(name: str) -> Optional[MotionPreset]:
    """
    Get a motion preset by name.

    Args:
        name: Preset name (e.g., "slow_zoom_in")

    Returns:
        MotionPreset if found, None otherwise
    """
    return PRESET_LIBRARY.get(name)


def list_presets() -> list:
    """
    List all available preset names.

    Returns:
        List of preset name strings
    """
    return list(PRESET_LIBRARY.keys())


def get_preset_for_index(index: int) -> MotionPreset:
    """
    Get a preset by cycling through the library.

    Useful for automatically assigning different presets
    to sequential segments.

    Args:
        index: Segment index (will be modulo'd against library size)

    Returns:
        MotionPreset
    """
    preset_names = list(PRESET_LIBRARY.keys())
    preset_name = preset_names[index % len(preset_names)]
    return PRESET_LIBRARY[preset_name]
