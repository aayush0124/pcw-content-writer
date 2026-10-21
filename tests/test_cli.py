"""Every pcw.py subcommand, run as a user runs it: exit codes and output shape."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

from helpers import HOME, cli, cli3, snapshot, tmp_home
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
                        "--tone", "tone:authoritative", "--lang", "lang:hinglish_roman")
        self.assertEqual(code, 0)
        self.assertIn("(genre:press_release)", out.splitlines()[0])
        for section in ("## Platform: ", "## Tone: ", "## Language: "):
            self.assertIn(section, out)
        self.assertIn("- check: `pcw.py check draft.txt --platform plat:linkedin_post` enforces ['post text']", out)
        self.assertIn("## Lint (python pcw.py check draft.txt --genre genre:press_release)", out)

    def test_brief_no_match(self):
        """A free-text request that matches nothing prints the hint and exits 1 (final pass 2026-10-20: a pipeline must
        be able to tell that no brief was written); an explicit id that does not resolve (unknown, mistyped or of
        another kind) is an error naming the flag, exit 1, and no brief."""
        code, out = cli("pcw.py", "brief", "zzqx wvvq")
        self.assertEqual(code, 1)
        self.assertIn("No genre card matches", out)
        code, out, err = cli3("pcw.py", "brief", "--genre", "genre:does_not_exist")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("--genre genre:does_not_exist: no genre card", err)
        code, out, err = cli3("pcw.py", "brief", "--genre", "genre:cold_email", "--platform", "genre:linkedin_post",
                              "--lang", "lang:hinglish", "--tone", "tone:playfull")
        self.assertEqual(code, 1)
        self.assertIn("--platform genre:linkedin_post: no platform card 'genre:linkedin_post': genre:linkedin_post is "
                      "a genre card; did you mean plat:linkedin_post?", err)
        self.assertIn("--lang lang:hinglish: no language card", err)
        self.assertIn("--tone tone:playfull: no tone card", err)
        self.assertEqual(cli3("pcw.py", "brief", "--genre", "tone:authoritative")[0], 1)  # a tone is not a genre

    def test_brief_flags_are_parsed(self):
        """--opt=value works, words around the flags join into the request; a typo'd or empty flag exits 2."""
        code, out = cli("pcw.py", "brief", "cold", "--genre=genre:press_release", "email")
        self.assertEqual(code, 0)
        self.assertIn("(genre:press_release)", out.splitlines()[0])
        for bad in (["--genr", "genre:cold_email"], ["--genre"], ["--genre", ""]):
            self.assertEqual(cli3("pcw.py", "brief", *bad)[0], 2, bad)

    def test_find_and_card_arguments(self):
        self.assertEqual(cli3("pcw.py", "find")[0], 2)
        self.assertEqual(cli3("pcw.py", "card")[0], 2)
        code, out, err = cli3("pcw.py", "card", "genre:nope")
        self.assertEqual((code, json.loads(out)), (1, None))
        self.assertIn("no card 'genre:nope'", err)
        for kind in ("framework", "fw:"):  # a kind name or an id prefix with its colon
            out = cli("pcw.py", "find", "aida", kind)[1]
            self.assertTrue(out.startswith("[fw:aida") and all(l.startswith("[fw:") for l in out.splitlines()), out)
        self.assertTrue(cli("pcw.py", "find", "landing", "page", "saas")[1].startswith("[genre:"))  # no kind 'page'
        self.assertEqual(cli3("pcw.py", "find", "aida", "fx:")[0], 2)  # an unknown id prefix
        self.assertEqual(cli("pcw.py", "ids", "fw:", "aida")[1].split()[0], "fw:aida")

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
        # final pass 2026-10-20: a warn, not an info line, so "OK: no fails" never stands alone as a pass
        self.assertIn("[warn] plat:google_ads_rsa has 3 fields and nothing was measured: pass --field", out)
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
        self.assertEqual(cli("pcw.py", "check", "-", "--platform", "plat:linkedin_post", stdin="Piped.")[0], 0)

    def test_missing_or_unreadable_draft_is_a_usage_error(self):
        """stress 2026-10-20: a draft path that is not a readable text file exits 2 at once. It never falls back to
        stdin (an empty pipe used to lint '' and print OK; an open pipe hung) and never shares exit 1 with lint."""
        for args in ([self.dir / "no_such_draft.txt"], [self.dir], [""]):
            code, out, err = cli3("pcw.py", "check", *args, "--platform", "plat:linkedin_post", stdin="")
            self.assertEqual(code, 2, (args, out, err))
            self.assertNotIn("OK: no fails", out)
        p = subprocess.Popen([sys.executable, str(HOME / "pcw.py"), "check", str(self.dir / "nope.txt")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:  # stdin stays open, as in an agent's shell
            code = p.wait(timeout=60)
        finally:
            if p.poll() is None:
                p.kill()
            for f in (p.stdin, p.stdout, p.stderr):
                f.close()
        self.assertEqual(code, 2)
        bad = self.dir / "cp1252.txt"
        bad.write_bytes("Launch day \x96 price \x80 5".encode("latin-1"))  # Notepad 'ANSI'
        code, out, err = cli3("pcw.py", "check", bad)
        self.assertEqual(code, 2)
        self.assertIn("not UTF-8 text", err)
        binary = self.dir / "x.bin"
        binary.write_bytes(bytes(range(256)))
        self.assertEqual(cli3("pcw.py", "check", binary)[0], 2)

    def test_empty_draft_fails(self):
        code, out = cli("pcw.py", "check", self.draft(" \n"), "--platform", "plat:linkedin_post")
        self.assertEqual(code, 1)
        self.assertIn("[fail] draft is empty", out)

    def test_utf16_bom_and_crlf_drafts_count_like_utf8(self):
        text = "Short post.\nReply if useful."
        ref = cli("pcw.py", "check", self.draft(text), "--platform", "plat:linkedin_post")
        u16 = self.dir / "ps51.txt"  # Windows PowerShell 5.1 `>` writes UTF-16LE with a BOM
        u16.write_bytes(b"\xff\xfe" + text.replace("\n", "\r\n").encode("utf-16-le"))
        self.assertEqual(cli("pcw.py", "check", u16, "--platform", "plat:linkedin_post"), ref)
        crlf = self.dir / "crlf.txt"
        crlf.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(cli("pcw.py", "check", crlf, "--platform", "plat:linkedin_post"), ref)

    def test_piped_text_is_utf8_whatever_the_console_code_page(self):
        """Piped bytes are decoded as UTF-8 (BOM stripped) even when Python's stdin encoding is cp1252."""
        hindi = "नमस्ते दोस्तों, आज मुफ़्त डिलीवरी है।"
        args = ("--platform", "plat:x_bio", "--field", "bio")
        ref = cli("pcw.py", "check", self.draft(hindi), *args)
        legacy = {"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
        self.assertEqual(cli3("pcw.py", "check", *args, stdin=hindi.encode("utf-8"), env=legacy)[:2], ref)
        code, out, _ = cli3("pcw.py", "check", *args, stdin=b"\xef\xbb\xbf" + b"y" * 160, env=legacy)
        self.assertEqual(code, 0, out)
        # repair 2026-10-20, as README says: piped legacy code-page bytes that are not valid UTF-8 are rejected
        code, out, err = cli3("pcw.py", "check", *args, stdin="Launch day \x96 price \x80 5".encode("latin-1"))
        self.assertEqual(code, 2, out)
        self.assertIn("not UTF-8 text", err)

    def test_flags_are_parsed(self):
        """--opt=value works; a typo'd flag, a flag with no value, an empty value, a second draft and --field without
        --platform exit 2 instead of silently checking nothing; a repeated flag keeps the last value."""
        long = self.draft("x" * 3200)
        self.assertEqual(cli("pcw.py", "check", long, "--platform", "plat:linkedin_post")[0], 1)
        self.assertEqual(cli("pcw.py", "check", long, "--platform=plat:linkedin_post")[0], 1)
        self.assertEqual(cli("pcw.py", "check", long, "--platform", "plat:x_bio", "--platform", "plat:linkedin_post")[0], 1)
        other = self.dir / "other.txt"
        other.write_text("ok", encoding="utf-8")
        for bad in (["--platfrom", "plat:linkedin_post"], ["--platform"], ["--platform", ""], ["--genre", ""],
                    [other, "--platform", "plat:linkedin_post"], ["--field", "post text"]):
            code, out, err = cli3("pcw.py", "check", long, *bad)
            self.assertEqual(code, 2, (bad, out, err))

    def test_wrong_kind_ids_fail(self):
        """A genre id (or a card name) given as --platform, or a platform id as --genre, is a fail, not a pass."""
        long = self.draft("x" * 3200)
        code, out = cli("pcw.py", "check", long, "--platform", "genre:linkedin_post")
        self.assertEqual(code, 1)
        self.assertIn("[fail] no platform card 'genre:linkedin_post': genre:linkedin_post is a genre card; did you "
                      "mean plat:linkedin_post?", out)
        self.assertEqual(cli("pcw.py", "check", long, "--platform", "LinkedIn post")[0], 1)
        code, out = cli("pcw.py", "check", long, "--genre", "plat:x_bio")
        self.assertIn("[fail] no genre card 'plat:x_bio': plat:x_bio is a platform card", out)

    def test_exact_field_name_selects_that_limit(self):
        """--field description is the App Store's 4,000-character description, not the 45-character in-app purchase
        description it is a substring of; a substring still works when no field is named exactly."""
        desc = self.draft("An offline notes app for students. " * 15)
        args = ("--platform", "plat:apple_app_store")
        self.assertEqual(cli("pcw.py", "check", desc, *args, "--field", "description")[0], 0)
        code, out = cli("pcw.py", "check", desc, *args, "--field", "purchase description")
        self.assertEqual(code, 1)
        self.assertIn("in-app purchase description", out)
        code, out = cli("pcw.py", "check", self.draft("x" * 100), "--platform", "plat:email_subject_line",
                        "--field", "subject line")
        self.assertIn("subject line (recommended): 100 chars > max 60", out)

    def test_count_and_weight_rows_do_not_hide_the_text_limit(self):
        """A URL weight (X counts a link as 23) and count rows are not separate fields: X, Instagram caption and
        comment, Telegram ads are enforced without --field; X is counted the X way."""
        code, out = cli("pcw.py", "check", self.draft("x" * 400), "--platform", "plat:x_post")
        self.assertEqual(code, 1)
        self.assertIn("[fail] plat:x_post post text: 400 X-weighted chars > max 280", out)
        hindi = ("नमस्ते दोस्तों, आज की बात सुनिए। " * 12)[:300]  # 300 code points, 192 visible characters
        self.assertEqual(cli("pcw.py", "check", self.draft(hindi), "--platform", "plat:x_post")[0], 1)
        link = self.draft("x" * 250 + " https://example.com/" + "a" * 100)  # 250 + 1 + 23
        self.assertEqual(cli("pcw.py", "check", link, "--platform", "plat:x_post")[0], 0)
        code, out = cli("pcw.py", "check", self.draft("Short post."), "--platform", "plat:x_post", "--field", "URL")
        self.assertIn("has no lintable limit matching --field 'URL'", out)
        code, out = cli("pcw.py", "check", self.draft("x" * 2850), "--platform", "plat:instagram_caption")
        self.assertIn("[fail] plat:instagram_caption caption: 2850 chars > max 2200", out)
        code, out = cli("pcw.py", "check", self.draft(" ".join(f"@user{i}" for i in range(21))),
                        "--platform", "plat:instagram_caption")
        self.assertIn("[fail] plat:instagram_caption @ mentions per caption: 21 count > max 20", out)
        code, out = cli("pcw.py", "check", self.draft("Spring launch " + "#tag " * 9), "--platform", "plat:bluesky_post",
                        "--field", "tags")
        self.assertNotIn("count > max 8", out)  # in-text hashtags are not Bluesky's 'extra tags'

    def test_sms_counts_the_encoding(self):
        """SMS: GSM-7 septets (extension characters cost 2) or, with any other character, UCS-2 UTF-16 units; one SMS
        is 160 or 70, and the per-segment sizes (153 / 67) never fail a message that fits one SMS."""
        dlt = ("--platform", "plat:sms_india_dlt", "--field", "message body")
        offer = "Flat ₹200 off on your next Kaapi Kudi order above ₹999. Use code CHAI200 at checkout. Valid till 31 Oct. T&C apply. -KAAPIK"
        code, out = cli("pcw.py", "check", self.draft(offer), *dlt)
        self.assertEqual(code, 1)
        self.assertIn("UCS-2 message, 123 UTF-16 units > max 70 for one SMS (2 segments)", out)
        seg = ("--platform", "plat:sms_encoding_segments", "--field", "SMS")
        self.assertEqual(cli("pcw.py", "check", self.draft("x" * 158), *seg)[0], 0)
        self.assertEqual(cli("pcw.py", "check", self.draft("x" * 68 + "’"), *seg)[0], 0)  # 69 UCS-2 units
        code, out = cli("pcw.py", "check", self.draft("x" * 156 + "€[]"), *seg)
        self.assertIn("GSM-7 message, 162 septets > max 160", out)
        code, out = cli("pcw.py", "check", self.draft("x" * 149 + "’"), *seg)
        self.assertIn("UCS-2 message, 150 UTF-16 units > max 70", out)


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
        self.assertTrue(os.path.samefile(out.strip(), md), (out, md))  # Windows may print the 8.3 short path
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
