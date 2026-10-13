"""Shared test helpers: run a CLI as a user would, and make a throwaway copy of the repo for commands that write."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path

HOME = Path(os.environ.get("PCW_HOME") or Path(__file__).resolve().parents[1]).resolve()
COPY = ["pcw.py", "pipeline.py", "CONTRACT.md", "PCW.md", "README.md", "harvest", "cards", "gallery", "work/batches",
        "work/gaps.jsonl", "work/lead/status.py", "work/lead/collect_fixes.py"]
sys.path.insert(0, str(HOME))


def cli(script, *args, home=HOME, stdin=""):
    """(exit code, stdout) of `python <home>/<script> args...`, run from a neutral folder against `home`."""
    env = dict(os.environ, PCW_HOME=str(home), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(home / script), *map(str, args)], input=stdin, capture_output=True,
                       text=True, encoding="utf-8", env=env, cwd=tempfile.gettempdir())
    return r.returncode, r.stdout


def tmp_home():
    """A copy of the tracked data in a temp folder (caller removes it with shutil.rmtree)."""
    d = Path(tempfile.mkdtemp(prefix="pcw_test_"))
    for rel in COPY:
        src, dst = HOME / rel, d / rel
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return d


def snapshot(root):
    """{relative path: bytes} for every file under root (to prove a re-run changed nothing)."""
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts}
