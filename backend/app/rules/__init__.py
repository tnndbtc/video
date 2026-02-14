"""
Rules module for parsing natural language rendering rules.

Provides beat-based prompt rendering that allows users to control media
switching via natural language (e.g., "8 beats", "fast", "每4拍").
"""

from .rule_parser import parse_user_rule

__all__ = ["parse_user_rule"]
