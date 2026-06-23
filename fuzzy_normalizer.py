"""
fuzzy_normalizer.py  — v3 (precision edition)

Key changes vs v2:
  - Fuzzy matching vocab reduced to ONLY genuinely garbled STT words
    (no action words like "turn", "full", "speed" that are already correct English)
  - _MATCH_THRESHOLD raised to 88 to stop false-positive substitutions
  - Word-to-digit converter unchanged (correct)
  - Added _STOP_WORDS: common English words that should NEVER be fuzzily matched
  - Fuzzy now skips words that are already valid English

Root cause of v2 failures:
  "turn" scored 90 vs "turn on" → inserted "on" in wrong position
  "speed" scored 90 vs "fan speed" → doubled the word
  "bright" scored 90 vs "brightness" → broke "too bright outside"
  "fully" scored 88 vs "full" → stripped suffix, broke pattern match
"""

try:
    from rapidfuzz import process, fuzz
    _FUZZY_AVAILABLE = True
except ImportError:
    _FUZZY_AVAILABLE = False
    # rapidfuzz is installed in the project venv (venv/bin/python3).
    # This warning fires only if running with the system Python — use start.sh instead.
    import sys as _sys
    if "edge-auto-assistant/venv" not in _sys.prefix:
        print("[Fuzzy] rapidfuzz not available in current Python env. Use start.sh to run inside venv.")

# ── Garble-only vocabulary ────────────────────────────────────────────────────
# ONLY include words that would NEVER appear in correct natural speech.
# Do NOT include short common English words — they cause false positives.
_VOCAB: list[str] = [
    "sunroof", "moonroof", "temperature", "headlights",
    "aircon", "brightness", "dashboard",
]

# ── Word substitution table: confirmed STT errors → correct automotive terms ──
_SUBSTITUTIONS: dict[str, str] = {
    "androof":         "sunroof",
    "sunrof":          "sunroof",
    "snroof":          "sunroof",
    "sunrooof":        "sunroof",
    "moonrof":         "moonroof",
    "temperatre":      "temperature",
    "temperture":      "temperature",
    "tempurature":     "temperature",
    "temprature":      "temperature",
    "hedlights":       "headlights",
    "headlightes":     "headlights",
    "headlight":       "headlights",
    "lightes":         "lights",
    "lites":           "lights",
    "brigthness":      "brightness",
    "birightness":     "brightness",
    "brightnes":       "brightness",
    "dashbord":        "dashboard",
    "dashbaord":       "dashboard",
    "airconditioning": "air conditioning",
    "blwr":            "fan",
    "fanspeed":        "fan speed",
    "rooftop":         "sunroof",
    "toplight":        "sunroof",
    "closethe":        "close the",
    "openthe":         "open the",
    "turnon":          "turn on",
    "turnoff":         "turn off",
    # Common colloquial mappings
    "bro":             "",        # strip filler
    "yaar":            "",        # strip filler
    "like":            "",        # avoids confusing "it is like a sauna"
}

# Words that are correct English and must NEVER be fuzzily substituted.
# This prevents "turn" → "turn on", "speed" → "fan speed", etc.
_STOP_WORDS: set[str] = {
    "turn", "full", "speed", "bright", "screen", "light", "heat", "cold",
    "warm", "cool", "open", "close", "set", "make", "feel", "need", "want",
    "high", "low", "fan", "air", "roof", "just", "more", "less", "some",
    "that", "this", "here", "there", "please", "could", "would", "should",
    "have", "like", "much", "little", "very", "too", "bit", "good", "dark",
    "sun", "star", "rain", "night", "morning", "evening", "stuffy", "freezing",
    "sweating", "breathe", "outside", "inside",
}

# Minimum fuzzy match score (0–100) to accept a correction.
_MATCH_THRESHOLD = 88


def normalize(text: str) -> tuple[str, bool]:
    """
    Normalize a raw STT transcript.

    Returns:
        (normalized_text, was_corrected)

    Changes applied (in order):
      1. Known exact substitutions (fast path)
      2. Word-to-digit conversion ("twenty five" → "25")
      3. Fuzzy match for genuinely garbled automotive terms only
    """
    if not text:
        return text, False

    # Fast path: check known substitution table first (word-by-word)
    words = text.lower().split()
    corrected_words = []
    was_corrected = False

    for word in words:
        if word in _SUBSTITUTIONS:
            replacement = _SUBSTITUTIONS[word]
            if replacement:  # non-empty replacement
                corrected_words.append(replacement)
            # empty replacement = strip the word (filler words)
            was_corrected = True
        else:
            corrected_words.append(word)

    normalized = " ".join(corrected_words).strip()

    # Also check multi-word phrases
    for wrong, right in _SUBSTITUTIONS.items():
        if " " in wrong and wrong in normalized:
            normalized = normalized.replace(wrong, right)
            was_corrected = True

    # Convert number words to digits (e.g. "twenty five" → "25")
    _NUMS = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100
    }

    num_words = normalized.split()
    converted = []
    i = 0
    while i < len(num_words):
        w1 = num_words[i]
        if w1 in _NUMS:
            val = _NUMS[w1]
            if i + 1 < len(num_words) and num_words[i+1] in _NUMS:
                w2 = num_words[i+1]
                val2 = _NUMS[w2]
                if val >= 20 and val < 100 and val2 < 10:
                    val += val2
                    i += 1
            converted.append(str(val))
            was_corrected = True
        else:
            converted.append(w1)
        i += 1

    normalized = " ".join(converted)

    # Fuzzy path: ONLY for words that look like genuine garbled automotive terms
    # Skip common English words (in _STOP_WORDS) to prevent false substitutions
    if _FUZZY_AVAILABLE and not was_corrected:
        words2 = normalized.split()
        fuzzy_corrected = []
        for word in words2:
            # Only fuzzy-match long, unusual words — skip stop words and short words
            if len(word) >= 6 and not word.isdigit() and word not in _STOP_WORDS:
                match, score, _ = process.extractOne(
                    word, _VOCAB, scorer=fuzz.WRatio
                ) or (None, 0, None)
                if match and score >= _MATCH_THRESHOLD and match != word:
                    print(f"[Fuzzy] '{word}' → '{match}' (score={score})")
                    fuzzy_corrected.append(match)
                    was_corrected = True
                else:
                    fuzzy_corrected.append(word)
            else:
                fuzzy_corrected.append(word)
        normalized = " ".join(fuzzy_corrected)

    if was_corrected and normalized != text.lower():
        print(f"[Fuzzy] Corrected: '{text}' → '{normalized}'")

    return normalized, was_corrected
