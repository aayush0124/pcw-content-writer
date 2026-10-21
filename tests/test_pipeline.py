"""pipeline.py: status reads real numbers, doctor, run <stage>, all (idempotent). Writing stages run on a copy."""
import json, shutil, unittest
from collections import Counter

from helpers import HOME, cli, snapshot, tmp_home
import pcw

STAGES = ("harvest", "batches", "cards", "validate", "dupes", "samples", "judge", "fixes", "critic", "docs")


def rows(out):
    """status table -> {stage: (kind, state, numbers)}"""
    got = {}
    for line in out.splitlines()[1:]:
        p = line.split(None, 3)
        if p and p[0] in STAGES:
            got[p[0]] = (p[1], p[2], p[3] if len(p) > 3 else "")
    return got


class Status(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.out = cli("pipeline.py", "status")
        cls.rows = rows(cls.out)

    def test_exit_code_and_every_stage(self):
        self.assertIn(self.code, (0, 10), self.out)
        self.assertEqual(set(self.rows), set(STAGES))
        self.assertTrue(all(st in ("ok", "attention", "fail") for _, st, _ in self.rows.values()))
        self.assertEqual(self.rows["validate"][1], "ok")

    def test_numbers_are_real(self):
        hv, cs = pcw.harvest(), pcw.cards()
        self.assertTrue(self.rows["harvest"][2].startswith(f"{len(hv)} items"))
        self.assertTrue(self.rows["cards"][2].startswith(f"{len(cs)} cards"))
        tested = [c for c in cs if c["kind"] in ("genre", "hook", "framework")]
        v = Counter((c.get("verified") or {}).get("verdict") for c in tested)
        judged = len(tested) - v[None] - v["not_tested"]  # a not_tested verdict is not a judgement
        self.assertIn(f"{judged}/{len(tested)} judged: pass {v['pass']}, weak {v['weak']}, wrong {v['wrong']}, "
                      f"not_tested {v['not_tested']};", self.rows["judge"][2])  # a not_tested card is not hidden
        if v["not_tested"]:
            self.assertEqual(self.rows["judge"][1], "attention")
        n_samples = 0
        for f in {c["_file"] for c in tested}:
            g = HOME / "gallery" / f
            n_samples += len(json.loads(g.read_text(encoding="utf-8"))["samples"]) if g.exists() else 0
        self.assertTrue(self.rows["samples"][2].startswith(f"{n_samples}/{len(tested)} "), self.rows["samples"])

    def test_critic_row_reads_the_report(self):
        crit = json.loads((HOME / "cards" / "zz_critic.json").read_text(encoding="utf-8"))
        day = crit.get("as_of") or crit["critic"]["date"]
        self.assertTrue(self.rows["critic"][2].startswith(f"zz_critic.json as of {day}: {len(crit['gaps'])} gaps"),
                        self.rows["critic"])

    def test_agent_stages_name_their_brief(self):
        for stage in ("harvest", "cards", "samples", "judge", "critic"):
            self.assertEqual(self.rows[stage][0], "agent")
        code, out = cli("pipeline.py", "run", "cards")
        self.assertEqual(code, 10)
        self.assertIn("work/BRIEF_CARDS.md", out)


class Commands(unittest.TestCase):
    def test_doctor(self):
        code, out = cli("pipeline.py", "doctor")
        self.assertIn(code, (0, 10), out)
        for word in ("python", "PCW_HOME", "free RAM"):
            self.assertIn(word, out)

    def test_usage_and_bad_stage(self):
        self.assertEqual(cli("pipeline.py")[0], 0)
        self.assertEqual(cli("pipeline.py", "run", "nope")[0], 2)
        self.assertEqual(cli("pipeline.py", "nope")[0], 2)

    def test_read_only_stages(self):
        self.assertEqual(cli("pipeline.py", "run", "validate"), (0, "OK: 0 issues\n"))
        self.assertEqual(cli("pipeline.py", "run", "dupes")[0], 0)


class WritingStages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tmp_home()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_all_then_all_again_changes_nothing(self):
        code, out = cli("pipeline.py", "all", home=self.home)
        self.assertEqual(code, 0, out)
        for stage in ("batches", "validate", "dupes", "fixes", "docs"):
            self.assertIn(f"== {stage}", out)
        self.assertTrue((self.home / "work" / "lead" / "card_fixes.json").exists(), "fixes wrote into the copy")
        self.assertTrue((self.home / "PCW.md").exists())
        first = snapshot(self.home)
        self.assertEqual(cli("pipeline.py", "all", home=self.home)[0], 0)
        self.assertEqual(snapshot(self.home), first)

    def test_docs_writes_the_readme_block_from_status(self):
        cli("pipeline.py", "run", "docs", home=self.home)
        readme = (self.home / "README.md").read_text(encoding="utf-8")
        block = readme[readme.index("<!-- pipeline-status:begin -->"):readme.index("<!-- pipeline-status:end -->")]
        self.assertIn("| harvest | agent | ok |", block)
        self.assertIn("| judge |", block)
        self.assertNotIn("| docs |", block)
        code, out = cli("pipeline.py", "status", home=self.home)
        self.assertEqual(rows(out)["docs"][1], "ok", out)


if __name__ == "__main__":
    unittest.main()
