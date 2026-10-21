"""Visible-character counting must not depend on whether the optional `regex` module is installed."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pcw  # noqa: E402

# expected counts = len(regex.findall(r"\X", s)) with the regex module (Unicode 15.1+ rules)
CASES = {
    "नमस्ते दोस्तों": 6, "क्षत्रिय": 3, "श्री": 1, "Hello\r\nWorld": 11, "\U0001F44D\U0001F3FD ok": 4,
    "\U0001F468‍\U0001F469‍\U0001F467 fam": 5, "\U0001F1EE\U0001F1F3\U0001F1FA\U0001F1F8": 2,
    "é café": 6, "தமிழ்": 3, "বাংলা ভাষা": 5, "ગુજરાતી": 4, "ਪੰਜਾਬੀ": 3, "ಕನ್ನಡ": 4,
    "മലയാളം": 4, "తెలుగు": 3, "اردو زبان": 9, "中文字": 3, "한국어": 3,
    # stress 2026-10-20: tag-sequence flag, decomposed Hangul, Thai SARA AM, Prepend, virama + independent vowel,
    # ZWJ between letters, controls before a mark, virama + ZWJ + consonant
    "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F win": 5,
    "\u1100\u1161\u11a8": 1, "\u0e01\u0e33": 1, "\u0d4e\u0d15": 1, "\u0915\u094d\u0905": 2,
    "a\u200db": 2, "\r\u0301\n\u0301\t\u0301": 6, "\u0915\u094d\u200d\u0937": 1,
    # repair 2026-10-20: ZWNJ after a virama ends the conjunct (GB9c's InCB=Extend has ZWJ, not ZWNJ), with or
    # without a ZWJ beside it; a trailing ZWNJ still attaches
    "\u0915\u094d\u200c\u0937": 2, "\u0915\u094d\u200c\u200d\u0937": 2, "\u0915\u094d\u200d\u200c\u0937": 2,
    "\u0915\u094d\u0937\u200c": 1,
}


class GraphemeTest(unittest.TestCase):
    def test_stdlib_fallback_counts(self):
        for s, n in CASES.items():
            self.assertEqual(n, pcw._graphemes_stdlib(s), repr(s))

    def test_matches_regex_on_gallery_texts(self):
        try:
            import regex
        except ImportError:
            self.skipTest("regex not installed; the fixed cases above cover the fallback")
        texts = []

        def walk(o):
            if isinstance(o, str) and len(o) > 3:
                texts.append(o)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        for f in sorted((ROOT / "gallery").glob("*.json")):
            walk(json.loads(f.read_text(encoding="utf-8")))
        bad = [t[:40] for t in texts if len(regex.findall(r"\X", t)) != pcw._graphemes_stdlib(t)]
        self.assertEqual([], bad)


if __name__ == "__main__":
    unittest.main()
