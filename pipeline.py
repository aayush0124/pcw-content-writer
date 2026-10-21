"""PCW pipeline: one entry point for every stage of the build (see CONTRACT.md for what each stage produces).

    python pipeline.py status          per-stage counts; exit 0 ok, 10 needs attention, 1 failure
    python pipeline.py run <stage>     one deterministic stage: batches | validate | dupes | fixes | docs
    python pipeline.py doctor          Python, paths, optional modules, free RAM
    python pipeline.py all             every deterministic stage in order (batches, validate, dupes, fixes, docs)

Agent stages (harvest, cards, samples, judge, critic) need an LLM agent; `status` names the file that drives each
one and they never run from CI. Every deterministic stage is idempotent. Paths follow pcw.py: this folder, or
$PCW_HOME when set.
"""
import os, platform, re, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcw  # noqa: E402

HERE = pcw.HERE
LEAD = HERE / "work" / "lead"
OK, ATTENTION, FAIL = 0, 10, 1
STAGES = [  # name, kind, what runs it
    ("harvest", "agent", "research workers: CONTRACT.md 'Harvest file format'; gap fills: work/BRIEF_GAPS.md"),
    ("batches", "code", "python pcw.py batches"),
    ("cards", "agent", "one card writer per work/batches/<batch>.json: work/BRIEF_CARDS.md"),
    ("validate", "code", "python pcw.py validate"),
    ("dupes", "code", "python pcw.py dupes"),
    ("samples", "agent", "writers: work/BRIEF_VERIFY.md, section Writer -> gallery/<batch>.json"),
    ("judge", "agent", "judges: work/BRIEF_VERIFY.md, section Judge -> cards[].verified"),
    ("fixes", "code", "python work/lead/collect_fixes.py -> work/lead/card_fixes.json (a fixer agent applies them)"),
    ("critic", "agent", "CONTRACT.md step 6: cards/zz_critic.json from work/gaps.jsonl and the weak list"),
    ("docs", "code", "python pcw.py docs -> PCW.md, plus the coverage block in README.md"),
]
README_BEGIN, README_END = "<!-- pipeline-status:begin -->", "<!-- pipeline-status:end -->"


def _lead_script(name, *args):
    """Run one of the lead's tools in work/lead/ exactly as the lead does, against this PCW home."""
    script = LEAD / name
    if not script.exists():
        return None
    # the data home's script, but this checkout's pcw.py when the home holds data only
    env = dict(os.environ, PCW_HOME=str(HERE), PYTHONPATH=str(Path(__file__).resolve().parent), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", env=env)
    return r.stdout if r.returncode == 0 else None


def verify_table():
    """work/lead/status.py's per-batch table as {file: {...}, "TOTAL": {...}} (None when the script is missing)."""
    out = _lead_script("status.py")
    if out is None:
        return None
    lines = out.strip().splitlines()
    cols = lines[0].split()[1:]
    return {p[0]: dict(zip(cols, map(int, p[1:]))) for p in (l.split() for l in lines[1:]) if len(p) == len(cols) + 1}


def pending_fixes():
    """Cards whose judge note still asks for a CARD FIX, counted by work/lead/collect_fixes.py (written to a temp
    file, so status never touches the lead's card_fixes.json)."""
    with tempfile.TemporaryDirectory() as d:
        out = _lead_script("collect_fixes.py", Path(d) / "fixes.json")
    m = re.search(r"cards with fixes: (\d+)", out or "")
    return int(m.group(1)) if m else None


def _readme_block(rows):
    keep = [r for r in rows if r["stage"] != "docs"]  # the block is part of the docs: never describe itself
    return "\n".join([README_BEGIN, "| stage | kind | state | numbers |", "|---|---|---|---|"] +
                     [f"| {r['stage']} | {r['kind']} | {r['state']} | {r['numbers']} |" for r in keep] + [README_END])


def _readme_fresh(rows):
    f = HERE / "README.md"
    if not f.exists():
        return True
    t = f.read_text(encoding="utf-8")
    return README_BEGIN not in t or _readme_block(rows) in t


def status_rows():
    pcw.harvest.cache_clear(); pcw.cards.cache_clear(); pcw._card_terms.cache_clear()
    hv, cs = pcw.harvest(), pcw.cards()
    kinds = lambda xs: ", ".join(f"{k} {n}" for k, n in sorted(Counter(xs).items()))  # noqa: E731
    files = sorted((HERE / "harvest").glob("*.json"))
    nsrc = sum(len(it.get("sources") or []) + len(it.get("evidence") or []) for it in hv.values())
    batched = set()
    for f in (HERE / "work" / "batches").glob("*.json"):
        batched |= {it.get("id") for it in pcw._load(f).get("items") or []}
    real = [c for c in cs if not c["_file"].startswith("zz_")]
    uncarded = len(set(hv) - {c.get("id") for c in real})
    issues, dup = pcw.validate(), pcw.dupes()
    vt, fx = verify_table(), pending_fixes()
    rows = [
        dict(stage="harvest", state="ok" if hv else "fail",
             numbers=f"{len(hv)} items from {len(files)} files, {nsrc} cited sources ({kinds(it['kind'] for it in hv.values())})"),
        dict(stage="batches", state="ok" if not set(hv) - batched else "attention",
             numbers=f"{len(set(hv) & batched)}/{len(hv)} items batched"),
        dict(stage="cards", state="ok" if not uncarded else "attention",
             numbers=f"{len(real)} cards, {uncarded} harvest items without a card ({kinds(c['kind'] for c in real)})"),
        dict(stage="validate", state="ok" if not issues else "fail", numbers=f"{len(issues)} issues"),
        dict(stage="dupes", state="ok", numbers=f"{len(dup)} name collisions left for the critic"),
    ]
    if vt and "TOTAL" in vt:
        t = vt["TOTAL"]
        rows += [dict(stage="samples", state="ok" if t["samples"] >= t["cards"] else "attention",
                      numbers=f"{t['samples']}/{t['cards']} genre, hook and framework cards have a demo piece"),
                 dict(stage="judge", state="ok" if t["judged"] >= t["cards"] and not t["wrong"]
                      and not t.get("untested") else "attention",
                      numbers=f"{t['judged']}/{t['cards']} judged: pass {t['pass']}, weak {t['weak']}, wrong {t['wrong']}"
                              f", not_tested {t.get('untested', 0)}; {t['fixed']} cards rewritten after judging")]
    else:
        rows += [dict(stage=s, state="attention", numbers="work/lead/status.py missing or failed") for s in ("samples", "judge")]
    rows.append(dict(stage="fixes", state="attention" if fx is None or fx else "ok",
                     numbers="work/lead/collect_fixes.py missing or failed" if fx is None
                     else f"{fx} cards with an open CARD FIX note"))
    crit = pcw._load(HERE / "cards" / "zz_critic.json") if (HERE / "cards" / "zz_critic.json").exists() else {}
    gaps, bad = pcw.gaps()  # a bad line is reported, never a crash
    as_of = crit.get("as_of") or (crit.get("critic") or {}).get("date")  # old shape: as_of; current: critic.date
    seen = crit.get("gaps_seen")  # how many gap lines the critic read; without it, gaps dated after the critic's day
    later = gaps[seen:] if isinstance(seen, int) and not isinstance(seen, bool) else \
        [g for g in gaps if str(g.get("date", "")) > str(as_of or "")]
    n = lambda k: len(crit.get(k) or [])  # noqa: E731
    rows.append(dict(stage="critic", state="ok" if as_of and not later and not bad else "attention",
                     numbers=((f"zz_critic.json as of {as_of}: {n('gaps')} gaps, {n('weak_cards')} weak cards, "
                               f"{n('doubtful')} doubts, {n('next_steps')} next steps; {len(later)} gaps logged since")
                              if as_of else "no cards/zz_critic.json yet")
                     + (f"; {len(bad)} unreadable lines in work/gaps.jsonl: {[i for i, _ in bad][:10]}" if bad else "")))
    for r in rows:
        r["kind"] = next(k for s, k, _ in STAGES if s == r["stage"])
    fresh = pcw.docs_fresh() and _readme_fresh(rows)
    rows.append(dict(stage="docs", kind="code", state="ok" if fresh else "attention",
                     numbers="PCW.md and the README coverage block are current" if fresh
                     else "stale: python pipeline.py run docs"))
    return rows


def status():
    rows = status_rows()
    run = {s: how for s, _, how in STAGES}
    print(f"{'stage':9}{'kind':7}{'state':11}numbers")
    for r in rows:
        print(f"{r['stage']:9}{r['kind']:7}{r['state']:11}{r['numbers']}")
        if r["state"] != "ok":
            print(f"{'':27}-> {run[r['stage']]}")
    states = {r["state"] for r in rows}
    return FAIL if "fail" in states else ATTENTION if "attention" in states else OK


def run(stage):
    if stage == "batches":
        try:
            made = pcw.batches()
        except ValueError as e:
            print(e)
            return FAIL
        print("\n".join(made) or "every harvest item is already batched")
        return OK
    if stage == "validate":
        issues = pcw.validate()
        print("\n".join(issues) or "OK: 0 issues")
        return FAIL if issues else OK
    if stage == "dupes":
        print("\n".join(pcw.dupes()) or "no name collisions")
        return OK
    if stage == "fixes":
        out = _lead_script("collect_fixes.py", LEAD / "card_fixes.json")
        print(out if out is not None else "work/lead/collect_fixes.py missing or failed")
        return OK if out is not None else FAIL
    if stage == "docs":
        print(pcw.docs())
        f = HERE / "README.md"
        if f.exists() and README_BEGIN in f.read_text(encoding="utf-8"):
            t = f.read_text(encoding="utf-8")
            new = t[:t.index(README_BEGIN)] + _readme_block(status_rows()) + t[t.index(README_END) + len(README_END):]
            if new != t:
                f.write_bytes(new.encode("utf-8"))  # LF, like the rest of the repo
            print(f)
        return OK
    agent = {s: how for s, k, how in STAGES if k == "agent"}
    if stage in agent:
        print(f"{stage} is an agent stage: {agent[stage]}")
        return ATTENTION
    print(__doc__)
    return 2


def free_ram_gb():
    try:
        if os.name == "nt":
            import ctypes

            class Mem(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("total", "avail", "pt", "pa", "vt", "va", "ve")]
            m = Mem(len=ctypes.sizeof(Mem))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.avail / 2 ** 30
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) / 2 ** 20
    except Exception:  # noqa: BLE001  (macOS and others: unknown is fine, nothing here needs much RAM)
        pass
    return None


def doctor():
    checks = []
    py = sys.version_info
    checks.append(("python", f"{platform.python_version()} ({sys.executable})", "ok" if py >= (3, 10) else "fail"))
    checks.append(("PCW_HOME", f"{HERE}" + (" (from $PCW_HOME)" if os.environ.get("PCW_HOME") else " (this folder)"),
                   "ok" if (HERE / "harvest").is_dir() and (HERE / "cards").is_dir() else "fail"))
    for name in ("status.py", "collect_fixes.py"):
        checks.append((f"work/lead/{name}", "found" if (LEAD / name).exists() else "missing",
                       "ok" if (LEAD / name).exists() else "attention"))
    try:
        import regex  # noqa: F401
        checks.append(("regex module", "installed: visible characters counted by full UAX #29", "ok"))
    except ImportError:
        checks.append(("regex module", "not installed: visible characters counted by the stdlib segmenter (agrees on "
                                       "Latin, Indic, emoji, Hangul; rarer scripts may differ; pip install regex)", "ok"))
    ram = free_ram_gb()
    checks.append(("free RAM", f"{ram:.1f} GB" if ram is not None else "unknown", "ok"))
    checks.append(("apps", "none needed: PCW is text-only, offline, standard library", "ok"))
    for name, val, st in checks:
        print(f"{name:28}{st:11}{val}")
    states = {c[2] for c in checks}
    return FAIL if "fail" in states else ATTENTION if "attention" in states else OK


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cmd = argv[0] if argv else ""
    if cmd == "status":
        return status()
    if cmd == "doctor":
        return doctor()
    if cmd == "run" and len(argv) > 1:
        return run(argv[1])
    if cmd == "all":
        for stage in ("batches", "validate", "dupes", "fixes", "docs"):
            print(f"== {stage}")
            code = run(stage)
            if code == FAIL:
                return FAIL
        return OK
    print(__doc__)
    return 0 if not argv else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
