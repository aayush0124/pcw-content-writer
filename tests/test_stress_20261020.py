"""Regression tests for the stress review of 2026-10-20: draft counting and lint patterns, validation gaps, data homes
and the pipeline's tolerance of hand-edited files. Each test names the defect it pins."""
import ast, json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

from helpers import HOME, cli, cli3, tmp_home
import pcw


def warns(text, **kw):
    return pcw.check_text(text, **kw)[1]


def tells(text):
    return [w for w in warns(text) if w.startswith("AI tell")]


class Counting(unittest.TestCase):
    def test_emoji_are_counted_as_seen(self):
        """One per emoji as the reader sees it (flag, ZWJ family, skin tone, keycap = 1); emoji-presentation symbols
        outside the old three blocks count; text symbols without U+FE0F do not."""
        cases = {"Made in India \U0001F1EE\U0001F1F3": 1, "Family pack \U0001F468\u200d\U0001F469\u200d\U0001F467": 1,
                 "Thanks \U0001F44D\U0001F3FD": 1, "Rate us \u2b50\u2b50\u2b50\u2b50\u2b50 \u23f0": 6,
                 "Step 1\ufe0f\u20e3": 1, "Up \u2b06\ufe0f": 1, "\u2713 GST invoice": 0, "Rated 4.6\u2605": 0,
                 "\u27a4 next": 0, "\u00a9 2026": 0, "Go \U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F": 1}
        for text, n in cases.items():
            self.assertEqual(pcw.stats_text(text)["emoji"], n, ascii(text))

    def test_a_number_is_not_a_hashtag(self):
        for text, n in (("India's #1 pressure cooker", 0), ("order #4821", 0), ("Press #2 for Hindi", 0),
                        ("#2026Goals", 1), ("#Diwali #sale", 2)):
            self.assertEqual(pcw.stats_text(text)["hashtags"], n, text)
        fails = pcw.check_text("Your order #4821 has shipped \U0001F1EE\U0001F1F3. Track it in the app.",
                               genre="genre:transactional_email")[0]
        self.assertFalse([f for f in fails if f.startswith(("max_emoji", "max_hashtags"))], fails)
        fails = pcw.check_text("Hi Priya, \u2b50\u2b50\u2b50\u2b50\u2b50 \u23f0 Worth a call next week?",
                               genre="genre:cold_email")[0]
        self.assertIn("max_emoji 0: draft has 6", fails)

    def test_number_ranges_are_not_dashes(self):
        self.assertEqual(pcw.stats_text("Revenue grew 18% in FY2025\u201326, pages 10\u201312.")["dashes"], 0)
        self.assertEqual(pcw.stats_text("We ship \u2014 today.")["dashes"], 1)

    def test_abbreviations_do_not_end_sentences(self):
        long = ("Hi Priya, our team set up returns dashboards for kurta brands in Jaipur and Pune, and for Rs. 499 a "
                "month your team gets the same size-chart fix that cut returns by 12% for two of them last quarter. "
                "Worth a call? Ravi")
        self.assertEqual(pcw.stats_text(long)["max_sentence_words"], 39)
        self.assertIn("max_sentence_words 30: draft has 39", pcw.check_text(long, genre="genre:cold_email")[0])
        for s in ("Dr. Mehta will join the call.", "Use e.g. the size chart.", "Plot No. 14, Sector 5."):
            self.assertEqual(pcw.stats_text(s)["sentences"], 1, s)
        self.assertEqual(pcw.stats_text("Answer: No. Next step. मेरा नाम। 1934 की बात।")["sentences"], 4)
        # repair 2: a full stop before a lowercase word still ends a sentence (lowercase styling, Roman Hinglish), and
        # "ms." is not the title "Ms."
        lower = ("new drop is live. soft cotton, easy fit, made in jaipur. sizes run true. grab yours before friday. "
                 "link in bio.")
        for s, n in ((lower, 5), ("aaj sale hai. jaldi aao. stock limited hai. 50% off sirf aaj.", 4),
                     ("Page load fell to 300 ms. Users stayed longer.", 2),
                     ("We stock kurtas, sarees, etc. The new line drops Friday.", 2)):
            self.assertEqual(pcw.stats_text(s)["sentences"], n, s)
        self.assertEqual(pcw.stats_text(lower)["max_sentence_words"], 7)
        self.assertEqual(pcw.check_text(lower, genre="genre:push_notification")[0], [])

    def test_visible_window_and_fail_message_use_visible_characters(self):
        hindi = "स्वास्थ्य मंत्रालय ने कहा कि क्षेत्रीय अस्पतालों में ऑक्सीजन पर्याप्त है। " * 5
        p, f = "plat:linkedin_ads_sponsored_content", "introductory text (single image)"
        fails, _, info = pcw.check_text(hindi, platform=p, field=f)
        window = next(i for i in info if i.startswith("visible before truncation"))
        shown = ast.literal_eval(window.split(": ", 1)[1])  # the repr the tool printed
        self.assertEqual(len(pcw._clusters(shown)), 150)
        self.assertEqual(pcw._clusters(hindi)[:150], pcw._clusters(shown))
        fails = pcw.check_text(hindi * 2, platform=p, field="headline")[0]
        self.assertTrue(any(f"{len(pcw._clusters((hindi * 2).strip()))} chars (" in x for x in fails), fails)

    def test_x_weighted_and_sms_units(self):
        self.assertEqual(pcw.x_weighted("\u4e2d" * 140), 280)
        self.assertEqual(pcw.x_weighted("a https://example.com/x."), 1 + 1 + 23 + 1)  # the full stop is not the URL
        self.assertEqual(pcw.sms_units("x" * 160)[:3], ("GSM-7", 160, 1))
        self.assertEqual(pcw.sms_units("x" * 161)[:3], ("GSM-7", 161, 2))
        self.assertEqual(pcw.sms_units("{}")[:2], ("GSM-7", 4))
        enc, n, segs, odd = pcw.sms_units("Price \u20b9200")
        self.assertEqual((enc, n, segs, odd), ("UCS-2", 10, 1, "\u20b9"))


class Tells(unittest.TestCase):
    def test_curly_apostrophes_do_not_hide_a_tell(self):
        for s in ("It\u2019s not just a tool, it\u2019s a partner.", "In today\u2019s fast-paced world, every brand "
                  "needs content.", "Let\u2019s be honest: nobody reads the T&Cs.", "Here\u2019s the thing about pricing."):
            self.assertTrue(tells(s), s)
        fails = pcw.check_text("In today\u2019s fast-paced world, founders post daily.", genre="genre:linkedin_post")[0]
        self.assertTrue(any(f.startswith("banned") for f in fails), fails)

    def test_not_x_but_y(self):
        must = ["It's not a bug. It's a feature.", "This isn't just a phone, it's a camera.",
                "This isn't about price. It's about trust.", "It's not a cost, it's an investment."]
        never = ["That's not possible this week, but we can refund the order today.",
                 "It's not ready yet, but the beta opens on Friday.", "This is not a sale item, but the code still works.",
                 "This is a great product. It is made in Jaipur.", "It is late. It is dark."]
        for s in must:
            self.assertTrue(any("not X but Y" in w for w in tells(s)), s)
        for s in never:
            self.assertFalse(any("not X but Y" in w for w in tells(s)), s)

    def test_certainly(self):
        self.assertTrue(any("chatbot residue" in w for w in tells("Certainly! Here is the revised draft.")))


class Validation(unittest.TestCase):
    hv = {"genre:a": {"name": "A"}, "fw:b": {"name": "B"}, "tech:c": {"name": "C"}, "plat:p": {"name": "P"}}

    def card(self, **kw):
        base = dict(zip(pcw.COMMON, ("genre:a", "genre", "A", "current", "s", ["u"], ["v"], "high")))
        return dict(base, buyers=["x"], value="high", goal="g", structure=[{"part": "p", "does": "d"}],
                    length={"min": 1}, frameworks=["fw:b"], techniques=["tech:c"], checklist=["c"], pitfalls=["p"],
                    exemplar_brief="e", **dict({"lint": {"max_words": 99}}, **kw))

    def test_reference_fields_hold_lists_of_the_right_kind(self):
        self.assertEqual(pcw.check_card(self.card(), self.hv), [])
        for bad in (dict(compliance="comp:asci_code"), dict(frameworks=["tech:c"]), dict(platforms=["genre:a"])):
            self.assertTrue(pcw.check_card(dict(self.card(), **bad), self.hv), bad)

    def test_platform_limits_compare_unit_and_visible(self):
        it = {"name": "P", "limits": [{"field": "post", "max": 3000, "unit": "chars", "visible": 210}]}
        c = dict(zip(pcw.COMMON, ("plat:p", "platform", "P", "current", "s", ["u"], ["v"], "high")),
                 sources=[{"url": "https://x.example"}], formatting="f", writing_notes=["w"],
                 limits=[{"field": "post", "max": 3000, "unit": "chars", "visible": 210}])
        self.assertEqual(pcw.check_card(c, {"plat:p": it}), [])
        for k, v in (("unit", "words"), ("visible", 140), ("lint", False)):
            c2 = dict(c, limits=[dict(c["limits"][0], **{k: v})])
            self.assertTrue(any("harvested limits unchanged" in x for x in pcw.check_card(c2, {"plat:p": it})), k)
        c3 = dict(c, limits=[dict(c["limits"][0], count="tweet")])
        self.assertTrue(any("count 'tweet'" in x for x in pcw.check_card(c3, {"plat:p": it})))

    def test_framework_mini_example_limit_is_120_words(self):
        fw = dict(zip(pcw.COMMON, ("fw:b", "framework", "B", "current", "s", ["u"], ["v"], "high")),
                  steps=[{"step": "s", "does": "d"}], best_for=["x"], not_for=["y"], mini_example="w " * 121)
        self.assertIn("fw:b: mini_example over 120 words", pcw.check_card(fw, self.hv))
        self.assertEqual(pcw.check_card(dict(fw, mini_example="w " * 120), self.hv), [])

    def test_no_card_lint_regex_eats_blank_lines(self):
        """(?m)^\\s* runs in cubic time on a paste with hundreds of blank lines; validate rejects it statically."""
        slow = {"label": "x", "regex": r"(?im)^\s*#{0,4}\s*(tip|item) ?\d+\s*$"}
        self.assertTrue(any("cubic" in x for x in pcw.check_card(self.card(lint={"ban": [slow]}), self.hv)))
        for c in pcw.cards():
            for r in ((c.get("lint") or {}).get("require") or []) + ((c.get("lint") or {}).get("ban") or []):
                slow = re.compile(r["regex"]).flags & re.M and pcw.SLOW_RX.search(r["regex"])
                self.assertFalse(slow, (c["id"], r["regex"]))

    def test_read_draft(self):
        d = Path(tempfile.mkdtemp(prefix="pcw_draft_"))
        try:
            (d / "a.txt").write_bytes(b"\xef\xbb\xbfHi\r\nthere")
            self.assertEqual(pcw.read_draft(str(d / "a.txt")), "Hi" + chr(10) + "there")
            (d / "u16.txt").write_bytes("Hi".encode("utf-16"))
            self.assertEqual(pcw.read_draft(str(d / "u16.txt")), "Hi")
            for bad in (str(d / "nope.txt"), str(d), ""):
                self.assertRaises(pcw.DraftError, pcw.read_draft, bad)
            (d / "cp.txt").write_bytes(b"caf\xe9")
            self.assertRaises(pcw.DraftError, pcw.read_draft, str(d / "cp.txt"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class DataHome(unittest.TestCase):
    def test_a_wrong_home_is_reported_not_treated_as_empty(self):
        missing = Path(tempfile.gettempdir()) / "pcw_no_such_home_20261020"
        env = {"PCW_HOME": str(missing)}
        code, out, err = cli3("pcw.py", "validate", env=env)
        self.assertEqual(code, 1)
        self.assertIn("no harvest/*.json under", out)
        for args in (("find", "aida"), ("stats",), ("brief", "cold email")):
            self.assertEqual(cli3("pcw.py", *args, env=env)[0], 2, args)
        quoted = {"PCW_HOME": f'"{HOME}" '}  # cmd's `set PCW_HOME="<folder>"` keeps the quotes
        self.assertEqual(json.loads(cli3("pcw.py", "card", "genre:cold_email", env=quoted)[1])["id"], "genre:cold_email")

    def test_tests_use_their_own_checkout(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import helpers, pcw; "
                "print(helpers.HOME == pcw.HERE == __import__('pathlib').Path(sys.argv[2]).resolve())")
        env = dict(os.environ, PCW_HOME=tempfile.gettempdir())
        r = subprocess.run([sys.executable, "-c", code, str(HOME / "tests"), str(HOME)], capture_output=True,
                           text=True, env=env, cwd=tempfile.gettempdir())
        self.assertEqual(r.stdout.strip(), "True", r.stderr)


class HandEditedFiles(unittest.TestCase):
    """Files agents edit by hand (gaps.jsonl, card files, batch files) are reported when broken, never a crash or a
    silent loss. Runs on a throwaway copy."""

    @classmethod
    def setUpClass(cls):
        cls.home = tmp_home()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def status(self):
        code, out = cli("pipeline.py", "status", home=self.home)
        return code, {l.split()[0]: l for l in out.splitlines()[1:] if l and not l.startswith(" ")}

    def test_bad_gap_lines(self):
        g = self.home / "work" / "gaps.jsonl"
        before = g.read_bytes()
        try:
            with g.open("ab") as f:
                f.write(b"{'date': '2026-10-20', 'kind': 'genre', 'gap': 'x'}\n")
                f.write('{"date":"2026-10-20","kind":"genre","gap":"y"}\r\n'.encode("utf-16-le"))
            code, rows = self.status()
            self.assertIn(code, (1, 10))
            self.assertIn("2 unreadable lines in work/gaps.jsonl", rows["critic"])
            code, out = cli("pcw.py", "validate", home=self.home)
            self.assertEqual(code, 1)
            self.assertIn("work/gaps.jsonl line", out)
        finally:
            g.write_bytes(before)

    def test_gaps_logged_on_the_critics_day_count(self):
        crit, g = self.home / "cards" / "zz_critic.json", self.home / "work" / "gaps.jsonl"
        c0, g0 = crit.read_bytes(), g.read_bytes()
        try:
            d = json.loads(c0)
            rows, _ = pcw.gaps()
            d["gaps_seen"] = len(rows)
            crit.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
            with g.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"date": d["critic"]["date"], "kind": "genre", "gap": "same-day gap"}) + "\n")
            self.assertIn("1 gaps logged since", self.status()[1]["critic"])
        finally:
            crit.write_bytes(c0)
            g.write_bytes(g0)

    def test_bom_and_list_shaped_card_files(self):
        f = self.home / "cards" / "genre_05.json"
        raw = f.read_bytes()
        try:
            f.write_bytes(b"\xef\xbb\xbf" + raw)
            code, out = cli("pcw.py", "card", "genre:facebook_post", home=self.home)
            self.assertEqual(json.loads(out)["id"], "genre:facebook_post")
            f.write_text("[]", encoding="utf-8")
            code, out, err = cli3("pcw.py", "validate", "cards/genre_05.json", home=self.home)
            self.assertEqual(code, 1)
            self.assertIn("top level must be a JSON object", out)
            code, out, err = cli3("pcw.py", "stats", home=self.home)
            self.assertEqual(code, 0)
            self.assertIn("pcw: skipped", err)
        finally:
            f.write_bytes(raw)

    def test_unreadable_or_duplicated_batch_files(self):
        b = self.home / "work" / "batches" / "tone_01.json"
        raw = b.read_bytes()
        try:
            b.write_bytes(raw[:300])
            names = sorted(p.name for p in b.parent.glob("*.json"))
            code, out, err = cli3("pcw.py", "batches", home=self.home)
            self.assertEqual(code, 1)
            self.assertIn("before re-batching", err)
            self.assertEqual(sorted(p.name for p in b.parent.glob("*.json")), names)  # nothing written
            b.write_bytes(raw)
            dup = b.parent / "tone_99.json"
            dup.write_bytes(raw)
            code, out = cli("pcw.py", "validate", home=self.home)
            self.assertEqual(code, 1)
            self.assertIn("batch files", out)
            dup.unlink()
        finally:
            b.write_bytes(raw)

    def test_a_card_without_its_sample(self):
        f = self.home / "gallery" / "genre_01.json"
        raw = f.read_bytes()
        try:
            d = json.loads(raw)
            gone = d["samples"][1]["id"]
            d["samples"][1] = dict(d["samples"][0])
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            code, out = cli("pcw.py", "validate", home=self.home)
            self.assertIn(f"genre_01.json: {d['samples'][0]['id']} has 2 samples", out)
            self.assertNotIn(gone, out)  # a missing sample is the samples row's attention, not a validate issue
            self.assertEqual(self.status()[1]["samples"].split()[2], "attention")
        finally:
            f.write_bytes(raw)

    def test_a_gallery_file_written_as_you_go(self):
        """repair 2: work/BRIEF_VERIFY.md says to write the gallery file as you go, so a partial file validates."""
        f = self.home / "gallery" / "genre_01.json"
        raw = f.read_bytes()
        try:
            d = json.loads(raw)
            d["samples"] = d["samples"][:5]
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            code, out = cli("pcw.py", "validate", home=self.home)
            self.assertEqual(code, 0, out)
            code, rows = self.status()
            self.assertEqual(code, 10)
            self.assertEqual(rows["validate"].split()[2], "ok")
            self.assertEqual(rows["samples"].split()[2], "attention")
        finally:
            f.write_bytes(raw)


class FinalPassCheck(unittest.TestCase):
    """Final pass 2026-10-20: check_text (platform fields, counting, URLs, tells, sentences)."""

    def test_a_multi_field_platform_never_reads_as_a_clean_pass(self):
        """audit 5: no --field on a multi-field platform is a warn ('nothing was measured'), not an info line."""
        fails, w, info = pcw.check_text("x" * 3200, platform="plat:mastodon_post")
        self.assertEqual(fails, [])
        self.assertTrue(any("nothing was measured" in x for x in w), w)
        no_rows = next(c for c in pcw.cards() if c["kind"] == "platform" and not pcw.lint_rows(c))
        self.assertTrue(any("by hand" in x for x in pcw.check_text("Hello.", platform=no_rows["id"])[2]))

    def test_a_field_that_fits_alternative_surfaces_asks_for_one(self):
        """audit 21: a shared base name or substring that fits several rows of one unit is a fail naming them, not a
        fail against a surface the draft is not written for; the full name tests that row."""
        for pid, field, ok_field, text in (
                ("plat:google_play_listing", "description", "full description", "x" * 380),
                ("plat:linkedin_ads_sponsored_content", "introductory text", "introductory text (single image)", "x" * 500),
                ("plat:meta_ads", "headline", "headline, Instagram", "x" * 34),
                ("plat:telegram_bio", "bio", "bio (Premium)", "x" * 100)):
            fails = pcw.check_text(text, platform=pid, field=field)[0]
            self.assertTrue(len(fails) == 1 and "fits several alternative fields; name one" in fails[0], (pid, fails))
            self.assertEqual(pcw.check_text(text, platform=pid, field=ok_field)[0], [], (pid, ok_field))
        self.assertEqual(pcw.check_text("x" * 379, platform="plat:apple_app_store", field="description")[0], [])
        self.assertEqual(pcw.check_text("x" * 158, platform="plat:sms_encoding_segments", field="GSM-7")[0], [])

    def test_count_rows_of_the_selected_text_come_along(self):
        """round 2, 11: --field 'subject line' also enforces the emoji and punctuation caps of the subject; Threads'
        'post text' its links per post; Instagram's caption its @ mentions."""
        fails = pcw.check_text("\U0001F389\U0001F525 Big Diwali sale!!! Ready?!", platform="plat:email_subject_line",
                               field="subject line")[0]
        self.assertTrue(any("emojis per subject" in f for f in fails) and any("punctuation" in f for f in fails), fails)
        links = " ".join(f"https://example.com/{i}" for i in range(6))
        fails = pcw.check_text(links, platform="plat:threads_post", field="post text")[0]
        self.assertTrue(any("links per post" in f for f in fails), fails)
        fails = pcw.check_text(" ".join(f"@user{i}" for i in range(21)), platform="plat:instagram_caption",
                               field="caption")[0]
        self.assertTrue(any("@ mentions per caption" in f for f in fails), fails)

    def test_spaced_number_ranges_are_not_dashes(self):
        """audit 28 (range half): 'Pages 10 – 12' is a range; a single em dash still warns (house rule, round 2 12)."""
        self.assertEqual(pcw.stats_text("Pages 10 – 12 and Rs 10–12 per unit.")["dashes"], 0)
        self.assertEqual(pcw.stats_text("We ship – today.")["dashes"], 1)
        steps = " ".join(pcw.card("edit:ai_tell_removal")["steps"])
        self.assertNotIn("a single em dash,", steps)  # the card no longer calls one dash a false positive

    def test_a_gsm7_field_fails_a_message_that_needs_ucs2(self):
        """round 2, 1: --field 'single SMS, GSM-7' used to skip a UCS-2 message silently."""
        args = dict(platform="plat:sms_encoding_segments", field="single SMS, GSM-7")
        fails = pcw.check_text("It’s Diwali at Kaapi Kudi: 20% off every filter coffee till Sunday. Show this SMS. -KAAPIK", **args)[0]
        self.assertTrue(any("does not fit one GSM-7 SMS: UCS-2 because of '’'" in f for f in fails), fails)
        self.assertEqual(pcw.check_text("It's Diwali: 20% off till Sunday. -KAAPIK", **args)[0], [])

    def test_x_links_without_a_scheme_and_in_capitals(self):
        """round 2, 2: X links zomato.com, amazon.in/deals, www. domains and HTTPS:// as 23 each; e.g., U.S. and a bare
        country-code domain (amazon.in) are not links."""
        self.assertEqual(pcw.x_weighted("a" * 265 + " zomato.com"), 265 + 1 + 23)
        self.assertEqual(pcw.x_weighted("a" * 260 + " amazon.in/deals"), 260 + 1 + 23)
        self.assertEqual(pcw.x_weighted("www.example.com/" + "p" * 60 + " " + "a" * 220), 23 + 1 + 220)
        self.assertEqual(pcw.x_weighted("HTTPS://EXAMPLE.COM/" + "P" * 40), 23)
        for s in ("e.g.", "U.S.", "amazon.in", "Rs.499", "a.m."):
            self.assertEqual(pcw.x_weighted(s), len(s), s)
        self.assertTrue(pcw.check_text("a" * 265 + " zomato.com", platform="plat:x_post")[0])

    def test_x_counts_a_skin_tone_sequence_without_fe0f_as_one_emoji(self):
        """round 2, 10: U+270C U+1F3FD weighs 2, not 4."""
        self.assertEqual(pcw.x_weighted("✌\U0001F3FD"), 2)
        self.assertEqual(pcw.x_weighted("\U0001F590\U0001F3FD"), 2)
        self.assertEqual(pcw.check_text("✌\U0001F3FD" * 140, platform="plat:x_post")[0], [])
        self.assertEqual(pcw.stats_text("✌\U0001F3FD")["emoji"], 1)

    def test_abbreviations_and_the_ellipsis_character(self):
        """round 2, 3: company words, a.m./p.m., initials, vs. and e.g. do not end a sentence; '…' does."""
        for s in ("Acme Pvt. Ltd. has opened a new plant in Pune.",
                  "The webinar starts at 11 a.m. on Friday and ends at 1 p.m. sharp.",
                  "Watch India vs. Australia live on Sunday.", "Big cities, e.g. Mumbai, sell out first.",
                  "Visit us at 14 M.G. Road, Bengaluru.", "Ask Sharma & Co. for the quote.", "The U.S. market is slow."):
            self.assertEqual(pcw.stats_text(s)["sentences"], 1, s)
        push = "Flash sale is live… Grab 40% off on all kurtas till midnight and get free shipping above Rs 499"
        self.assertEqual(pcw.stats_text(push)["sentences"], 2)
        self.assertFalse([f for f in pcw.check_text(push, genre="genre:push_notification")[0]
                          if f.startswith("max_sentence_words")])

    def test_telegram_bio_counts_code_points(self):
        """round 2, 4: Telegram's 'UTF-8 length' is characters (TDLib utf8_length counts code points), not bytes."""
        hindi = "जयपुर CA | GST आसान भाषा में"
        self.assertEqual(pcw.check_text(hindi, platform="plat:telegram_bio")[0], [])  # 28 code points, 60 bytes
        fails = pcw.check_text("का" * 36, platform="plat:telegram_bio")[0]  # 72 code points, 36 visible
        self.assertTrue(any("72 code points > max 70" in f for f in fails), fails)
        rows = pcw.harvest()["plat:telegram_bio"]["limits"]
        self.assertEqual({(l["unit"], l.get("count")) for l in rows}, {("chars", "code_points")})

    def test_ads_count_double_width_characters_as_two(self):
        """round 2, 5: Google Ads counts a CJK character as 2; Microsoft Advertising also an emoji."""
        self.assertTrue(pcw.check_text("中" * 20, platform="plat:google_ads_rsa", field="headline")[0])
        self.assertEqual(pcw.check_text("中" * 15, platform="plat:google_ads_rsa", field="headline")[0], [])
        self.assertTrue(pcw.check_text("中" * 13, platform="plat:google_ads_assets", field="callout")[0])
        self.assertEqual(pcw.check_text("中" * 12, platform="plat:google_ads_assets", field="callout")[0], [])
        fails = pcw.check_text("Diwali Sale Flat 50% Off " + "\U0001F389" * 3, platform="plat:microsoft_ads_rsa",
                               field="headline")[0]
        self.assertTrue(any("31 chars > max 30" in f for f in fails), fails)

    def test_url_parts_are_not_copy(self):
        """round 2, 6: '#pricing' in a link is no hashtag, '?ref=' no question, '/@handle' no mention."""
        email = ("Hi Priya, our team cut returns by 12% for two Jaipur kurta brands last quarter with one size-chart "
                 "fix. Our rates: https://studio.in/#pricing Thanks, Arjun")
        self.assertFalse([f for f in pcw.check_text(email, genre="genre:cold_email")[0] if f.startswith("max_hashtags")])
        noask = email.replace("https://studio.in/#pricing", "https://studio.in/work?ref=coldmail")
        self.assertIn("missing: has one clear ask", pcw.check_text(noask, genre="genre:cold_email")[0])
        links = " ".join(f"https://medium.com/@rangrez/post-{i}" for i in range(6))
        self.assertEqual(pcw.check_text(links, platform="plat:instagram_comment")[0], [])

    def test_final_check_regressions(self):
        """final check: a company word or a.m./p.m. before a capitalised word ends the sentence; an en dash with a
        number on one side only still counts; a link typed without a scheme is cut to its host like an http(s) one."""
        for s in ("Doors open at 10 a.m. Entry is free.", "We are Acme Pvt. Ltd. Our plant is in Pune.",
                  "He works at Acme Co. The rest left."):
            self.assertEqual(pcw.stats_text(s)["sentences"], 2, s)
        push = "Sale ends today at 11 p.m. Grab 50% off on all kurtas, sarees and lehengas before the stock runs out."
        self.assertFalse([f for f in pcw.check_text(push, genre="genre:push_notification")[0]
                          if f.startswith("max_sentence_words")])
        for s in ("Founded 2019 – and still growing.", "Call us – 9876543210."):
            self.assertEqual(pcw.stats_text(s)["dashes"], 1, s)
        email = ("Hi Priya, our team cut returns by 12% for two Jaipur kurta brands last quarter with one size-chart "
                 "fix. See our work: {} Thanks, Arjun")
        for link in ("studio.in/work?ref=coldmail", "bit.ly/st?utm=mail"):
            self.assertIn("missing: has one clear ask", pcw.check_text(email.format(link), genre="genre:cold_email")[0])
        self.assertEqual(pcw.stats_text("Our rates: www.studio.in/#pricing")["hashtags"], 0)

    def test_no_detached_combining_or_format_characters_in_code(self):
        """final check: a combining mark that starts a string ('\\u0900') or a format character (ZWNJ) is invisible in an
        editor and easy to lose; code writes them as escapes. Marks inside a written word (Hindi test strings) are fine."""
        import unicodedata
        bad = []
        for i, line in enumerate((HOME / "pcw.py").read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#")[0]
            for j, ch in enumerate(code):
                cat = unicodedata.category(ch)
                if cat == "Cf" or (cat in ("Mn", "Mc") and (j == 0 or not (code[j - 1].isalpha()
                                                                            or unicodedata.category(code[j - 1]) in ("Mn", "Mc")))):
                    bad.append((i, hex(ord(ch))))
        self.assertEqual(bad, [])

    def test_ai_tells_catch_inflections_and_spare_plain_phrasing(self):
        """round 2, 8 and 9: inflected AI words and the stock email opener warn; 'Let me know if you need ...' does
        not (the assistant's offer still does)."""
        for s in ("We delved into the data.", "underscoring the point", "We showcased the range.", "It fostered trust.",
                  "The post garnered likes.", "the intricacies of GST", "rich tapestries", "a game-changing launch",
                  "Unlocking growth for MSMEs", "In today's ever-evolving landscape, brands adapt.",
                  "The fast-paced world of fintech", "I hope this email finds you well."):
            self.assertTrue(tells(s), s)
        self.assertEqual(tells("Let me know if you need a GST copy of the invoice."), [])
        self.assertTrue(tells("Let me know if you'd like me to adjust the tone."))

    def test_the_zwnj_branch_is_written_as_an_escape(self):
        """reverify: an invisible literal U+200C in the code would turn into '' if an editor stripped it."""
        src = (HOME / "pcw.py").read_text(encoding="utf-8")
        line = next(l for l in src.splitlines() if "or not ext:" in l)
        self.assertIn("\\u200c", line.split("#")[0])
        self.assertNotIn("\u200c", line.split("#")[0])


class FinalPassData(unittest.TestCase):
    """Final pass 2026-10-20: briefs, judge accounting, the critic report."""

    def test_every_back_link_reaches_the_brief(self):
        """round 2, 13: a law whose card names a genre, and a platform card that names it, show in that genre's brief
        (a full checklist for the genre's own list, a one-line pointer for the rest)."""
        cs = pcw.cards()
        for g in (c for c in cs if c["kind"] == "genre"):
            b = pcw.brief(genre=g["id"])
            for c in cs:
                if c["kind"] == "compliance" and g["id"] in (c.get("applies_to") or []):
                    self.assertTrue(c["id"] in b or f"## Legal: {c['name']} (" in b, (g["id"], c["id"]))
                if c["kind"] == "platform" and g["id"] in (c.get("related") or []):
                    self.assertIn(c["id"], b, g["id"])
        self.assertIn("comp:rera_advertisement_rules", pcw.brief(genre="genre:real_estate_listing"))
        self.assertIn("comp:trai_tcccpr_2018", pcw.brief(genre="genre:sms_marketing"))
        self.assertIn("plat:linkedin_profile", pcw.brief(genre="genre:linkedin_profile"))

    def test_validate_checks_the_genre_platform_twin_rule(self):
        """final check: CONTRACT says genre:x and plat:x name each other; genre:linkedin_profile did not, unnoticed."""
        home = tmp_home()
        self.addCleanup(shutil.rmtree, home, True)
        f = home / "cards" / "genre_07.json"
        f.write_text(f.read_text(encoding="utf-8").replace('"plat:linkedin_profile"\n   ],', '\n   ],', 1),
                     encoding="utf-8")
        code, out = cli("pcw.py", "validate", home=home)
        self.assertNotEqual(code, 0, out)
        self.assertIn("genre:linkedin_profile / plat:linkedin_profile: twin cards must name each other", out)
        self.assertEqual(cli("pcw.py", "validate")[0], 0)

    def test_judge_scores_equal_their_rubric(self):
        """round 2, 16: CONTRACT's score is the total of the five 0-2 marks a judge note lists."""
        rx = re.compile(r"\bP(\d)\s+S(\d)\s+Sp(\d)\s+V(\d)\s+C(\d)\b(?!-)")
        bad = [(c["id"], c["verified"]["score"]) for c in pcw.cards()
               if (m := rx.search((c.get("verified") or {}).get("note") or ""))
               and sum(map(int, m.groups())) != c["verified"]["score"]]
        self.assertEqual(bad, [])

    def test_the_critic_report_matches_the_code(self):
        """round 2, 15: the critic's tool limits no longer say X weighting is missing; the telegram_ads doubt is
        closed after the 2026-10-20 re-read."""
        crit = json.loads((HOME / "cards" / "zz_critic.json").read_text(encoding="utf-8"))
        self.assertNotIn("does not implement X's weighted counting", " ".join(crit["tool_limits"]))
        self.assertFalse([w for w in crit["weak_cards"] if w.startswith("plat:telegram_ads")])


if __name__ == "__main__":
    unittest.main()
