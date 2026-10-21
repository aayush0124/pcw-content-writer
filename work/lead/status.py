"""Verify-wave status per batch: cards, samples written, judged, verdicts, cards fixed after judging."""
import json, os, sys
from collections import Counter
from pathlib import Path

HOME = Path(os.environ.get("PCW_HOME") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(HOME))
import pcw  # noqa: E402

G = HOME / "gallery"
by = {}
for c in pcw.cards():
    by.setdefault(c["_file"], []).append(c)
print(f"{'file':16}{'cards':>6}{'samples':>8}{'judged':>7}{'pass':>5}{'weak':>5}{'wrong':>6}{'fixed':>6}{'untested':>9}")
tot = Counter()
for f in sorted(by):
    if not f.startswith(("genre", "hook", "framework")):
        continue
    cs = by[f]
    try:  # cards with a demo piece (a duplicated or stray sample is not one more card covered)
        ns = len({s.get("id") for s in json.loads((G / f).read_text(encoding="utf-8"))["samples"]} & {c["id"] for c in cs})
    except Exception:  # noqa: BLE001  (no gallery yet)
        ns = 0
    v = Counter((c.get("verified") or {}).get("verdict") for c in cs)
    fx = sum("CARD FIXED" in (c.get("verified") or {}).get("note", "") for c in cs)
    # judged = a pass / weak / wrong verdict; a not_tested card has no judgement yet (its own column)
    row = dict(cards=len(cs), samples=ns, judged=len(cs) - v[None] - v["not_tested"], p=v["pass"], w=v["weak"],
               x=v["wrong"], fx=fx, nt=v["not_tested"])
    tot.update(row)
    print(f"{f:16}{row['cards']:6}{ns:8}{row['judged']:7}{row['p']:5}{row['w']:5}{row['x']:6}{fx:6}{row['nt']:9}")
print(f"{'TOTAL':16}{tot['cards']:6}{tot['samples']:8}{tot['judged']:7}{tot['p']:5}{tot['w']:5}{tot['x']:6}{tot['fx']:6}"
      f"{tot['nt']:9}")
