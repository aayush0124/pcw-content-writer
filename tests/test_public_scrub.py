"""Public-scrub gate: nothing tracked (or about to be tracked) may hold a machine path, a client / employer / party
name, an internal system name, personal data, a credential, a vendor or project file, a file over 5 MB, or a
third-party quote over 25 words.

Banned names are stored as truncated SHA-256 hashes of lower-cased word n-grams, so this public file does not
publish the very names it keeps out.

Modes:
  default (strict)       every hit fails. This is the mode CI runs.
  PCW_SCRUB_STRICT=0     transitional: hits in content the content wave still owns (cards/, gallery/, work/, and
                         PCW.md, which is generated from cards) are printed and that test is skipped; code, docs,
                         harvest and skill must still be clean. Fix list: work/repo_prep/scrub_cards_todo.json.
"""
import hashlib, json, os, re, subprocess, sys, unittest
from pathlib import Path

HOME = Path(os.environ.get("PCW_HOME") or Path(__file__).resolve().parents[1]).resolve()
STRICT = os.environ.get("PCW_SCRUB_STRICT", "1") != "0"
CONTENT = ("cards/", "gallery/", "work/", "PCW.md")
MAX_BYTES = 5 * 1024 * 1024
MAX_QUOTE_WORDS = 25
VENDOR_EXT = {".ffx", ".mogrt", ".cube", ".look", ".prfpset", ".abr", ".atn", ".grd", ".pat", ".asl", ".csh", ".aia",
              ".aep", ".prproj", ".psd", ".ai", ".cdr", ".exe", ".dll", ".msi"}
REGEX = [
    ("machine path", re.compile(r"(?<![\w/])[A-Za-z]:[\\/]+\w|AppData[\\/]+Local|(?<!\w)/(home|Users)/\w|/t[m]p/|[\\/]scratchpad[\\/]")),
    ("personal email", re.compile(r"(?i)[\w.+-]+@(gmail|googlemail|yahoo|hotmail|outlook|live|icloud|proton|protonmail|rediffmail)\.\w+")),
    ("credential", re.compile(r"sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16}"
                              r"|xox[abp]-[\w-]{10,}|AIza[\w-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY"
                              r"|(?i:(api[_-]?key|access[_-]?token|secret|password)[\"']?\s*[:=]\s*[\"'][^\"'\s]{8,})")),
    ("episode path", re.compile(r"episodes[\\/]+\w")),
]
PLACEHOLDER = re.compile(r"(?i)your|xxxx|example|placeholder|dummy|changeme|<")  # sample keys in docs are fine
PHONE = re.compile(r"\+91[\s-]?\d{5}[\s-]?\d{5}")
# client / employer / party / leader names and internal system names (see the module docstring)
BANNED = {'c9c61db581934f1d', '1c2d1d71cee24643', '9402bbacd28022cd', '8b719d108e8a63a9', '44c8cf4ce0611762',
          '0a16bea95629a2ec', 'd2f65c844120c0fe', '71556e2c1c3aa8fd', '12a1f2cfbafe21c2', '625bbf6071ab7828',
          '93080e35013dc52a', '4fddbb2dab7dc1da', 'e8e6aa88f69f1851', 'fe3d1e75ae191950', '675275c40dd78df1',
          '49819657d919dc82', '0f5a0d85a5adbf02', 'e0b06cec9dc555f9', 'ee6bdf51cd594100', '641feac462dd8586',
          '0adb48c0abaa30f1', '126cd968858fc2e8', '25abaa87300c65e1', 'cefda6c2fa87f75e', 'd90d0b04e1bba779',
          '10c42a2f4b28ce96', 'b5a0295a00bd9ac9', '0b89ac28ee89f35f', '43f4dba240721db1', '08d15f49576fb7f0',
          '5533a8949925d7a5', '8e42d1dd5b4ac1af', 'fa4e798f81651e7d'}
FIRST = {'089bbc5f7a9ac7b3', '08d15f49576fb7f0', '0a16bea95629a2ec', '0c77c53ce5bb0873', '13a186cf9f5e7118',
         '1c2d1d71cee24643', '25abaa87300c65e1', '2dadabdfcfc35f0e', '32e83e92d45d71f6', '3db20e1df89a35ea',
         '44c8cf4ce0611762', '49819657d919dc82', '4fddbb2dab7dc1da', '5533a8949925d7a5', '5d2ada361b47f841',
         '623f0b5584eb86d9', '675275c40dd78df1', '8b719d108e8a63a9', '8e41e925da60505f', '8e42d1dd5b4ac1af',
         '93080e35013dc52a', '9402bbacd28022cd', 'af4a400a2ceb7963', 'bd875c1bcfcb8baa', 'c9c61db581934f1d',
         'e75eb6e2d3fb49fb', 'ea9724e2e43fd7fd', 'ec08467ce12be512', 'eda565a9067e4049', 'ee6bdf51cd594100',
         'fb04dcb6970e4c3d', 'fb9ebf18103e119e', 'fe3d1e75ae191950'}
# a quoted span: "...", curly quotes, or '...' (an apostrophe inside a word does not end it)
SPAN = re.compile(r'"([^"]+)"|“([^”]+)”|‘([^’]+)’|(?<![\w])\'((?:[^\']|(?<=\w)\'(?=\w))+?)\'(?![\w])')
CARD_QUOTE_KEYS = {"quote", "rule", "claim", "supports", "penalty"}  # card fields that carry a source's words


def _h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def tracked():
    """Files git tracks or would track (cached + untracked-not-ignored)."""
    try:
        out = subprocess.run(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=HOME,
                             capture_output=True, check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError) as e:
        raise unittest.SkipTest(f"not a git checkout ({e}); the scrub needs git ls-files")
    return sorted({f for f in out.split("\0") if f and (HOME / f).is_file()})


def _walk(v, path):
    if isinstance(v, str):
        yield path, v
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _walk(x, f"{path}[{i}]")
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _walk(x, f"{path}.{k}")


def strings(rel):
    """(where, text) for every string in a file: decoded JSON strings, else lines."""
    try:
        text = (HOME / rel).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    if rel.endswith(".json"):
        try:
            yield from _walk(json.loads(text), "")
            return
        except ValueError:
            pass
    for n, line in enumerate(text.splitlines(), 1):
        if rel.endswith(".jsonl"):
            try:
                for where, s in _walk(json.loads(line), ""):
                    yield f"line {n}{where}", s
                continue
            except ValueError:
                pass
        yield f"line {n}", line


def banned_ngrams(s):
    toks = re.findall(r"\w+", s.lower())
    for i, t in enumerate(toks):
        if _h(t) in FIRST:
            for n in (1, 2, 3):
                g = " ".join(toks[i:i + n])
                if len(toks) >= i + n and _h(g) in BANNED:
                    yield g


def long_quotes(rel, where, s):
    key = re.sub(r"\[\d+\]", "", where).rsplit(".", 1)[-1]
    if rel.startswith(("harvest/", "work/batches/")):
        pass  # research text: every field
    elif rel.startswith("cards/") and (key in CARD_QUOTE_KEYS or ".algorithm_notes[" in where):
        pass
    else:
        return
    if key == "quote":
        if len(s.split()) > MAX_QUOTE_WORDS:
            yield s
        return
    for m in SPAN.finditer(s):
        q = next(g for g in m.groups() if g)
        if len(q.split()) > MAX_QUOTE_WORDS:
            yield q


def scan(files):
    hits = []
    for rel in files:
        size = (HOME / rel).stat().st_size
        if size > MAX_BYTES:
            hits.append((rel, "", "file over 5 MB", f"{size / 2**20:.1f} MB"))
        if Path(rel).suffix.lower() in VENDOR_EXT:
            hits.append((rel, "", "vendor/project file", rel))
        for where, s in strings(rel):
            for rule, rx in REGEX:
                hits += [(rel, where, rule, m.group(0)) for m in rx.finditer(s)
                         if not (rule == "credential" and PLACEHOLDER.search(m.group(0)))]
            for m in PHONE.finditer(s):
                d = re.sub(r"\D", "", m.group(0))[-10:]
                if not (d.endswith("00000") or d[1:].count("0") >= 7):  # 90000 00000-style demo numbers are fine
                    hits.append((rel, where, "phone number", m.group(0)))
            hits += [(rel, where, "banned name", g) for g in banned_ngrams(s)]
            hits += [(rel, where, f"quote over {MAX_QUOTE_WORDS} words", q[:80] + "...") for q in long_quotes(rel, where, s)]
    return hits


def _fmt(hits):
    return "\n".join(f"  {f} {w} [{r}] {t!r}" for f, w, r, t in hits)


class PublicScrub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tracked()
        cls.hits = scan(cls.files)

    def test_files_found(self):
        self.assertIn("pcw.py", self.files)
        self.assertTrue(any(f.startswith("harvest/") for f in self.files))

    def test_code_docs_harvest_skill_clean(self):
        bad = [h for h in self.hits if not h[0].startswith(CONTENT)]
        self.assertEqual(bad, [], "public-scrub hits outside the content folders:\n" + _fmt(bad))

    def test_content_clean(self):
        bad = [h for h in self.hits if h[0].startswith(CONTENT)]
        if bad and not STRICT:
            print(f"\n[scrub, transitional] {len(bad)} hit(s) in cards/ gallery/ work/ PCW.md:\n{_fmt(bad)}",
                  file=sys.stderr)
            self.skipTest(f"{len(bad)} content hit(s); PCW_SCRUB_STRICT=0 (fix list: work/repo_prep/scrub_cards_todo.json)")
        self.assertEqual(bad, [], "public-scrub hits in content:\n" + _fmt(bad))

    def test_scanner_catches_known_bad(self):
        """Negative test: the rules fire on planted examples (built at run time so this file stays clean)."""
        drive = "E" + ":" + "\\" + "Somewhere\\x"
        self.assertTrue(REGEX[0][1].search(drive))
        self.assertTrue(PHONE.search("+91 " + "98290 1234" + "5"))
        name = "".join(map(chr, (98, 106, 112)))  # a banned party abbreviation
        self.assertEqual(list(banned_ngrams(f"vote for the {name} now")), [name])
        self.assertEqual(list(long_quotes("harvest/x.json", ".note", "says '" + "word " * 30 + "end'")), ["word " * 30 + "end"])
        self.assertEqual(list(long_quotes("cards/x.json", ".mini_example", '"' + "w " * 40 + '"')), [])


if __name__ == "__main__":
    unittest.main()
