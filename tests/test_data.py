"""Data integrity, golden queries, brief shape, docs reproducibility and the in-memory selftest (no subprocess)."""
import json, unittest
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
            key = lambda ls: sorted((l.get("field"), l.get("max"), l.get("min"), l.get("unit")) for l in ls or [])  # noqa: E731
            self.assertEqual(key(c.get("limits")), key(self.hv[c["id"]].get("limits")), c["id"])

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
             ("app store metadata apple", "compliance", "comp:apple_app_review_metadata")]

    def test_find_returns_the_known_card_first(self):
        for q, kind, want in self.CASES:
            with self.subTest(q=q):
                self.assertEqual(pcw.find(q, kind, 1)[0]["id"], want)

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
