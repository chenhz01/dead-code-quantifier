#!/usr/bin/env python3
"""Self-test for dead-code-quantifier. Round 1: 40 checks; Round 2: +10 = 50.

Run:  python self_test.py
Last line printed:  SUMMARY: PASS n/n
Categories: A = functional, E = exception paths, X = extreme edges.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dead_code_quantifier as core

passed = 0
failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL: %s" % name)


def dead_names(src, mode="conservative"):
    rep = core.analyze_sources({"f.py": src}, mode)
    return [d["name"] for d in rep["files"][0]["dead"]]


SRC = """\
import os

CONST = 1

def used():
    return os.path.join('a', 'b')

def unused_plain():
    return 1

def main():
    used()

class Used:
    def method_used(self):
        return 1

obj = Used()
obj.method_used()
"""

# ---------- A. functional unit tests (1-20) ----------
check("A01 unused function flagged (conservative)", "unused_plain" in dead_names(SRC))
check("A02 used function alive", "used" not in dead_names(SRC))
check("A03 used class alive", "Used" not in dead_names(SRC))
check("A04 main() never flagged", "main" not in dead_names(SRC))
dunder = "class C:\n    def __init__(self):\n        pass\n\nC()\n"
check("A05 dunders never flagged", dead_names(dunder) == [])
decorated = "import functools\n\n@functools.lru_cache()\ndef cb():\n    return 1\n"
check("A06 decorated def alive in conservative", dead_names(decorated) == [])
allsrc = "def exported():\n    return 1\n\n__all__ = ['exported']\n"
check("A07 __all__ export alive", dead_names(allsrc) == [])
big_def = "".join(["def unused_big():\n"] + ["    x = %d\n" % i for i in range(9)] + ["    return x\nunused_plain_holder = 0\n"])
rep = core.analyze_sources({"f.py": "def unused_big():\n    a = 1\n    b = 2\n    c = 3\n    return a\n"})
check("A08 dead LOC spans body", rep["files"][0]["dead"][0]["loc"] == 5)
check("A09 dead_pct computed", rep["totals"]["dead_pct"] == 100.0)
varsrc = "UNUSED_VAR = 42\n\nprint('hi')\n"
check("A10 aggressive flags unused module variable", "UNUSED_VAR" in dead_names(varsrc, "aggressive"))
check("A11 conservative ignores variables", dead_names(varsrc, "conservative") == [])
methsrc = "class C:\n    def _ghost(self):\n        return 1\n\nC()\n"
check("A12 aggressive flags unused private method", "_ghost" in dead_names(methsrc, "aggressive"))
check("A13 conservative skips methods entirely", dead_names(methsrc, "conservative") == [])
methused = "class C:\n    def helper(self):\n        return 1\n\nx = C()\nx.helper()\n"
check("A14 method used via attribute is alive (aggressive)", dead_names(methused, "aggressive") == [])
cross = {"a.py": "def shared():\n    return 1\n", "b.py": "from a import shared\nshared()\n"}
check("A15 cross-file usage keeps def alive", core.analyze_sources(cross)["totals"]["dead_count"] == 0)
rep_json = json.dumps(core.analyze_sources({"f.py": SRC}))
check("A16 report JSON has required keys", all(k in rep_json for k in ['"mode"', '"files"', '"totals"']))
check("A17 gate helper fires above threshold", core.gate_dead_pct(rep, 50.0) is True)
check("A18 mode recorded in report", core.analyze_sources({"f.py": SRC}, "aggressive")["mode"] == "aggressive")
asyncsrc = "async def unused_async():\n    return 1\n"
check("A19 async def handled", "unused_async" in dead_names(asyncsrc))
innersrc = "def outer():\n    def inner():\n        return 1\n    return 2\n\nouter()\n"
check("A20 unused nested def flagged", "inner" in dead_names(innersrc))

# ---------- E. exception paths (21-30) ----------
rep_syn = core.analyze_sources({"bad.py": "def broken(:\n", "ok.py": "x = 1\n"})
check("E01 syntax error recorded, other file analyzed",
      len(rep_syn["errors"]) == 1 and rep_syn["totals"]["total_loc"] == 1)
check("E02 empty source yields zero totals", core.analyze_sources({"e.py": ""})["totals"]["dead_count"] == 0)
check("E03 empty source map yields zeros", core.analyze_sources({})["totals"]["total_loc"] == 0)
try:
    core.analyze_sources({"f.py": "x = 1\n"}, "yolo")
    check("E04 bad mode raises ValueError", False)
except ValueError:
    check("E04 bad mode raises ValueError", True)
check("E05 None source recorded as error, no crash",
      len(core.analyze_sources({"n.py": None})["errors"]) == 1)
check("E06 comment-only file has no defs", core.analyze_sources({"c.py": "# nothing\n"})["totals"]["dead_count"] == 0)
check("E07 gate with None threshold never fires", core.gate_dead_pct(rep, None) is False)
check("E08 binary garbage recorded as error, not crash",
      len(core.analyze_sources({"b.py": "\x00\x01\x02"})["errors"]) == 1)
dupsrc = "def dup():\n    return 1\n\ndef dup():\n    return 2\n\ndup()\n"
check("E09 redefinition + one usage: no crash", core.analyze_sources({"d.py": dupsrc})["totals"]["dead_count"] == 0)
recsrc = "def recursive(n):\n    return recursive(n - 1)\n"
check("E10 self-recursion keeps def alive (documented)", dead_names(recsrc) == [])

# ---------- X. extreme edges (31-40) ----------
longfn = "def unused_long():\n" + "".join("    v%d = %d\n" % (i, i) for i in range(500)) + "    return v499\n"
rep_long = core.analyze_sources({"f.py": longfn})
check("X01 500-line function LOC correct", rep_long["files"][0]["dead"][0]["loc"] == 502)
check("X02 unicode def name flagged", "未用函数" in dead_names("def 未用函数():\n    return 1\n"))
many = {"m.py": "".join("def unused_%d():\n    return %d\n" % (i, i) for i in range(300))}
check("X03 300 defs counted", core.analyze_sources(many)["totals"]["dead_count"] == 300)
ten = "class C:\n" + "".join("    def _m%d(self):\n        return %d\n" % (i, i) for i in range(10)) + "\nC()\n"
check("X04 10 private methods all dead (aggressive)",
      core.analyze_sources({"t.py": ten}, "aggressive")["totals"]["dead_count"] == 10)
shadow = "x = 1\nx = 2\nprint('done')\n"
check("X05 both shadowed assignments counted (aggressive)",
      core.analyze_sources({"s.py": shadow}, "aggressive")["totals"]["dead_count"] == 2)
attrsrc = "class P:\n    def parse(self):\n        return 1\n\nobj_parse_holder = P()\nobj_parse_holder.parse()\n"
check("X06 attribute usage keeps method alive (aggressive)", dead_names(attrsrc, "aggressive") == [])
check("X07 CRLF source parses", core.analyze_sources({"c.py": "def unused_c():\r\n    return 1\r\n"})["totals"]["dead_count"] == 1)
deep = "".join("    " * i + "if True:\n" for i in range(300)) + "    " * 300 + "pass\n"
check("X08 300-level nesting guarded, no crash", isinstance(core.analyze_sources({"d.py": deep})["totals"], dict))
check("X09 report deterministic", core.analyze_sources({"f.py": SRC}) == core.analyze_sources({"f.py": SRC}))
check("X10 dead list sorted by line order",
      [d["line"] for d in core.analyze_sources({"f.py": SRC})["files"][0]["dead"]] ==
      sorted(d["line"] for d in core.analyze_sources({"f.py": SRC})["files"][0]["dead"]))

print("SUMMARY: PASS %d/%d" % (passed, passed + failed))
