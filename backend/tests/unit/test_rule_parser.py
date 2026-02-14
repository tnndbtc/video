"""
Unit tests for Rule Parser.

Tests the beat-based prompt rendering parser that converts
natural language rules to structured render plans.
"""

import pytest

from app.rules.rule_parser import parse_user_rule, DEFAULT_BEATS_PER_CUT


class TestParseUserRule:
    """Tests for parse_user_rule function."""

    def test_basic_beats_pattern(self):
        """Test parsing '8 beats' pattern."""
        result = parse_user_rule("8 beats")
        assert result["beats_per_cut"] == 8
        assert result["version"] == 1
        assert result["type"] == "beat_sequence"
        assert result["loop_media"] is True

    def test_every_n_beats_pattern(self):
        """Test parsing 'every 4 beats' pattern."""
        result = parse_user_rule("every 4 beats")
        assert result["beats_per_cut"] == 4

    def test_fast_keyword(self):
        """Test parsing 'fast cuts' keyword."""
        result = parse_user_rule("fast cuts")
        assert result["beats_per_cut"] == 2

    def test_slow_cinematic_keyword(self):
        """Test parsing 'slow cinematic' keywords."""
        result = parse_user_rule("slow cinematic")
        assert result["beats_per_cut"] == 16

    def test_chinese_pattern(self):
        """Test parsing Chinese '每8拍' pattern."""
        result = parse_user_rule("每8拍")
        assert result["beats_per_cut"] == 8

    def test_chinese_pattern_with_spaces(self):
        """Test parsing Chinese '每 8 拍' pattern with spaces."""
        result = parse_user_rule("每 8 拍")
        assert result["beats_per_cut"] == 8

    def test_spanish_cada_pattern(self):
        """Test parsing Spanish 'cada 8 beats' pattern."""
        result = parse_user_rule("cada 8 beats")
        assert result["beats_per_cut"] == 8

    def test_spanish_tiempo_pattern(self):
        """Test parsing Spanish 'cada 4 tiempo' pattern."""
        result = parse_user_rule("cada 4 tiempo")
        assert result["beats_per_cut"] == 4

    def test_random_text_fallback(self):
        """Test that random text falls back to default."""
        result = parse_user_rule("something random")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT

    def test_empty_string_fallback(self):
        """Test that empty string falls back to default."""
        result = parse_user_rule("")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT

    def test_none_safe(self):
        """Test handling of None input (should use default)."""
        result = parse_user_rule(None)
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT

    def test_chinese_fast_keyword(self):
        """Test parsing Chinese '快' keyword."""
        result = parse_user_rule("快")
        assert result["beats_per_cut"] == 2

    def test_chinese_slow_keyword(self):
        """Test parsing Chinese '慢' keyword."""
        result = parse_user_rule("慢")
        assert result["beats_per_cut"] == 16

    def test_chinese_normal_keyword(self):
        """Test parsing Chinese '正常' keyword."""
        result = parse_user_rule("正常")
        assert result["beats_per_cut"] == 8

    def test_chinese_cinematic_keyword(self):
        """Test parsing Chinese '电影感' keyword."""
        result = parse_user_rule("电影感")
        assert result["beats_per_cut"] == 16

    def test_mixed_case(self):
        """Test case insensitivity."""
        result = parse_user_rule("FAST")
        assert result["beats_per_cut"] == 2

        result = parse_user_rule("Every 4 Beats")
        assert result["beats_per_cut"] == 4

    def test_beat_singular(self):
        """Test parsing '1 beat' (singular)."""
        result = parse_user_rule("1 beat")
        assert result["beats_per_cut"] == 1

    def test_no_space_beats(self):
        """Test parsing '8beats' without space."""
        result = parse_user_rule("8beats")
        assert result["beats_per_cut"] == 8

    def test_4_beats(self):
        """Test parsing '4 beats'."""
        result = parse_user_rule("4 beats")
        assert result["beats_per_cut"] == 4

    def test_16_beats(self):
        """Test parsing '16 beats'."""
        result = parse_user_rule("16 beats")
        assert result["beats_per_cut"] == 16

    def test_quick_keyword(self):
        """Test parsing 'quick' keyword."""
        result = parse_user_rule("quick")
        assert result["beats_per_cut"] == 2

    def test_rapid_keyword(self):
        """Test parsing 'rapid' keyword."""
        result = parse_user_rule("rapid")
        assert result["beats_per_cut"] == 2

    def test_medium_keyword(self):
        """Test parsing 'medium' keyword."""
        result = parse_user_rule("medium")
        assert result["beats_per_cut"] == 8

    def test_normal_keyword(self):
        """Test parsing 'normal' keyword."""
        result = parse_user_rule("normal")
        assert result["beats_per_cut"] == 8

    def test_output_structure(self):
        """Test that output has correct structure."""
        result = parse_user_rule("8 beats")

        assert "version" in result
        assert "type" in result
        assert "beats_per_cut" in result
        assert "loop_media" in result

        assert isinstance(result["version"], int)
        assert isinstance(result["type"], str)
        assert isinstance(result["beats_per_cut"], int)
        assert isinstance(result["loop_media"], bool)

    def test_beats_out_of_range_high(self):
        """Test that extremely high beat values fall back to default."""
        result = parse_user_rule("999 beats")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT

    def test_beats_zero(self):
        """Test that 0 beats falls back to default."""
        result = parse_user_rule("0 beats")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT

    def test_beats_in_valid_range(self):
        """Test various valid beat values."""
        for n in [1, 2, 4, 8, 16, 32, 64]:
            result = parse_user_rule(f"{n} beats")
            assert result["beats_per_cut"] == n, f"Failed for {n} beats"

    def test_with_prefix_text(self):
        """Test parsing with prefix text."""
        result = parse_user_rule("switch every 4 beats")
        assert result["beats_per_cut"] == 4

    def test_with_suffix_text(self):
        """Test parsing with suffix text."""
        result = parse_user_rule("8 beats please")
        assert result["beats_per_cut"] == 8

    def test_chinese_4_beats(self):
        """Test parsing '每4拍'."""
        result = parse_user_rule("每4拍")
        assert result["beats_per_cut"] == 4

    def test_chinese_with_sentence(self):
        """Test parsing Chinese with surrounding context."""
        result = parse_user_rule("请每4拍切换一次")
        assert result["beats_per_cut"] == 4


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_whitespace_only(self):
        """Test input with only whitespace."""
        result = parse_user_rule("   ")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT

    def test_newlines(self):
        """Test input with newlines."""
        result = parse_user_rule("8\nbeats")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT  # Pattern doesn't match across newlines

    def test_tabs(self):
        """Test input with tabs."""
        result = parse_user_rule("8\tbeats")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT  # Tabs may not match space pattern

    def test_special_characters(self):
        """Test input with special characters."""
        result = parse_user_rule("8 beats!!!")
        assert result["beats_per_cut"] == 8

    def test_numbers_only(self):
        """Test input with just a number (no beat word)."""
        result = parse_user_rule("8")
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT

    def test_unicode_normalization(self):
        """Test Unicode normalization in Chinese input."""
        # Full-width characters
        result = parse_user_rule("８ beats")  # Full-width 8
        # This should fall back since we don't handle full-width digits
        assert result["beats_per_cut"] == DEFAULT_BEATS_PER_CUT
