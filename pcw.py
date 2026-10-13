"""PCW ("professional content writer"): every genre, framework, technique, hook, platform limit, tone, language,
editing pass, legal rule and 2026 trend a writing job needs, harvested from cited sources, written up as knowledge
cards and tested by writing a demo piece from each card. Writing sessions read it before they write. See CONTRACT.md.

    python pcw.py brief "cold email to D2C founders" [--genre ID] [--platform ID] [--lang ID] [--tone ID]
    python pcw.py check draft.txt [--genre ID] [--platform ID] [--field NAME]   lint a draft (exit 1 on fails)
    python pcw.py find "landing page saas" [kind]       search cards
    python pcw.py card genre:cold_email                 one card in full
    python pcw.py ids [kind] [words]                    harvested ids (for cross-references)
    python pcw.py validate [file ...]                   harvest + cards (default: everything)
    python pcw.py dupes                                 harvest items that look like the same thing
    python pcw.py batches [kind ...]                    merged harvest -> work/batches/<kind>_<nn>.json
    python pcw.py stats | docs                          counts | regenerate PCW.md

    import sys; sys.path.insert(0, "<path to this folder>"); import pcw
    pcw.brief("press release"); pcw.check_text(text, genre="genre:press_release") -> (fails, warns, info)

Data (harvest/, cards/, work/, PCW.md) is read from the folder this file is in, or from $PCW_HOME when it is set.
"""
import json, os, re, sys, warnings
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path

HERE = Path(os.environ.get("PCW_HOME") or Path(__file__).parent).resolve()
KINDS = {"genre": "genre", "framework": "fw", "technique": "tech", "hook": "hook", "platform": "plat", "tone": "tone",
         "language": "lang", "editing": "edit", "compliance": "comp", "trend": "trend"}
PREFIX_KIND = {v: k for k, v in KINDS.items()}
ID_RE = re.compile(r"^(%s):[a-z0-9_]+$" % "|".join(KINDS.values()))
STATUS = {"current", "rising", "declining", "dated", "niche"}
CONF = {"high", "medium", "low"}
VALUE = {"high", "medium", "low"}
VERDICT = {"pass", "weak", "wrong", "not_tested"}
UNITS = {"chars", "words", "bytes", "lines", "count", "px", "seconds"}
TREND_FLOOR = "2025-10-04"  # trend evidence must be published on or after this date (12 months before the harvest)
COMMON = ("id", "kind", "name", "status", "summary", "use_for", "avoid", "confidence")
KIND_FIELDS = {
    "genre": ("buyers", "value", "goal", "structure", "length", "frameworks", "techniques", "checklist", "pitfalls",
              "lint", "exemplar_brief"),
    "framework": ("steps", "best_for", "not_for", "mini_example"),
    "technique": ("level", "how", "before", "after", "overuse_signs"),
    "hook": ("templates", "examples", "why_it_works", "works_on", "risk"),
    "platform": ("limits", "formatting", "writing_notes"),
    "tone": ("markers", "avoid", "sample", "fits"),
    "language": ("rules", "mistakes", "sample", "script"),
    "editing": ("steps", "checks"),
    "compliance": ("jurisdiction", "applies_to", "rules", "checks", "as_of"),
    "trend": ("as_of", "evidence", "do", "dont", "half_life_months"),
}
NEEDS_SOURCES = {"platform", "compliance", "trend"}
REF_FIELDS = ("related", "frameworks", "techniques", "hooks", "platforms", "tones", "languages", "compliance", "fits",
              "works_on")
LINT_KEYS = {"min_words", "max_words", "max_sentence_words", "max_avg_sentence_words", "grade_max", "require", "ban",
             "max_exclamations", "max_emoji", "max_hashtags"}

# High-signal AI tells, applied to every draft (the full method is the humanizer skill: edit:ai_tell_removal).
AI_TELLS = [
    ("AI vocabulary", r"(?i)\b(delve|delves|delving|tapestry|testament to|underscores?|pivotal|showcas(e|es|ing)|"
                      r"foster(s|ing)?|intricate|interplay|garner|vibrant|seamless(ly)?|game[- ]changer|"
                      r"unlock (the|your)|elevate (your|the)|in today's (fast-paced|digital|ever-changing))\b"),
    ("not X but Y", r"(?i)\b(it'?s|this is|that'?s) not (just |only |merely )?(about )?[^.!?\n]{1,40}[,;—–-] ?(it'?s|but)\b"),
    ("filler phrase", r"(?i)\b(in order to|due to the fact that|at this point in time|it is important to note that|"
                      r"it'?s worth noting that|needless to say)\b"),
    ("fake-candid opener", r"(?im)^(honestly\?|here'?s the thing|let'?s be honest|real talk)"),
    ("generic send-off", r"(?i)\b(the future (looks|is) bright|exciting times (lie|are) ahead|journey towards? excellence)\b"),
    ("chatbot residue", r"(?i)\b(as an ai|i hope this helps|certainly!|great question|let me know if you)\b"),
]
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")


# ---------------------------------------------------------------- loading

def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001  (reported by validate; a file mid-write is skipped by the loaders)
        return {"_error": f"{path}: {e}"}


@lru_cache(None)
def harvest():
    """id -> merged item (first file wins the fields, sources and aliases are unioned)."""
    out = {}
    for f in sorted((HERE / "harvest").glob("*.json")):
        d = _load(f)
        for it in d.get("items") or []:
            iid = it.get("id")
            if not iid:
                continue
            if iid in out:
                m = out[iid]
                m["sources"] = (m.get("sources") or []) + [s for s in it.get("sources") or []
                                                            if s.get("url") not in {x.get("url") for x in m.get("sources") or []}]
                m["aliases"] = sorted(set(m.get("aliases") or []) | set(it.get("aliases") or []))
                m["_files"].append(f.name)
            else:
                out[iid] = dict(it, kind=d.get("kind") or PREFIX_KIND.get(iid.split(":")[0]), _files=[f.name])
    return out


@lru_cache(None)
def cards():
    out = []
    for f in sorted((HERE / "cards").glob("*.json")):
        for c in _load(f).get("cards") or []:
            out.append(dict(c, _file=f.name))
    return out


def card(cid):
    n = cid.lower()
    hit = [c for c in cards() if c.get("id", "").lower() == n] or \
          [c for c in cards() if c.get("name", "").lower() == n]
    return hit[0] if hit else None


STOP = {"about", "for", "the", "an", "to", "my", "our", "your", "of", "on", "in", "with", "and", "me", "us", "write",
        "make", "create", "need", "want", "please", "some", "this", "that", "from", "by", "at", "is", "it"}


def _words(q):
    return [w for w in re.split(r"\W+", q.lower()) if len(w) > 1 and w not in STOP]


def find(query, kind=None, limit=20):
    """Rank cards by query words in name / id / summary / use_for / aliases (name + id hits weigh most); verified
    passes and current items float up."""
    words, scored = _words(query), []
    hv = harvest()
    for c in cards():
        if kind and c.get("kind") != kind:
            continue
        head = " ".join([c.get("name", ""), c.get("id", "").replace("_", " "),
                         " ".join((hv.get(c.get("id")) or {}).get("aliases") or [])]).lower()
        hay = " ".join([head, c.get("summary", ""), " ".join(c.get("use_for") or []),
                        (hv.get(c.get("id")) or {}).get("category", "")]).lower()
        s = sum(3 * (w in head) + min(hay.count(w), 3) for w in words)
        q = " ".join(words)  # a whole alias or name inside the request is the strongest signal ("reel script")
        names = re.split(r"\s*/\s*", re.sub(r"\(.*?\)", "", c.get("name", "")))  # "A / B (x)" -> "A", "B"
        s += 6 * sum(1 for a in names + list((hv.get(c.get("id")) or {}).get("aliases") or [])
                     if len(_words(a)) > 1 and " ".join(_words(a)) in q)
        if s:
            v = (c.get("verified") or {}).get("verdict")
            s += (c.get("status") in ("current", "rising")) + 2 * (v == "pass") - 2 * (v == "wrong")
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:limit]]


def ids(kind=None, words=""):
    w = _words(words)
    return [f"{i}  {it.get('name')}" for i, it in sorted(harvest().items())
            if (not kind or it.get("kind") == kind)
            and all(x in (i + " " + it.get("name", "") + " " + " ".join(it.get("aliases") or [])).lower() for x in w)]


# ---------------------------------------------------------------- validation

def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_harvest_file(path):
    d, issues = _load(path), []
    if "_error" in d:
        return [d["_error"]]
    kind = d.get("kind")
    if kind not in KINDS:
        return [f"{path.name}: kind {kind!r} not in {sorted(KINDS)}"]
    for k in ("worker", "as_of", "source", "items"):
        if not d.get(k):
            issues.append(f"{path.name}: missing top-level {k!r}")
    seen = Counter(it.get("id") for it in d.get("items") or [])
    for i, it in enumerate(d.get("items") or []):
        w = f"{path.name} #{i} {it.get('id')}"
        if seen[it.get("id")] > 1:
            issues.append(f"{w}: id repeated in this file")
        if not ID_RE.match(it.get("id") or "") or it["id"].split(":")[0] != KINDS[kind]:
            issues.append(f"{w}: id must be {KINDS[kind]}:<lower_snake>")
        miss = [k for k in ("name", "category", "one_line") if not it.get(k)]
        if miss:
            issues.append(f"{w}: missing {miss}")
        for s in it.get("sources") or []:
            if not str(s.get("url", "")).startswith("http"):
                issues.append(f"{w}: source without an http url: {s}")
        if kind == "genre" and it.get("value") not in VALUE:
            issues.append(f"{w}: genre value must be one of {sorted(VALUE)}")
        if kind == "platform":
            if not it.get("limits"):
                issues.append(f"{w}: platform item needs limits[] (sourced)")
            for lim in it.get("limits") or []:
                miss = [k for k in ("field", "unit", "url", "checked", "confidence") if lim.get(k) in (None, "")]
                if lim.get("max") is None and lim.get("min") is None:
                    miss.append("max (or min)")
                if miss:
                    issues.append(f"{w}: limit {lim.get('field')!r} missing {miss}")
                for k in ("max", "min"):
                    if lim.get(k) is not None and not _is_num(lim.get(k)):
                        issues.append(f"{w}: limit {lim.get('field')!r} {k} must be a number")
                if lim.get("unit") and lim["unit"] not in UNITS:
                    issues.append(f"{w}: limit unit {lim['unit']!r} not in {sorted(UNITS)}")
                if str(lim.get("confidence", "")).split(" ")[0] not in CONF:
                    issues.append(f"{w}: limit confidence must start with high / medium / low")
        if kind == "trend":
            ev = it.get("evidence") or []
            if not ev:
                issues.append(f"{w}: trend needs evidence[]")
            for e in ev:
                if not (e.get("claim") and str(e.get("url", "")).startswith("http") and e.get("date")):
                    issues.append(f"{w}: evidence needs claim, url, date: {e}")
            if ev and max(str(e.get("date", "")) for e in ev) < TREND_FLOOR:
                issues.append(f"{w}: newest evidence is older than {TREND_FLOOR}: not a 2026 trend")
        if kind in NEEDS_SOURCES and kind != "platform" and not it.get("sources") and not it.get("evidence"):
            issues.append(f"{w}: {kind} item needs sources[]")
    return issues


def _batch_for(card_file):
    b = HERE / "work" / "batches" / card_file.name
    return _load(b) if b.exists() else None


def check_card(c, hv):
    w, issues = c.get("id") or c.get("name"), []
    kind = c.get("kind")
    miss = [f for f in COMMON + KIND_FIELDS.get(kind, ()) if c.get(f) in (None, "", [], {})]
    if kind not in KINDS:
        return [f"{w}: kind {kind!r} not in {sorted(KINDS)}"]
    if miss:
        issues.append(f"{w}: missing {miss}")
    it = hv.get(c.get("id"))
    if hv and not it:
        issues.append(f"{w}: id is not in the harvest (python pcw.py ids {kind} ...)")
    elif it and c.get("name") != it.get("name"):
        issues.append(f"{w}: name {c.get('name')!r} must be the harvested name {it.get('name')!r}")
    if c.get("status") and c["status"] not in STATUS:
        issues.append(f"{w}: status {c['status']!r} not in {sorted(STATUS)}")
    if c.get("confidence") and c["confidence"] not in CONF:
        issues.append(f"{w}: confidence {c['confidence']!r} not in {sorted(CONF)}")
    if kind in NEEDS_SOURCES and not c.get("sources") and not c.get("evidence"):
        issues.append(f"{w}: a {kind} card needs sources")
    for s in c.get("sources") or []:
        if not str(s.get("url", "")).startswith("http"):
            issues.append(f"{w}: source without an http url: {s}")
    for f in REF_FIELDS:
        v = c.get(f)
        if f == "compliance" and kind == "compliance":
            continue
        refs = v if isinstance(v, list) else []
        bad = [r for r in refs if isinstance(r, str) and ID_RE.match(r) and hv and r not in hv]
        junk = [r for r in refs if not (isinstance(r, str) and ID_RE.match(r))]
        if f == "applies_to":
            continue
        if bad:
            issues.append(f"{w}: {f} names ids not in the harvest: {bad[:8]}")
        if junk:
            issues.append(f"{w}: {f} must hold PCW ids (prefix:slug), got {junk[:5]}")
    if c.get("id") in (c.get("related") or []):
        issues.append(f"{w}: related lists itself")
    if kind == "genre":
        if c.get("value") and c["value"] not in VALUE:
            issues.append(f"{w}: value must be one of {sorted(VALUE)}")
        for p in c.get("structure") or []:
            if not (isinstance(p, dict) and p.get("part") and p.get("does")):
                issues.append(f"{w}: structure entries need part + does")
                break
        lint = c.get("lint") or {}
        unknown = set(lint) - LINT_KEYS
        if unknown:
            issues.append(f"{w}: lint has unknown keys {sorted(unknown)} (allowed {sorted(LINT_KEYS)})")
        for k in ("require", "ban"):
            for r in lint.get(k) or []:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error")  # e.g. "possible nested set": meaning may change later
                        re.compile(r.get("regex", ""))
                    if not r.get("label") or not r.get("regex"):
                        raise ValueError("needs label + regex")
                except Exception as e:  # noqa: BLE001
                    issues.append(f"{w}: lint.{k} entry {r}: {e}")
        if lint.get("min_words") and lint.get("max_words") and lint["min_words"] > lint["max_words"]:
            issues.append(f"{w}: lint min_words > max_words")
    if kind == "platform" and it:
        hl = {(l.get("field"), l.get("max"), l.get("min")) for l in it.get("limits") or []}
        cl = {(l.get("field"), l.get("max"), l.get("min")) for l in c.get("limits") or []}
        if hl and cl != hl:
            issues.append(f"{w}: limits must be the harvested limits unchanged: harvest {sorted(hl, key=str)} "
                          f"card {sorted(cl, key=str)}")
    if kind == "hook" and len(c.get("examples") or []) < 3:
        issues.append(f"{w}: hook needs >= 3 examples")
    if kind == "framework":
        for s in c.get("steps") or []:
            if not (isinstance(s, dict) and s.get("step") and s.get("does")):
                issues.append(f"{w}: steps entries need step + does")
                break
        if len((c.get("mini_example") or "").split()) > 140:
            issues.append(f"{w}: mini_example over 120 words")
    if kind == "trend" and c.get("evidence") and max(str(e.get("date", "")) for e in c["evidence"]) < TREND_FLOOR:
        issues.append(f"{w}: newest evidence older than {TREND_FLOOR}")
    v = c.get("verified")
    if v:
        if v.get("verdict") not in VERDICT:
            issues.append(f"{w}: verified.verdict {v.get('verdict')!r} not in {sorted(VERDICT)}")
        if v.get("verdict") in ("pass", "weak", "wrong") and not _is_num(v.get("score")):
            issues.append(f"{w}: verified.score must be a number 0-10")
    return issues


def check_card_file(path):
    d = _load(path)
    if "_error" in d:
        return [d["_error"]]
    hv, cs = harvest(), d.get("cards") or []
    issues = [f"{path.name}: {x}" for c in cs for x in check_card(c, hv)]
    b = _batch_for(path)
    if b:
        want = {it["id"] for it in b.get("items") or []}
        got = Counter(c.get("id") for c in cs)
        issues += [f"{path.name}: missing card for {i}" for i in sorted(want - set(got))]
        issues += [f"{path.name}: {i} is not in this batch" for i in sorted(set(got) - want)]
        issues += [f"{path.name}: {n} cards for {i}" for i, n in got.items() if n > 1]
    return issues


def validate(paths=None):
    harvest.cache_clear(); cards.cache_clear()
    if not paths:
        paths = sorted((HERE / "harvest").glob("*.json")) + sorted((HERE / "cards").glob("*.json"))
        dup = Counter(c.get("id") for c in cards())
        glob = [f"duplicate card id across files: {i} ({n}x)" for i, n in dup.items() if n > 1]
    else:
        glob = []
    issues = []
    for p in map(Path, paths):
        p = p if p.is_absolute() else (Path.cwd() / p if (Path.cwd() / p).exists() else HERE / p)
        if p.parent.name == "harvest":
            issues += check_harvest_file(p)
        elif p.parent.name == "cards":
            if p.name.startswith("zz_"):
                continue
            issues += check_card_file(p)
        elif p.parent.name == "gallery":
            d, known = _load(p), {c.get("id") for c in cards()}
            ss = d.get("samples") or []
            issues += [d["_error"]] if "_error" in d else []
            issues += [f"{p.name}: sample {s.get('id')!r} missing {[k for k in ('id', 'brief', 'text', 'check', 'writer') if not s.get(k)]}"
                       for s in ss if not all(s.get(k) for k in ("id", "brief", "text", "check", "writer"))]
            issues += [f"{p.name}: {s.get('id')} is not a card" for s in ss if s.get("id") not in known]
            issues += [f"{p.name}: {i} has {n} samples" for i, n in Counter(s.get("id") for s in ss).items() if n > 1]
        else:
            issues.append(f"{p}: not under harvest/ or cards/")
    return issues + glob


def dupes():
    """Pairs of harvest items whose normalised names / aliases collide (same kind)."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", re.sub(r"\(.*?\)", "", s.lower())).strip()
    seen, out = {}, []
    for iid, it in harvest().items():
        for n in [it.get("name", ""), iid.split(":")[1].replace("_", " ")] + list(it.get("aliases") or []):
            k = (it.get("kind"), norm(n))
            if k[1] and k in seen and seen[k] != iid:
                out.append(f"{seen[k]}  ~  {iid}   ({n!r}; {'/'.join(harvest()[seen[k]]['_files'])} vs {'/'.join(it['_files'])})")
            seen.setdefault(k, iid)
    return sorted(set(out))


def batches(kinds=None, size=30, sizes={"genre": 20}):
    """Merged harvest -> work/batches/<kind>_<nn>.json (genre cards are the richest, so smaller batches). Safe to
    re-run: items already in a batch file are skipped and new batches are numbered after the existing ones."""
    out = HERE / "work" / "batches"
    out.mkdir(parents=True, exist_ok=True)
    batched, last = set(), Counter()
    for f in out.glob("*.json"):
        batched |= {it["id"] for it in _load(f).get("items") or []}
        k, _, n = f.stem.rpartition("_")
        last[k] = max(last[k], int(n) if n.isdigit() else 0)
    by_kind = {}
    for iid, it in sorted(harvest().items()):
        if (not kinds or it["kind"] in kinds) and iid not in batched:
            by_kind.setdefault(it["kind"], []).append({k: v for k, v in it.items() if k != "_files"})
    made = []
    for kind, items in by_kind.items():
        nb = -(-len(items) // sizes.get(kind, size))  # batch count, then even chunks (no 1-item stragglers)
        step = -(-len(items) // nb)
        for n, i in enumerate(range(0, len(items), step), last[kind] + 1):
            f = out / f"{kind}_{n:02d}.json"
            f.write_text(json.dumps({"kind": kind, "items": items[i:i + step]}, indent=1, ensure_ascii=False),
                         encoding="utf-8")
            made.append(f"{f.name} ({len(items[i:i + step])})")
    return made


# ---------------------------------------------------------------- writing: brief + check

def _short(c, keys):
    return {k: c[k] for k in keys if c.get(k)}


def brief(request="", genre=None, platform=None, lang=None, tone=None):
    """Everything a writer needs for one job, as Markdown: the genre card's structure, length, checklist and lint, its
    frameworks / techniques / hooks (compact), the platform limits, tone + language rules, legal checks, live trends."""
    g = card(genre) if genre else next(iter(find(request, "genre", 1)), None)
    if not g:
        return f"No genre card matches {request!r}. Try: python pcw.py find \"{request}\""
    L = [f"# Brief: {g['name']} ({g['id']})", "", g.get("summary", ""), ""]
    v = g.get("verified") or {}
    if v:  # verdict only: the judge's note is test history, not guidance (and would leak into re-tests)
        L += [f"Card tested: {v.get('verdict')} ({v.get('score')}/10)", ""]
    L += [f"**Goal:** {g.get('goal', '')}", f"**Buyers:** {', '.join(g.get('buyers') or [])}",
          f"**Length:** {json.dumps(g.get('length'), ensure_ascii=False)}", "", "## Structure"]
    L += [f"{i}. **{p['part']}**: {p['does']}" + (f" ({p['length']})" if p.get("length") else "")
          for i, p in enumerate(g.get("structure") or [], 1)]
    L += ["", "## Checklist (every item must be yes)"] + [f"- [ ] {x}" for x in g.get("checklist") or []]
    L += ["", "## Pitfalls"] + [f"- {x}" for x in g.get("pitfalls") or []]
    L += ["", "## Avoid"] + [f"- {x}" for x in g.get("avoid") or []]

    def section(title, ids_, keys, cap=4):
        got = [card(i) for i in (ids_ or [])[:cap]]
        got = [c for c in got if c]
        if not got:
            return []
        out = ["", f"## {title}"]
        for c in got:
            out.append(f"### {c['name']} ({c['id']})")
            for k, val in _short(c, keys).items():
                if isinstance(val, list):
                    val = "; ".join(x if isinstance(x, str) else " / ".join(str(y) for y in x.values()) for x in val)
                out.append(f"- {k}: {val}")
        return out

    L += section("Frameworks", g.get("frameworks"), ("summary", "steps", "best_for"), 3)
    L += section("Techniques", g.get("techniques"), ("how",), 6)
    L += section("Hooks", g.get("hooks"), ("templates", "risk"), 4)
    plats = [platform] if platform else (g.get("platforms") or [])[:2]
    for pid in plats:
        p = card(pid)
        if p:
            L += ["", f"## Platform: {p['name']} ({p['id']})"]
            L += [f"- {l['field']}: " + ", ".join(f"{k} {l[k]}" for k in ("min", "max") if l.get(k) is not None)
                  + f" {l['unit']}" + (f", visible {l['visible']}" if l.get("visible") else "")
                  + f"  [{l.get('confidence', '').split(' ')[0]}, checked {l.get('checked')}]" for l in p.get("limits") or []]
            L += [f"- formatting: {p.get('formatting')}"] + [f"- {x}" for x in p.get("writing_notes") or []]
    for tid in [tone] if tone else (g.get("tones") or [])[:1]:
        t = card(tid)
        if t:
            L += ["", f"## Tone: {t['name']}", f"- markers: {'; '.join(t.get('markers') or [])}",
                  f"- avoid: {'; '.join(t.get('avoid') or [])}"]
    if lang:
        lc = card(lang)
        if lc:
            L += ["", f"## Language: {lc['name']}"] + [f"- {x}" for x in lc.get("rules") or []]
            L += [f"- mistake: {x}" for x in lc.get("mistakes") or []]
    for cid in g.get("compliance") or []:
        c = card(cid)
        if c:
            L += ["", f"## Legal: {c['name']} ({c.get('jurisdiction', '')}, as of {c.get('as_of', '')})"]
            L += [f"- [ ] {x}" for x in c.get("checks") or []]
    rel = {g["id"]} | set(plats)
    tr = [c for c in cards() if c.get("kind") == "trend" and rel & set(c.get("related") or [])]
    if tr:
        L += ["", "## Live trends that touch this job"]
        L += [f"- {c['name']} (as of {c.get('as_of')}): do {'; '.join(c.get('do') or [])}" for c in tr[:4]]
    if g.get("lint"):
        L += ["", "## Lint (python pcw.py check draft.txt --genre " + g["id"] + ")",
              "```json", json.dumps(g["lint"], ensure_ascii=False), "```"]
    L += ["", "Last pass: humanizer skill (edit:ai_tell_removal), then `pcw.py check`."]
    return "\n".join(L)


def _graphemes(text):
    """Visible characters (extended grapheme clusters); code points when the `regex` module is missing."""
    try:
        import regex
        return len(regex.findall(r"\X", text))
    except ImportError:  # ponytail: stdlib has no grapheme segmentation; code points overcount Devanagari
        return len(text)


def _syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def stats_text(text):
    words = [w for w in text.split() if re.search(r"\w", w)]  # table pipes, bullets and dashes are not words
    sents = [s for s in re.split(r"(?<=[.!?।])\s+|(?<=[.!?।][\"'”’)])\s+|\n+|\|", text)  # also ." and .)
             if re.search(r"\w", s)]  # line breaks and table cells end a unit
    sw = [len(s.split()) for s in sents] or [0]
    latin = sum(ch.isascii() and ch.isalpha() for ch in text)
    alpha = sum(ch.isalpha() for ch in text) or 1
    grade = None
    if latin / alpha > 0.9 and words and sents:
        syl = sum(_syllables(w) for w in words)
        grade = round(0.39 * len(words) / len(sents) + 11.8 * syl / len(words) - 15.59, 1)
    return {"words": len(words), "chars": len(text), "sentences": len(sents), "max_sentence_words": max(sw),
            "avg_sentence_words": round(sum(sw) / len(sents), 1) if sents else 0, "fk_grade": grade,
            "exclamations": len(re.findall(r"!(?![\[=])", text)),  # not Markdown images "![" or "!="
            "emoji": len(EMOJI_RE.findall(text)),
            "hashtags": len(re.findall(r"(?<!\w)#\w+", text)), "dashes": len(re.findall(r"[—–]| -- ", text)),
            "devanagari": any("\u0900" <= ch <= "\u097f" for ch in text)}


def check_text(text, genre=None, platform=None, field=None):
    """-> (fails, warns, info). Fails: genre lint and platform limits. Warns: AI tells, dashes, readability drift."""
    text = text.lstrip("﻿").strip()  # a BOM or the file's trailing newline is not part of the copy
    st, fails, warns, info = stats_text(text), [], [], []
    info.append(json.dumps(st, ensure_ascii=False))
    for label, rx in AI_TELLS:
        hits = sorted({m.group(0) for m in re.finditer(rx, text)})
        if hits:
            warns.append(f"AI tell ({label}): {hits[:5]}")
    if st["dashes"]:
        warns.append(f"{st['dashes']} em/en dashes (AI tell unless the brand voice uses them)")
    g = card(genre) if genre else None
    if genre and not g:
        fails.append(f"no genre card {genre!r}")
    lint = (g or {}).get("lint") or {}
    for k, stat, op in (("min_words", "words", "<"), ("max_words", "words", ">"),
                        ("max_sentence_words", "max_sentence_words", ">"),
                        ("max_avg_sentence_words", "avg_sentence_words", ">"),
                        ("max_exclamations", "exclamations", ">"), ("max_emoji", "emoji", ">"),
                        ("max_hashtags", "hashtags", ">")):
        if k in lint and (st[stat] < lint[k] if op == "<" else st[stat] > lint[k]):
            fails.append(f"{k} {lint[k]}: draft has {st[stat]}")
    if "grade_max" in lint and st["fk_grade"] is not None and st["fk_grade"] > lint["grade_max"]:
        fails.append(f"grade_max {lint['grade_max']}: draft reads at grade {st['fk_grade']}")
    for r in lint.get("require") or []:
        if not re.search(r["regex"], text):
            fails.append(f"missing: {r['label']}")
    for r in lint.get("ban") or []:
        m = re.search(r["regex"], text)
        if m:
            fails.append(f"banned ({r['label']}): {m.group(0)!r}")
    p = card(platform) if platform else None
    if platform and not p:
        fails.append(f"no platform card {platform!r}")
    # A limit is lintable when its unit is measurable on the draft; a "count" limit when its field names what to count.
    counts = {"hashtag": st["hashtags"], "emoji": st["emoji"], "mention": len(re.findall(r"(?<!\w)@\w+", text)),
              "link": len(re.findall(r"https?://\S+", text)), "url": len(re.findall(r"https?://\S+", text)),
              "punctuation": len(re.findall(r"[!?.,;:]", text))}
    what = lambda l: next((v for k, v in counts.items() if k in l.get("field", "").lower()), None)  # noqa: E731
    lintable = [l for l in (p or {}).get("limits") or [] if l.get("unit") in ("chars", "words", "bytes", "lines")
                or (l.get("unit") == "count" and what(l) is not None)]
    if field:
        lims = [l for l in lintable if field.lower() in l.get("field", "").lower()]
        if p and not lims:
            fails.append(f"{p['id']} has no lintable limit matching --field {field!r}: "
                         f"{[l['field'] for l in lintable]}")
    elif len(lintable) > 1:  # several fields (headline / description, title / body): the writer must name one
        lims = []
        info.append(f"{p['id']} has {len(lintable)} fields; pass --field <one of> {[l['field'] for l in lintable]}")
    else:
        lims = lintable
    for l in lims:
        n = {"chars": st["chars"], "words": st["words"], "bytes": len(text.encode("utf-8")),
             "lines": text.count("\n") + 1, "count": what(l)}.get(l.get("unit"))
        if n is None:
            continue
        if l.get("min") is not None and l.get("unit") != "count" and n < l["min"]:
            fails.append(f"{p['id']} {l['field']}: {n} {l['unit']} < min {l['min']}")
        if l.get("max") is None:
            continue
        g = _graphemes(text) if l.get("unit") == "chars" else n
        if g > l["max"]:
            fails.append(f"{p['id']} {l['field']}: {n} {l['unit']} > max {l['max']}")
        elif n > l["max"]:  # Devanagari / emoji: over in code points, within visible characters
            warns.append(f"{p['id']} {l['field']}: {n} code points > max {l['max']} but {g} visible characters; "
                         f"check the platform's own counter")
        if l.get("visible") and l.get("unit") == "chars":
            info.append(f"visible before truncation ({l['visible']} chars): {text[:l['visible']]!r}")
    if st["devanagari"] and p and "sms" in p["id"]:
        info.append("Devanagari forces UCS-2 encoding: 70 chars per SMS segment (67 when concatenated)")
    return fails, warns, info


# ---------------------------------------------------------------- docs + stats

def stats():
    hv, cs = harvest(), cards()
    return {"harvest": dict(Counter(it["kind"] for it in hv.values())), "cards": dict(Counter(c["kind"] for c in cs)),
            "verdicts": dict(Counter((c.get("verified") or {}).get("verdict") for c in cs if c.get("verified"))),
            "uncarded": len(set(hv) - {c.get("id") for c in cs})}


DOCS_STAMP = "Generated by `python pcw.py docs` on "


def docs_text(day=None):
    cs, s = cards(), stats()
    L = ["# PCW: professional content writer", "",
         f"{DOCS_STAMP}{day or date.today()}. Contract: `CONTRACT.md`.", "",
         "Before writing anything: `python pcw.py brief \"<what you are writing>\"`; after: "
         "`python pcw.py check draft.txt --genre <id> [--platform <id>]`.", "",
         f"Cards: {sum(s['cards'].values())} ({', '.join(f'{k} {v}' for k, v in sorted(s['cards'].items()))}). "
         f"Verdicts: {s['verdicts']}.", ""]
    for kind in KINDS:
        rows = sorted((c for c in cs if c.get("kind") == kind), key=lambda c: c.get("id"))
        if not rows:
            continue
        L += [f"## {kind} ({len(rows)})", "", "| id | name | status | verified | summary |", "|---|---|---|---|---|"]
        for c in rows:
            v = c.get("verified") or {}
            ver = f"{v.get('verdict')} {v.get('score')}" if v else ""
            L.append(f"| `{c['id']}` | {c['name']} | {c.get('status')} | {ver} | "
                     f"{(c.get('summary') or '').replace('|', '/')[:140]} |")
        L.append("")
    return "\n".join(L)


def _undated(md):
    return "\n".join(l for l in md.splitlines() if not l.startswith(DOCS_STAMP))


def docs_fresh():
    """True when PCW.md matches what `docs` would write today (the date line aside)."""
    f = HERE / "PCW.md"
    return f.exists() and _undated(f.read_text(encoding="utf-8")) == _undated(docs_text())


def docs():
    """Regenerate PCW.md. Rewritten only when the content changed, so re-running is a no-op (no date-only diffs)."""
    if not docs_fresh():
        (HERE / "PCW.md").write_text(docs_text(), encoding="utf-8")
    return HERE / "PCW.md"


def selftest():
    """In-memory checks of the lint and card rules (no files touched)."""
    global card
    real = card
    g = {"id": "genre:t", "kind": "genre", "lint": {"max_words": 12, "require": [{"label": "CTA", "regex": "(?i)reply"}],
                                                   "ban": [{"label": "spam", "regex": "(?i)free money"}]}}
    p = {"id": "plat:t", "limits": [{"field": "body", "max": 40, "unit": "chars", "visible": 10}]}
    card = lambda i: {"genre:t": g, "plat:t": p}.get(i)  # noqa: E731
    try:
        f, w, _ = check_text("We delve into it. Free money — reply today.", "genre:t", "plat:t")
        assert any("spam" in x for x in f) and any("plat:t body" in x for x in f), f
        assert any("AI vocabulary" in x for x in w) and any("dashes" in x for x in w), w
        f, w, _ = check_text("Short note. Reply if useful.", "genre:t", "plat:t")
        assert not f and not w, (f, w)
        f, _, _ = check_text("No call to action here at all.", "genre:t")
        assert f == ["missing: CTA"], f
        p["limits"][0]["max"] = 8  # "नमस्ते दोस्तों" = 14 code points, 6 visible characters
        f, w, _ = check_text("नमस्ते दोस्तों", None, "plat:t")
        assert not f and any("visible characters" in x for x in w), (f, w)
        p["limits"][0]["max"] = 5
        assert not check_text("﻿Hello\r\n", None, "plat:t")[0]  # BOM + newline from an editor do not count
    finally:
        card = real
    assert stats_text("एक दो। तीन")["fk_grade"] is None and stats_text("One two. Three four.")["sentences"] == 2
    assert stats_text('He said "stop." Then he left. (It rained.) Next.')["sentences"] == 4
    assert stats_text("| a b | c |\n![x](y.svg) Done!")["exclamations"] == 1
    hv = {"genre:a": {"name": "A"}, "fw:b": {"name": "B"}}
    base = dict(zip(COMMON, ("genre:a", "genre", "A", "current", "s", ["u"], ["v"], "high")))
    full = dict(base, buyers=["x"], value="high", goal="g", structure=[{"part": "p", "does": "d"}], length={"min": 1},
                frameworks=["fw:b"], techniques=["fw:b"], checklist=["c"], pitfalls=["p"], lint={"max_words": 99}, exemplar_brief="e")
    assert check_card(full, hv) == [], check_card(full, hv)
    assert any("not in the harvest" in x for x in check_card(dict(full, frameworks=["fw:zz"]), hv))
    assert any("unknown keys" in x for x in check_card(dict(full, lint={"max_word": 3}), hv))
    assert any("missing" in x for x in check_card(base, hv))
    return "selftest OK"


# ---------------------------------------------------------------- CLI

def _opt(rest, name):
    if name in rest:
        i = rest.index(name)
        val = rest[i + 1] if i + 1 < len(rest) else None
        del rest[i:i + 2]
        return val
    return None


def _main(argv):
    if not argv:
        print(__doc__)
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cmd, rest = argv[0], list(argv[1:])
    if cmd == "find":
        kind = rest[1] if len(rest) > 1 else None
        for c in find(rest[0], kind):
            v = (c.get("verified") or {}).get("verdict", "")
            print(f"[{c['id']}{' ' + v if v else ''}] {c['name']}: {(c.get('summary') or '')[:110]}")
    elif cmd == "card":
        print(json.dumps(card(rest[0]), indent=1, ensure_ascii=False))
    elif cmd == "ids":
        kind = rest[0] if rest and rest[0] in KINDS else None
        print("\n".join(ids(kind, " ".join(rest[1:] if kind else rest))))
    elif cmd == "brief":
        g, p, l, t = (_opt(rest, x) for x in ("--genre", "--platform", "--lang", "--tone"))
        print(brief(" ".join(rest), g, p, l, t))
    elif cmd == "check":
        g, p, f = (_opt(rest, x) for x in ("--genre", "--platform", "--field"))
        if not (rest and Path(rest[0]).exists()) and sys.stdin.isatty():  # no file and nothing piped: don't hang
            print("usage: python pcw.py check <draft.txt> [--genre ID] [--platform ID] [--field NAME]  (or pipe text in)")
            return 2
        text = Path(rest[0]).read_text(encoding="utf-8") if rest and Path(rest[0]).exists() else sys.stdin.read()
        fails, warns, info = check_text(text, g, p, f)
        print("\n".join([f"[fail] {x}" for x in fails] + [f"[warn] {x}" for x in warns] + [f"[info] {x}" for x in info]))
        print("OK: no fails" if not fails else f"{len(fails)} fail(s)")
        return 1 if fails else 0
    elif cmd == "validate":
        issues = validate(rest or None)
        print("\n".join(issues) or "OK: 0 issues")
        return 1 if issues else 0
    elif cmd == "dupes":
        print("\n".join(dupes()) or "no name collisions")
    elif cmd == "batches":
        print("\n".join(batches(rest or None)))
    elif cmd == "stats":
        print(json.dumps(stats(), indent=1))
    elif cmd == "docs":
        print(docs())
    elif cmd == "selftest":
        print(selftest())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
