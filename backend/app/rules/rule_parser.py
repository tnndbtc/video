"""
Rule Parser for Beat-Based Prompt Rendering.

Parses natural language rules for controlling media switching timing.
Supports multiple languages and formats:
- "8 beats", "every 4 beats"
- "fast", "slow", "normal"
- Chinese: "每4拍", "快", "慢"
- Spanish: "cada 8 tiempo"

No AI/LLM required - pure regex-based parsing.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Default beats per cut when no rule matches
DEFAULT_BEATS_PER_CUT = 8

# Keyword mappings for pace descriptors
KEYWORD_MAPPINGS = {
    # Fast pace (2 beats)
    "fast": 2,
    "quick": 2,
    "rapid": 2,
    "快": 2,
    "rapido": 2,
    "rápido": 2,
    # Normal pace (8 beats)
    "normal": 8,
    "medium": 8,
    "regular": 8,
    "正常": 8,
    "普通": 8,
    # Slow pace (16 beats)
    "slow": 16,
    "cinematic": 16,
    "慢": 16,
    "电影感": 16,
    "lento": 16,
}


def parse_user_rule(text: str) -> dict:
    """
    Parse a natural language rule into a structured render plan.

    Priority order:
    1. Extract digit before "beat/beats/拍/tiempo" (e.g., "8 beats", "4 拍")
    2. Chinese pattern "每N拍" (e.g., "每8拍")
    3. Keyword mapping (e.g., "fast" -> 2, "slow" -> 16)
    4. Default fallback: 8 beats

    Args:
        text: Natural language rule text (e.g., "8 beats", "fast", "每4拍")

    Returns:
        dict: Render plan with structure:
            {
                "version": 1,
                "type": "beat_sequence",
                "beats_per_cut": <int>,
                "loop_media": True
            }
    """
    if not text:
        return _create_render_plan(DEFAULT_BEATS_PER_CUT)

    # Normalize text: lowercase, strip whitespace
    normalized = text.strip().lower()

    try:
        beats = _extract_beats(normalized)
        if beats is not None:
            return _create_render_plan(beats)
    except Exception as e:
        logger.warning(f"Error parsing rule '{text}': {e}")

    # Default fallback
    return _create_render_plan(DEFAULT_BEATS_PER_CUT)


def _extract_beats(text: str) -> Optional[int]:
    """
    Extract beats per cut from text using priority-based matching.

    Args:
        text: Normalized (lowercase, stripped) input text

    Returns:
        int if pattern matched, None otherwise
    """
    # Priority 1: Digit before beat/beats/拍/tiempo
    # Matches: "8 beats", "4beats", "8 拍", "4 tiempo"
    pattern_beats = r"(\d+)\s*(?:beats?|拍|tiempo)"
    match = re.search(pattern_beats, text, re.IGNORECASE)
    if match:
        beats = int(match.group(1))
        if 1 <= beats <= 64:  # Sanity check: reasonable range
            logger.debug(f"Matched beats pattern: {beats}")
            return beats

    # Priority 2: Chinese pattern "每N拍"
    # Matches: "每8拍", "每 4 拍"
    pattern_chinese = r"每\s*(\d+)\s*拍"
    match = re.search(pattern_chinese, text)
    if match:
        beats = int(match.group(1))
        if 1 <= beats <= 64:
            logger.debug(f"Matched Chinese pattern: {beats}")
            return beats

    # Priority 2b: "every N beats" pattern
    pattern_every = r"every\s*(\d+)\s*(?:beats?|拍)?"
    match = re.search(pattern_every, text, re.IGNORECASE)
    if match:
        beats = int(match.group(1))
        if 1 <= beats <= 64:
            logger.debug(f"Matched 'every N beats' pattern: {beats}")
            return beats

    # Priority 2c: Spanish pattern "cada N beats/tiempo"
    pattern_cada = r"cada\s*(\d+)\s*(?:beats?|tiempo)?"
    match = re.search(pattern_cada, text, re.IGNORECASE)
    if match:
        beats = int(match.group(1))
        if 1 <= beats <= 64:
            logger.debug(f"Matched Spanish 'cada N' pattern: {beats}")
            return beats

    # Priority 3: Keyword mapping
    for keyword, beats in KEYWORD_MAPPINGS.items():
        if keyword in text:
            logger.debug(f"Matched keyword '{keyword}': {beats}")
            return beats

    # No match found
    return None


def _create_render_plan(beats_per_cut: int) -> dict:
    """
    Create a structured render plan dictionary.

    Args:
        beats_per_cut: Number of beats per media cut

    Returns:
        dict: Render plan with standardized structure
    """
    return {
        "version": 1,
        "type": "beat_sequence",
        "beats_per_cut": beats_per_cut,
        "loop_media": True,
    }
