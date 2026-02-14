/**
 * Rule Parser for Beat-Based Prompt Rendering (Frontend)
 *
 * Mirrors backend logic in backend/app/rules/rule_parser.py
 * Parses natural language rules for controlling media switching timing.
 *
 * Supports:
 * - "8 beats", "every 4 beats"
 * - "fast", "slow", "normal"
 * - Chinese: "每4拍", "快", "慢"
 * - Spanish: "cada 8 tiempo"
 */

// Default beats per cut when no rule matches
const DEFAULT_BEATS_PER_CUT = 8;

// Keyword mappings for pace descriptors
const KEYWORD_MAPPINGS: Record<string, number> = {
  // Fast pace (2 beats)
  fast: 2,
  quick: 2,
  rapid: 2,
  '快': 2,
  rapido: 2,
  'rápido': 2,
  // Normal pace (8 beats)
  normal: 8,
  medium: 8,
  regular: 8,
  '正常': 8,
  '普通': 8,
  // Slow pace (16 beats)
  slow: 16,
  cinematic: 16,
  '慢': 16,
  '电影感': 16,
  lento: 16,
};

export interface ParsedRule {
  beatsPerCut: number;
  isDefault: boolean;
  matchedPattern?: string;
}

/**
 * Parse a natural language rule into beats per cut.
 *
 * @param text - Natural language rule text (e.g., "8 beats", "fast", "每4拍")
 * @returns ParsedRule with beatsPerCut and match info
 */
export function parseRuleText(text: string): ParsedRule {
  if (!text || !text.trim()) {
    return { beatsPerCut: DEFAULT_BEATS_PER_CUT, isDefault: true };
  }

  const normalized = text.trim().toLowerCase();
  const result = extractBeats(normalized);

  if (result) {
    return {
      beatsPerCut: result.beats,
      isDefault: false,
      matchedPattern: result.pattern,
    };
  }

  return { beatsPerCut: DEFAULT_BEATS_PER_CUT, isDefault: true };
}

interface ExtractResult {
  beats: number;
  pattern: string;
}

function extractBeats(text: string): ExtractResult | null {
  // Priority 1: Digit before beat/beats/拍/tiempo
  // Matches: "8 beats", "4beats", "8 拍", "4 tiempo"
  const patternBeats = /(\d+)\s*(?:beats?|拍|tiempo)/i;
  let match = text.match(patternBeats);
  if (match) {
    const beats = parseInt(match[1], 10);
    if (beats >= 1 && beats <= 64) {
      return { beats, pattern: `${beats} beats` };
    }
  }

  // Priority 2: Chinese pattern "每N拍"
  const patternChinese = /每\s*(\d+)\s*拍/;
  match = text.match(patternChinese);
  if (match) {
    const beats = parseInt(match[1], 10);
    if (beats >= 1 && beats <= 64) {
      return { beats, pattern: `每${beats}拍` };
    }
  }

  // Priority 2b: "every N beats" pattern
  const patternEvery = /every\s*(\d+)\s*(?:beats?|拍)?/i;
  match = text.match(patternEvery);
  if (match) {
    const beats = parseInt(match[1], 10);
    if (beats >= 1 && beats <= 64) {
      return { beats, pattern: `every ${beats} beats` };
    }
  }

  // Priority 2c: Spanish pattern "cada N beats/tiempo"
  const patternCada = /cada\s*(\d+)\s*(?:beats?|tiempo)?/i;
  match = text.match(patternCada);
  if (match) {
    const beats = parseInt(match[1], 10);
    if (beats >= 1 && beats <= 64) {
      return { beats, pattern: `cada ${beats}` };
    }
  }

  // Priority 3: Keyword mapping
  for (const [keyword, beats] of Object.entries(KEYWORD_MAPPINGS)) {
    if (text.includes(keyword)) {
      return { beats, pattern: keyword };
    }
  }

  return null;
}
