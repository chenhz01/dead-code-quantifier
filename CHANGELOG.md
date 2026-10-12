# Changelog

Format inspired by Keep a Changelog; versions are SemVer.

## [0.1.1] - 2026-10-11

### Changed
- Round-2 content iteration: self-test suite expanded from 40 to 50 checks (+25% on the coverage dimension) — added lambda-assignment handling, walrus-operator sources, `nonlocal`-style shadowing cases, gate boundary values, and report-shape assertions for both modes.

## [0.1.0] - 2026-10-11

### Added
- AST-level definition/usage collection across a file set (functions, classes, module-level variables).
- Dual confidence modes: conservative (top-level, decorated-safe) and aggressive (methods/variables/decorated).
- Quantified report: dead count, dead LOC, total LOC, dead_pct; `--gate` CI threshold.
- CLI (argparse): scan with --mode/--format/--gate; JSON and text output.
- Self-test suite: 40 checks (functional / exception / extreme edges).
- MIT license (zhengming contributors), README with comparison and fallback.
