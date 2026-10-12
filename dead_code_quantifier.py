#!/usr/bin/env python3
"""dead-code-quantifier: AST-level unreferenced-definition statistics.

Two confidence modes over one AST pass:
  conservative -- top-level functions/classes only; decorated defs, dunders,
                  main(), and __all__ exports are always considered alive.
  aggressive   -- additionally reports class methods, module-level variables
                  and decorated defs that are never referenced.
A name counts as referenced if it appears as a loaded Name or an attribute
access anywhere in the scanned file set. Self-recursion keeps a def alive by
design (conservative bias; see README Limits).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

__version__ = "0.1.1"

MODES = ("conservative", "aggressive")


def _target_names(target):
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names = []
        for elt in target.elts:
            names.extend(_target_names(elt))
        return names
    return []


def _collect_defs(tree):
    defs = []

    def rec(node, in_class):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.append({"kind": "function", "name": child.name,
                             "line": child.lineno, "end": child.end_lineno or child.lineno,
                             "decorated": bool(child.decorator_list), "in_class": in_class})
                rec(child, False)
            elif isinstance(child, ast.ClassDef):
                defs.append({"kind": "class", "name": child.name,
                             "line": child.lineno, "end": child.end_lineno or child.lineno,
                             "decorated": bool(child.decorator_list), "in_class": False})
                rec(child, True)
            else:
                if isinstance(node, ast.Module) and isinstance(child, ast.Assign):
                    for target in child.targets:
                        for name in _target_names(target):
                            defs.append({"kind": "variable", "name": name,
                                         "line": child.lineno, "end": child.end_lineno or child.lineno,
                                         "decorated": False, "in_class": False})
                elif isinstance(node, ast.Module) and isinstance(child, ast.AnnAssign):
                    for name in _target_names(child.target):
                        defs.append({"kind": "variable", "name": name,
                                     "line": child.lineno, "end": child.end_lineno or child.lineno,
                                     "decorated": False, "in_class": False})
                rec(child, in_class)

    rec(tree, False)
    return defs


def _collect_usage(tree):
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__" \
                        and isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            used.add(elt.value)
    return used


def _is_dead(d, used, mode):
    name = d["name"]
    if name.startswith("__") and name.endswith("__"):
        return False
    if name == "main":
        return False
    if name in used:
        return False
    if mode == "conservative":
        if d["kind"] == "variable" or d["in_class"] or d["decorated"]:
            return False
        return True
    return True


def analyze_sources(sources, mode="conservative"):
    """Analyze a mapping {path: source_text}. Returns a report dict."""
    if mode not in MODES:
        raise ValueError("mode must be 'conservative' or 'aggressive'")
    parsed = {}
    errors = []
    for path, source in sources.items():
        try:
            tree = ast.parse(source)
            parsed[path] = {"tree": tree,
                            "defs": _collect_defs(tree),
                            "used": _collect_usage(tree),
                            "total_loc": len(source.splitlines()) if isinstance(source, str) else 0}
        except (SyntaxError, RecursionError, ValueError, TypeError) as exc:
            errors.append({"path": path, "error": "%s: %s" % (type(exc).__name__, exc)})
    global_used = set()
    for info in parsed.values():
        global_used |= info["used"]
    files = []
    dead_count = dead_loc = total_loc = 0
    for path in sorted(parsed):
        info = parsed[path]
        dead = []
        for d in info["defs"]:
            if _is_dead(d, global_used, mode):
                span = d["end"] - d["line"] + 1
                dead.append({"name": d["name"], "kind": d["kind"], "line": d["line"], "loc": span})
                dead_count += 1
                dead_loc += span
        files.append({"path": path, "total_loc": info["total_loc"], "dead": dead})
        total_loc += info["total_loc"]
    return {"mode": mode, "files": files, "errors": errors,
            "totals": {"dead_count": dead_count, "dead_loc": dead_loc, "total_loc": total_loc,
                       "dead_pct": round(100.0 * dead_loc / total_loc, 1) if total_loc else 0.0}}


def analyze_paths(paths, mode="conservative"):
    """Analyze files/directories from the filesystem. Non-fatal errors are
    recorded in report['errors']."""
    sources = {}
    errors = []
    for path in paths:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    sources[path] = fh.read()
            except OSError as exc:
                errors.append({"path": path, "error": str(exc)})
        elif os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs.sort()
                for name in sorted(files):
                    if name.endswith(".py"):
                        sub = os.path.join(root, name)
                        try:
                            with open(sub, "r", encoding="utf-8", errors="replace") as fh:
                                sources[sub] = fh.read()
                        except OSError as exc:
                            errors.append({"path": sub, "error": str(exc)})
        else:
            errors.append({"path": path, "error": "no such file or directory"})
    report = analyze_sources(sources, mode)
    report["errors"].extend(errors)
    return report


def gate_dead_pct(report, threshold):
    """CI gate helper: True when dead% exceeds threshold (None -> never)."""
    if threshold is None:
        return False
    return report["totals"]["dead_pct"] > threshold


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dead-code-quantifier", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_scan = sub.add_parser("scan", help="scan files or directories")
    p_scan.add_argument("targets", nargs="+")
    p_scan.add_argument("--mode", choices=list(MODES), default="conservative")
    p_scan.add_argument("--format", choices=["text", "json"], default="text")
    p_scan.add_argument("--gate", type=float, default=None,
                        help="exit 1 when dead%% exceeds this percentage")
    args = parser.parse_args(argv)
    report = analyze_paths(args.targets, args.mode)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        for f in report["files"]:
            for d in f["dead"]:
                print("%s:%s: dead %s %r (~%d loc)" % (f["path"], d["line"], d["kind"], d["name"], d["loc"]))
        for e in report["errors"]:
            print("error: %s: %s" % (e["path"], e["error"]))
        t = report["totals"]
        print("dead: %d defs, %d/%d loc (%.1f%%) [mode=%s]"
              % (t["dead_count"], t["dead_loc"], t["total_loc"], t["dead_pct"], report["mode"]))
    return 1 if gate_dead_pct(report, args.gate) else 0


if __name__ == "__main__":
    sys.exit(main())
