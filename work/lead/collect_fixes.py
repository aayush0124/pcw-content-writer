"""Collect judges' CARD FIX notes from verified.note into work/lead/card_fixes.json, grouped by card file.
Skips cards already fixed (note carries "CARD FIXED"). Prints per-file counts and the verdict totals."""
import json, os, re, sys
from collections import Counter
from pathlib import Path

HOME = Path(os.environ.get("PCW_HOME") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(HOME))
import pcw  # noqa: E402

only = set(sys.argv[2:])  # optional: collect_fixes.py <out.json> genre_07.json genre_09.json ...
dest = sys.argv[1] if len(sys.argv) > 1 else HOME / "work" / "lead" / "card_fixes.json"
out, verdicts = {}, Counter()
for c in pcw.cards():
    if only and c["_file"] not in only:
        continue
    v = c.get("verified") or {}
    if v:
        verdicts[v.get("verdict")] += 1
    note = v.get("note", "")
    if "CARD FIX" not in note or "CARD FIXED" in note:
        continue
    fixes = [f.strip(" .;") for f in re.findall(r"CARD FIX:?\s*(.+?)(?=CARD FIX|$)", note, re.S)]
    out.setdefault(c["_file"], []).append({"id": c["id"], "verdict": v.get("verdict"), "score": v.get("score"),
                                            "fixes": fixes})
Path(dest).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
print("verdicts:", dict(verdicts))
print({f: len(v) for f, v in sorted(out.items())}, "cards with fixes:", sum(len(v) for v in out.values()))
