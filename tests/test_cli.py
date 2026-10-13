"""Every pcw.py subcommand, run as a user runs it: exit codes and output shape."""
import json, shutil, tempfile, unittest
from pathlib import Path

from helpers import HOME, cli, snapshot, tmp_home
import pcw


class ReadOnlyCommands(unittest.TestCase):
    """Commands that only read: run against the real tree."""

    def test_no_args_prints_usage(self):
        code, out = cli("pcw.py")
        self.assertEqual(code, 0)
        self.assertIn("python pcw.py brief", out)

    def test_unknown_command_exits_2(self):
        self.assertEqual(cli("pcw.py", "nosuchcmd")[0], 2)

    def test_brief_from_request(self):
        code, out = cli("pcw.py", "brief", "cold email to D2C founders")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("# Brief: "), out[:80])
        self.assertIn("(genre:cold_email)", out.splitlines()[0])
        for section in ("## Structure", "## Checklist (every item must be yes)", "## Pitfalls"):
            self.assertIn(section, out)

    def test_brief_with_overrides(self):
        code, out = cli("pcw.py", "brief", "--genre", "genre:press_release", "--platform", "plat:linkedin_post",
                        "--tone", "tone:authoritative", "--lang", "lang:hinglish")
        self.assertEqual(code, 0)
        self.assertIn("(genre:press_release)", out.splitlines()[0])
        self.assertIn("## Platform: ", out)
        self.assertIn("## Lint (python pcw.py check draft.txt --genre genre:press_release)", out)

    def test_brief_no_match(self):
        code, out = cli("pcw.py", "brief", "--genre", "genre:does_not_exist")
        self.assertEqual(code, 0)
        self.assertIn("No genre card matches", out)

    def test_find(self):
        code, out = cli("pcw.py", "find", "aida", "framework")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("[fw:aida"), out[:80])
        self.assertTrue(all(l.startswith("[fw:") for l in out.splitlines()))

    def test_card(self):
        code, out = cli("pcw.py", "card", "genre:cold_email")
        self.assertEqual(code, 0)
        c = json.loads(out)
        self.assertEqual((c["id"], c["kind"]), ("genre:cold_email", "genre"))
        self.assertEqual(json.loads(cli("pcw.py", "card", "genre:nope")[1]), None)

    def test_ids(self):
        code, out = cli("pcw.py", "ids")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), len(pcw.harvest()))
        plats = cli("pcw.py", "ids", "platform")[1].splitlines()
        self.assertTrue(plats and all(l.startswith("plat:") for l in plats))
        self.assertIn("hook:curiosity_gap", cli("pcw.py", "ids", "hook", "curiosity")[1])

    def test_validate_clean(self):
        code, out = cli("pcw.py", "validate")
        self.assertEqual((code, out.strip()), (0, "OK: 0 issues"))

    def test_dupes(self):
        code, out = cli("pcw.py", "dupes")
        self.assertEqual(code, 0)
        self.assertTrue(out.strip() == "no name collisions" or all("~" in l for l in out.splitlines()))

    def test_stats(self):
        code, out = cli("pcw.py", "stats")
        self.assertEqual(code, 0)
        s = json.loads(out)
        self.assertEqual(set(s), {"harvest", "cards", "verdicts", "uncarded"})
        self.assertEqual(sum(s["harvest"].values()), len(pcw.harvest()))

    def test_selftest(self):
        self.assertEqual(cli("pcw.py", "selftest"), (0, "selftest OK\n"))


class Check(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="pcw_check_"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def draft(self, text):
        p = self.dir / "draft.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_over_limit_post_fails_on_a_quoted_limit(self):
        lim = pcw.harvest()["plat:linkedin_post"]["limits"][0]
        self.assertTrue(lim.get("quote") and lim.get("url"), "the test relies on a sourced, quoted limit")
        code, out = cli("pcw.py", "check", self.draft("x" * (lim["max"] + 100)), "--platform", "plat:linkedin_post")
        self.assertEqual(code, 1)
        self.assertIn(f"[fail] plat:linkedin_post {lim['field']}: {lim['max'] + 100} chars > max {lim['max']}", out)
        self.assertTrue(out.rstrip().endswith("1 fail(s)"))

    def test_within_limit_passes(self):
        code, out = cli("pcw.py", "check", self.draft("Short post. Reply if useful."), "--platform", "plat:linkedin_post")
        self.assertEqual(code, 0)
        self.assertTrue(out.rstrip().endswith("OK: no fails"))

    def test_multi_field_platform_needs_field(self):
        long = self.draft("x" * 100)
        code, out = cli("pcw.py", "check", long, "--platform", "plat:google_ads_rsa")
        self.assertEqual(code, 0)  # several fields and no --field: nothing enforced, the writer is told to pick one
        self.assertIn("[info] plat:google_ads_rsa has", out)
        self.assertIn("pass --field", out)
        code, out = cli("pcw.py", "check", long, "--platform", "plat:google_ads_rsa", "--field", "headline")
        self.assertEqual(code, 1)
        self.assertIn("[fail] plat:google_ads_rsa headline: 100 chars > max 30", out)
        code, out = cli("pcw.py", "check", long, "--platform", "plat:google_ads_rsa", "--field", "no such field")
        self.assertEqual(code, 1)
        self.assertIn("has no lintable limit matching --field", out)

    def test_web_stories_page_text_limit(self):
        """Gap wave C: Google's Web Story content policy: text-heavy pages are over 180 characters."""
        lim = next(l for l in pcw.harvest()["plat:google_web_stories"]["limits"] if "content policy" in l["field"])
        self.assertEqual((lim["max"], lim["unit"]), (180, "chars"))
        self.assertTrue(lim.get("quote") and lim["url"].startswith("https://developers.google.com/"))
        args = ("--platform", "plat:google_web_stories", "--field", "content policy")
        code, out = cli("pcw.py", "check", self.draft("x" * 181), *args)
        self.assertEqual(code, 1)
        self.assertIn(f"[fail] plat:google_web_stories {lim['field']}: 181 chars > max 180", out)
        self.assertEqual(cli("pcw.py", "check", self.draft("x" * 180), *args)[0], 0)

    def test_indiamart_title_limits(self):
        """Gap wave C: IndiaMART titles: under 70 characters (help article), ideally 5 words (approval guidelines)."""
        args = ("--platform", "plat:indiamart_listing", "--field", "product title")
        code, out = cli("pcw.py", "check", self.draft("Stainless Steel Pressure Cooker 5 Litre Induction Base"), *args)
        self.assertEqual(code, 1)
        self.assertIn("[fail] plat:indiamart_listing product title (ideal length): 8 words > max 5", out)
        self.assertNotIn("chars > max 70", out)
        code, out = cli("pcw.py", "check", self.draft(" ".join(["Steel"] * 12)), *args)
        self.assertIn("[fail] plat:indiamart_listing product title: 71 chars > max 70", out)
        self.assertEqual(cli("pcw.py", "check", self.draft("Steel Pressure Cooker 5 Litre"), *args)[0], 0)

    def test_99acres_description_single_lintable_field(self):
        """Gap wave C: the description cap (words) is the only lintable 99acres limit, so no --field is needed."""
        code, out = cli("pcw.py", "check", self.draft(" ".join(["flat"] * 5001)), "--platform", "plat:99acres_listing")
        self.assertEqual(code, 1)
        self.assertIn("[fail] plat:99acres_listing property description: 5001 words > max 5000", out)
        self.assertNotIn("pass --field", out)

    def test_genre_lint_and_ai_tells(self):
        code, out = cli("pcw.py", "check", self.draft("We delve into a tapestry of synergy."), "--genre", "genre:cold_email")
        self.assertIn("[warn] AI tell (AI vocabulary)", out)
        self.assertEqual(code, 1 if "[fail]" in out else 0)

    def test_unknown_ids_fail(self):
        code, out = cli("pcw.py", "check", self.draft("Hello."), "--genre", "genre:nope", "--platform", "plat:nope")
        self.assertEqual(code, 1)
        self.assertIn("[fail] no genre card 'genre:nope'", out)
        self.assertIn("[fail] no platform card 'plat:nope'", out)

    def test_stdin(self):
        code, out = cli("pcw.py", "check", "--platform", "plat:linkedin_post", stdin="Piped text works.")
        self.assertEqual(code, 0)
        self.assertIn("OK: no fails", out)


class WritingCommands(unittest.TestCase):
    """batches, docs and validate on a bad file: run on a throwaway copy, never on the real tree."""

    @classmethod
    def setUpClass(cls):
        cls.home = tmp_home()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_batches_idempotent(self):
        before = snapshot(self.home / "work" / "batches")
        self.assertEqual(cli("pcw.py", "batches", home=self.home), (0, "\n"))
        self.assertEqual(snapshot(self.home / "work" / "batches"), before)

    def test_batches_rebuilds_a_missing_batch_once(self):
        b = self.home / "work" / "batches" / "tone_03.json"
        ids = {it["id"] for it in json.loads(b.read_text(encoding="utf-8"))["items"]}
        b.unlink()
        code, out = cli("pcw.py", "batches", "tone", home=self.home)
        self.assertEqual(code, 0)
        made = json.loads((self.home / "work" / "batches" / "tone_03.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual({it["id"] for it in made}, ids)
        self.assertEqual(cli("pcw.py", "batches", home=self.home), (0, "\n"))

    def test_docs_reproducible(self):
        code, out = cli("pcw.py", "docs", home=self.home)
        self.assertEqual(code, 0)
        md = self.home / "PCW.md"
        self.assertEqual(Path(out.strip()), md)
        first = md.read_bytes()
        cli("pcw.py", "docs", home=self.home)
        self.assertEqual(md.read_bytes(), first)
        self.assertIn("# PCW: professional content writer", first.decode("utf-8"))

    def test_validate_flags_a_bad_card(self):
        bad = self.home / "cards" / "tmp_bad.json"
        bad.write_text(json.dumps({"cards": [{"id": "genre:cold_email", "kind": "genre", "name": "wrong name",
                                              "related": ["fw:not_a_real_id"]}]}), encoding="utf-8")
        try:
            code, out = cli("pcw.py", "validate", bad, home=self.home)
            self.assertEqual(code, 1)
            self.assertIn("missing", out)
            self.assertIn("must be the harvested name", out)
            self.assertIn("names ids not in the harvest", out)
        finally:
            bad.unlink()


if __name__ == "__main__":
    unittest.main()
