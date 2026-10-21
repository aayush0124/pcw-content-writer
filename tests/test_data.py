"""Data integrity, golden queries, brief shape, docs reproducibility and the in-memory selftest (no subprocess)."""
import json, re, unittest
from collections import Counter

from helpers import HOME
import pcw

TESTED_KINDS = ("genre", "hook", "framework")  # the kinds the verify wave demo-tests


def _urls(it):
    return ({s.get("url") for s in it.get("sources") or []} | {e.get("url") for e in it.get("evidence") or []}
            | {l.get("url") for l in it.get("limits") or []}) - {None}


class Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hv, cls.cs = pcw.harvest(), pcw.cards()

    def test_everything_validates(self):
        self.assertEqual(pcw.validate(), [])

    def test_ids_unique_and_legal(self):
        dup = [i for i, n in Counter(c.get("id") for c in self.cs).items() if n > 1]
        self.assertEqual(dup, [])
        bad = [c.get("id") for c in self.cs if not pcw.ID_RE.match(c.get("id") or "")]
        self.assertEqual(bad, [])

    def test_kinds_and_enums_legal(self):
        for c in self.cs:
            with self.subTest(card=c["id"]):
                self.assertIn(c["kind"], pcw.KINDS)
                self.assertEqual(c["kind"], self.hv[c["id"]]["kind"])
                self.assertEqual(c["id"].split(":")[0], pcw.KINDS[c["kind"]])
                self.assertIn(c["status"], pcw.STATUS)
                self.assertIn(c["confidence"], pcw.CONF)
                if c.get("verified"):
                    self.assertIn(c["verified"]["verdict"], pcw.VERDICT)
        for f in sorted((HOME / "harvest").glob("*.json")):
            self.assertIn(json.loads(f.read_text(encoding="utf-8"))["kind"], pcw.KINDS, f.name)

    def test_every_harvest_item_has_one_card(self):
        self.assertEqual(set(self.hv) - {c["id"] for c in self.cs}, set())
        self.assertEqual({c["id"] for c in self.cs} - set(self.hv), set())

    def test_card_sources_resolve_to_the_harvest(self):
        """A sourced card cites at least one URL its harvest item cites; sourced kinds always have sources."""
        for c in self.cs:
            with self.subTest(card=c["id"]):
                it = self.hv[c["id"]]
                if c["kind"] in pcw.NEEDS_SOURCES:
                    self.assertTrue(c.get("sources") or c.get("evidence"))
                if (c.get("sources") or c.get("evidence")) and _urls(it):
                    self.assertTrue(_urls(c) & _urls(it), "no source in common with the harvest item")

    def test_cross_references_resolve(self):
        for c in self.cs:
            for f in pcw.REF_FIELDS:
                refs = [r for r in c.get(f) or [] if isinstance(r, str) and pcw.ID_RE.match(r)]
                self.assertEqual([r for r in refs if r not in self.hv], [], f"{c['id']}.{f}")

    def test_platform_limits_match_the_harvest(self):
        for c in (c for c in self.cs if c["kind"] == "platform"):
            key = lambda ls: sorted(tuple(map(str, (l.get(k) for k in pcw.LIMIT_KEY))) for l in ls or [])  # noqa: E731
            self.assertEqual(key(c.get("limits")), key(self.hv[c["id"]].get("limits")), c["id"])

    def test_doc_example_ids_resolve(self):
        """stress 2026-10-20: every prefix:slug id the docs show is a real card (CONTRACT.md showed 10 that were not,
        and a writer copying lang:hinglish got a brief without its Language section)."""
        rx = re.compile(r"(?<![\w:])(?:%s):[a-z0-9_]+" % "|".join(pcw.KINDS.values()))
        for f in ("README.md", "CONTRACT.md", "skill/SKILL.md"):
            ids = set(rx.findall((HOME / f).read_text(encoding="utf-8")))
            self.assertEqual(sorted(i for i in ids if i not in self.hv), [], f)

    def test_platform_notes_do_not_promise_a_default_check(self):
        """stress 2026-10-20: about 30 platform cards told writers that a bare `check --platform` tests the first
        limit while check enforces nothing on a multi-field card. A note may only say so when it is true."""
        rx = re.compile(r"(?i)pcw\.py check[^.]*?(tests the first limit|first limit|by default|default test|"
                        r"tests only the first)|\bdefault test\b|the lint's default test")
        bad = []
        for c in (c for c in self.cs if c["kind"] == "platform"):
            if not pcw._several(pcw.lint_rows(c)):
                continue
            bad += [(c["id"], x[:80]) for x in c.get("writing_notes") or [] if rx.search(x)]
        self.assertEqual(bad, [])

    def test_cta_rules_ignore_words_that_merely_contain_a_cta(self):
        """stress 2026-10-20: a CTA / ask / contact `require` rule must not be satisfied by a paragraph with no call
        to action whose words only contain one (Facebook/book, recalled/call, visitors/visit, शामिल/मिल)."""
        decoy = ("Our founders met on Facebook in 2019 and kept a notebook of every customer note. The database grew "
                 "quickly across the industry. The following year, visitors from the border districts recalled the old "
                 "tagline together, and the shareholders backed a rebrand for the country. The background story is "
                 "long. हमने जयपुर के दो कुर्ता ब्रांड्स के रिटर्न 12% घटाए। इसमें साइज़ चार्ट का सुधार भी शामिल था।")
        label = re.compile(r"(?i)cta|call to action|ask|next step|action|contact|apply|register|response|backing|gift")
        hits = [(c["id"], r["label"], re.search(r["regex"], decoy).group(0)) for c in self.cs if c["kind"] == "genre"
                for r in (c.get("lint") or {}).get("require") or [] if label.search(r["label"])
                and re.search(r["regex"], decoy)]
        self.assertEqual(hits, [])

    def test_verdicts_point_at_real_samples(self):
        samples = {}
        for f in (HOME / "gallery").glob("*.json"):
            samples[f"gallery/{f.name}"] = {s.get("id") for s in json.loads(f.read_text(encoding="utf-8")).get("samples") or []}
        for c in self.cs:
            v = c.get("verified")
            if v and v.get("verdict") in ("pass", "weak", "wrong"):
                f, _, sid = v.get("sample", "").partition("#")
                self.assertIn(sid, samples.get(f, set()), f"{c['id']}: {v.get('sample')}")
                self.assertTrue(0 <= v["score"] <= 10)
        tested = [c for c in self.cs if c["kind"] in TESTED_KINDS]
        self.assertTrue(tested and all(c.get("verified") for c in tested), "every genre/hook/framework card is judged")


class Golden(unittest.TestCase):
    CASES = [("aida", "framework", "fw:aida"), ("cold email to D2C founders", "genre", "genre:cold_email"),
             ("curiosity gap", "hook", "hook:curiosity_gap"), ("influencer disclosure india", "compliance", "comp:asci_influencer"),
             # gap wave C (2026-10-13): at least one per critic gap
             ("mutual fund advertisement", "compliance", "comp:sebi_amfi_mf_advertising"),
             ("surrogate advertising", "compliance", "comp:surrogate_advertising_india"),
             ("ayurvedic drug advertisement", "compliance", "comp:ayush_drug_advertisement_rule_170"),
             ("e-commerce rules seller details country of origin", "compliance", "comp:consumer_protection_ecommerce_rules_2020"),
             ("press council norms", "compliance", "comp:pci_norms_journalistic_conduct"),
             ("web stories", "platform", "plat:google_web_stories"),
             ("indiamart product listing", "platform", "plat:indiamart_listing"),
             ("99acres property listing", "platform", "plat:99acres_listing"),
             ("price reduction prior price EU", "compliance", "comp:eu_prior_price_rule"),
             ("app store metadata apple", "compliance", "comp:apple_app_review_metadata"),
             # stress 2026-10-20: whole-token matching, one-letter names, Devanagari tokens, exact names first
             ("press release", "genre", "genre:press_release"), ("x thread", "genre", "genre:x_thread"),
             ("X post", "genre", "genre:x_post"), ("X post", "platform", "plat:x_post"), ("X ads", "platform", "plat:x_ads"),
             ("deadpan X post about Mondays", "genre", "genre:x_post"),
             ("LinkedIn post announcing my new job", "genre", "genre:linkedin_post"),
             ("X thread on AI tools for designers", "genre", "genre:x_thread"),
             ("refund SOP for the customer support team", "genre", "genre:sop_process_doc"),
             ("व्यंग्य", "tone", "tone:satirical_vyangya"), ("RTI आवेदन लिखना है", "genre", "genre:rti_application"),
             ("mere startup ke liye LinkedIn bio", "genre", "genre:linkedin_profile"),
             ("linkedin post", "plat:", "plat:linkedin_post"),
             # repair 2: a one-word bracket qualifier ("(Instagram / ...)") is no alias; shorthands and new aliases
             ("insta caption for my cafe", None, "genre:instagram_caption"), ("insta post", None, "genre:instagram_caption"),
             ("instagram", None, "genre:instagram_caption"), ("instagram post for diwali", None, "genre:festival_greeting"),
             ("web copy for my bakery", "genre", "genre:homepage_copy"), ("churn email", None, "genre:winback_email"),
             ("email to churned users", "genre", "genre:winback_email"),
             # final pass 2026-10-20: a one-word alias outweighs generic words and wins ties; platform nicknames;
             # the HEAD answers that rounds 1-2 lost (reels, shorts, insta, d2c, caption, review reply)
             ("product launch tweet", "genre", "genre:x_post"), ("magalog customer", "genre", "genre:direct_mail_package"),
             ("drabble customer", "genre", "genre:flash_fiction"), ("leader customer", "genre", "genre:editorial"),
             ("reels", "genre", "genre:short_form_video_script"), ("shorts", "genre", "genre:short_form_video_script"),
             ("insta story", "genre", "genre:instagram_story_copy"), ("insta bio", "genre", "genre:social_bio"),
             ("fb post", "genre", "genre:facebook_post"), ("yt description", "genre", "genre:youtube_title_description"),
             ("d2c", "genre", "genre:d2c_brand_store"), ("d2c brand website", "genre", "genre:d2c_brand_store"),
             ("caption", "genre", "genre:instagram_caption"), ("review reply", "genre", "genre:comment_reply"),
             # a slash part of a name ("Brand" of "Brand / business naming") must not outweigh the request's words
             ("brand guidelines", "genre", "genre:brand_voice_guide"),
             ("faq page for my clinic", "genre", "genre:faq_page")]

    def test_find_returns_the_known_card_first(self):
        for q, kind, want in self.CASES:
            with self.subTest(q=q):
                self.assertEqual(pcw.find(q, kind, 1)[0]["id"], want)

    def test_a_shorthand_still_finds_cards(self):
        """repair 2: a word of 5+ letters that is no card's whole token matches the name/alias tokens it begins
        ("advert" -> advertorial); "insta" and "churn" are aliases now."""
        for q in ("insta", "churn", "advert"):
            self.assertTrue(pcw.find(q, None, 1), q)
        self.assertIn("advertorial", pcw.find("advert", "genre", 1)[0]["id"])

    def test_every_card_is_found_by_its_own_name(self):
        """Held-out check (no tuning on it): each card's name, searched within its kind, ranks that card first."""
        miss = [c["id"] for c in pcw.cards() if pcw.find(c["name"], c["kind"], 1)[0]["id"] != c["id"]]
        self.assertEqual(miss, [])

    def test_exemplar_briefs_route_to_their_genre(self):
        """Regression floor on realistic requests: each genre card's exemplar_brief, searched among genres, should
        return that genre (199 of 290 with substring matching, 226 with whole tokens on 2026-10-20, 227 once bracket
        qualifiers stopped counting as aliases, 228 with one-word aliases weighted 9)."""
        gs = [c for c in pcw.cards() if c["kind"] == "genre" and c.get("exemplar_brief")]
        ok = sum(pcw.find(c["exemplar_brief"], "genre", 1)[0]["id"] == c["id"] for c in gs)
        self.assertGreaterEqual(ok, 220, f"{ok} of {len(gs)}")

    def test_ids_filter(self):
        self.assertEqual([l.split()[0] for l in pcw.ids("tone", "व्यंग्य")], ["tone:satirical_vyangya"])
        self.assertEqual(pcw.ids("language", "?!"), [])  # a filter with no usable word matches nothing

    def test_brief_sections(self):
        b = pcw.brief(genre="genre:press_release").splitlines()
        self.assertTrue(b[0].startswith("# Brief: ") and b[0].endswith("(genre:press_release)"), b[0])
        heads = [l for l in b if l.startswith("## ")]
        for want in ("## Structure", "## Checklist (every item must be yes)", "## Pitfalls", "## Avoid"):
            self.assertIn(want, heads)
        self.assertTrue(any(h.startswith("## Lint") for h in heads))
        self.assertTrue(any(l.startswith("1. **") for l in b), "structure is a numbered list")

    def test_check_text_flags_platform_and_genre(self):
        lim = pcw.card("plat:linkedin_post")["limits"][0]
        fails, _, _ = pcw.check_text("y" * (lim["max"] + 1), platform="plat:linkedin_post")
        self.assertTrue(any("> max" in f for f in fails), fails)
        fails, _, _ = pcw.check_text("x", genre="genre:nope")
        self.assertEqual(fails, ["no genre card 'genre:nope'"])


class Docs(unittest.TestCase):
    def test_docs_text_is_reproducible(self):
        a, b = pcw.docs_text("2026-01-01"), pcw.docs_text("2026-01-01")
        self.assertEqual(a, b)
        self.assertEqual(pcw._undated(a), pcw._undated(pcw.docs_text("2030-12-31")))  # only the date line moves
        for kind in pcw.KINDS:
            self.assertIn(f"## {kind} (", a)

    def test_selftest(self):
        self.assertEqual(pcw.selftest(), "selftest OK")


if __name__ == "__main__":
    unittest.main()
