#!/usr/bin/env python3
"""Lint docs/experiments/EXP-*.md against TEMPLATE.md structure.

Report only: no EXP is ever edited. The required set of ``##`` headings and
the five ``## Method`` part labels are parsed from TEMPLATE.md at run time, so
a drift in the template changes what this tool requires. Matching normalises
case and surrounding whitespace.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "docs" / "experiments" / "TEMPLATE.md"

HASH_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
ELISION_RE = re.compile(r"#[ \t]*(?:\.\.\.|…)")
WAIVER_RE = re.compile(r"`[ \t]*none[ \t]*\(tool-only task\)[ \t]*`", re.I)
HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.M)
PART_RE = re.compile(r"^[ \t]*[0-9]+\.[ \t]+\*\*([^*]+?)\*\*", re.M)
SUBHEADING_PART_RE = re.compile(r"^###[ \t]+([0-9]+)\.[ \t]+(.+?)[ \t]*$", re.M)
METHOD_ALIAS_RE = re.compile(r"^method\b", re.I)
PART_SUFFIX_RE = re.compile(r"[ \t]+\([^()]*\)[ \t]*$")
SAMPLE_RE = re.compile(r"^[ \t]*[-*][ \t]+\*\*sample:\*\*", re.I | re.M)
NEW_BULLET_RE = re.compile(r"^[ \t]*[-*][ \t]+\*\*", re.M)
ANY_HEADING_RE = re.compile(r"^#{1,6}[ \t]", re.M)
BOLD_RE = re.compile(r"\*\*([^*]+?)\*\*")


def norm(text: str) -> str:
    """Normalise a heading or bold part label for name-based matching."""
    return re.sub(r"\s+", " ", text.strip()).lower().rstrip(".")


def part_norm(text: str) -> str:
    """Normalise a Method part label, dropping a trailing parenthetical."""
    return norm(PART_SUFFIX_RE.sub("", text))


def part_markers(method: str) -> list[tuple[int, int, str]]:
    """Return (start, end, label) for both numbered-bold and ### part spellings.

    Markers are in document order so a Commands part can be sliced up to the
    first following part regardless of which spelling the record uses.
    """
    markers: list[tuple[int, int, str]] = []
    for m in PART_RE.finditer(method):
        markers.append((m.start(), m.end(), part_norm(m.group(1))))
    for m in SUBHEADING_PART_RE.finditer(method):
        markers.append((m.start(), m.end(), part_norm(m.group(2))))
    markers.sort()
    return markers


@dataclass(frozen=True)
class Requirements:
    headings: tuple[str, ...]
    parts: tuple[str, ...]
    source: str


def load_requirements(path: Path) -> Requirements:
    """Parse the heading set and the five Method part labels from a template."""
    text = path.read_text(encoding="utf-8")
    headings = tuple(dict.fromkeys(norm(m.group(1)) for m in HEADING_RE.finditer(text)))
    method = section_bodies(text).get("method")
    parts = ()
    if method is not None:
        parts = tuple(dict.fromkeys(norm(m.group(1)) for m in PART_RE.finditer(method)))
    return Requirements(headings=headings, parts=parts, source=str(path))


def section_bodies(text: str) -> dict[str, str]:
    """Map each normalised ``##`` heading to the body text below it.

    Several ``## Method ...`` headings are concatenated under the ``method``
    key: a record may put its five parts in a second Method-titled section.
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            if current is not None:
                sections.setdefault(current, []).append("\n".join(buf))
            key = norm(m.group(1))
            current = "method" if METHOD_ALIAS_RE.match(key) else key
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections.setdefault(current, []).append("\n".join(buf))
    return {key: "\n".join(bodies) for key, bodies in sections.items()}


def preamble(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if HEADING_RE.match(line):
            break
        out.append(line)
    return "\n".join(out)


def sample_bullet(text: str) -> str | None:
    """Return the Sample bullet with its wrapped continuation lines joined."""
    lines = preamble(text).splitlines()
    for i, line in enumerate(lines):
        if not SAMPLE_RE.match(line):
            continue
        collected = [line]
        for nxt in lines[i + 1:]:
            if NEW_BULLET_RE.match(nxt) or ANY_HEADING_RE.match(nxt) or not nxt.strip():
                break
            collected.append(nxt)
        return "\n".join(collected)
    return None


def commands_part(method: str, parts: tuple[str, ...]) -> str:
    """Slice Method part 2 (Commands), up to the next part marker."""
    if len(parts) < 2:
        return ""
    target = parts[1]
    markers = part_markers(method)
    start: int | None = None
    for i, (mstart, mend, label) in enumerate(markers):
        if label == target:
            start = mend
            if i + 1 < len(markers):
                end = markers[i + 1][0]
            else:
                end = len(method)
            return method[start:end]
    return ""


def check_text(text: str, req: Requirements) -> list[str]:
    """Return the list of reasons this record fails, empty means PASS."""
    reasons: list[str] = []
    bodies = section_bodies(text)
    for heading in req.headings:
        if heading not in bodies:
            reasons.append(f'missing heading "## {heading}"')
    if "method" not in bodies:
        return reasons
    method = bodies["method"]
    labels = {part_norm(m.group(1)) for m in BOLD_RE.finditer(method)}
    labels.update(label for _, _, label in part_markers(method))
    for part in req.parts:
        if part not in labels:
            reasons.append(f'missing Method part "**{part}**"')
    commands = commands_part(method, req.parts)
    if ELISION_RE.search(commands):
        reasons.append("elided command (# ...) in Method part 2 Commands")
    if not re.search(r"`", commands):
        reasons.append("Method part 2 Commands has no runnable command")
    bullet = sample_bullet(text)
    if bullet is None:
        reasons.append("missing Sample bullet")
    elif not WAIVER_RE.search(bullet) and not HASH_RE.search(bullet):
        reasons.append(
            "Sample has no full SHA-256 and no `none (tool-only task)` waiver"
        )
    return reasons


def run_checks(root: Path, req: Requirements, emit: bool = True) -> tuple[int, list[dict]]:
    if root.is_file():
        files = [root]
    else:
        files = sorted({*root.glob("EXP-*.md"), *root.glob("FIX-*.md")})
    results: list[dict] = []
    if not files:
        reason = "no records found (pattern EXP-*.md / FIX-*.md)"
        results.append({"file": str(root), "verdict": "FAIL", "reasons": [reason]})
        if emit:
            print(f"FAIL {root}: {reason}")
    for path in files:
        try:
            reasons = check_text(path.read_text(encoding="utf-8"), req)
        except OSError as exc:
            reasons = [f"unreadable: {exc}"]
        verdict = "FAIL" if reasons else "PASS"
        results.append({"file": path.name, "verdict": verdict, "reasons": reasons})
        if emit:
            if reasons:
                print(f"FAIL {path.name}: " + "; ".join(reasons))
            else:
                print(f"PASS {path.name}")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    ok = failed == 0
    if emit:
        print(f"exp_check: {'OK' if ok else 'FAILED'} "
              f"({len(results)} files, {failed} failed)")
    return (0 if ok else 1), results


GOOD = """# EXP-2026-01-01-FIX: good fixture

- **Status:** done
- **Sample:** `fixture.bin` SHA-256
  `0000000000000000000000000000000000000000000000000000000000000001`
- **Tools:** tools/exp_check.py

## Question
Does the lint pass this record?

## Hypothesis
It passes.

## Inputs
| Item | Value |

## Method
1. **Sample and hash.** The SHA-256 in the Sample bullet above.
2. **Commands.** `python3 tools/exp_check.py docs/experiments`
3. **Controls.** Positive: this record. Negative: an elided command.
4. **Scope.** This synthetic record only.
5. **Falsifier.** A FAIL line naming this file.

## Observations
none.

## Interpretation
- **FACT:** none.

## Conclusion
none.

## Overtaken by a later commit
none.

## Reproduction
`python3 tools/exp_check.py docs/experiments`

## Follow-ups
- [ ] none.
"""


SUBHEADING_GOOD = GOOD.replace(
    "## Method\n"
    "1. **Sample and hash.** The SHA-256 in the Sample bullet above.\n"
    "2. **Commands.** `python3 tools/exp_check.py docs/experiments`\n"
    "3. **Controls.** Positive: this record. Negative: an elided command.\n"
    "4. **Scope.** This synthetic record only.\n"
    "5. **Falsifier.** A FAIL line naming this file.\n",
    "## Method\n"
    "The five parts below use the named subheading spelling.\n\n"
    "## Method — five parts\n"
    "### 1. Sample and hash\n"
    "The SHA-256 in the Sample bullet above.\n\n"
    "### 2. Commands\n"
    "`python3 tools/exp_check.py docs/experiments`\n\n"
    "### 3. Controls\n"
    "Positive: this record. Negative: an elided command.\n\n"
    "### 4. Scope\n"
    "This synthetic record only.\n\n"
    "### 5. Falsifier (state before result, at both levels)\n"
    "A FAIL line naming this file.\n",
)


def set_sample(text: str, bullet: str) -> str:
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if SAMPLE_RE.match(line):
            out.append(bullet)
            skipping = True
        elif skipping and NEW_BULLET_RE.match(line):
            skipping = False
            out.append(line)
        elif not skipping:
            out.append(line)
    return "\n".join(out) + "\n"


def selftest() -> int:
    req = load_requirements(TEMPLATE_PATH)
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, text: str, reqs: Requirements | None,
               expect_empty: bool, needle: str = "") -> None:
        reasons = check_text(text, reqs or req)
        ok = (not reasons) if expect_empty else any(needle in r for r in reasons)
        checks.append((name, ok, "; ".join(reasons)))

    record("compliant record", GOOD, None, True)
    case_space = re.sub(
        r"^## (.+?)[ \t]*$",
        lambda m: "##  " + m.group(1).lower() + "  ",
        GOOD, flags=re.M,
    )
    record("case/spacing headings", case_space, None, True)
    record("backticked waiver",
           set_sample(GOOD, "- **Sample:** `none (tool-only task)` — no bytes."),
           None, True)
    record("hash dropped",
           set_sample(GOOD, "- **Sample:** `fixture.bin` (hash omitted)."),
           None, False, "SHA-256")
    record("bare none", set_sample(GOOD, "- **Sample:** none"),
           None, False, "SHA-256")
    record("wrong parenthetical",
           set_sample(GOOD, "- **Sample:** `none (manual task)` — no bytes."),
           None, False, "SHA-256")
    record("elided command", GOOD.replace(
        "2. **Commands.** `python3 tools/exp_check.py docs/experiments`",
        "2. **Commands.** `python3 tools/x.py IMG  # ...`"),
        None, False, "elided command")
    record("Method renamed", GOOD.replace("## Method", "## Approach"),
           None, False, 'missing heading "## method"')

    record("subheading parts pass", SUBHEADING_GOOD, None, True)
    record("subheading falsifier removed", SUBHEADING_GOOD.replace(
        "### 5. Falsifier (state before result, at both levels)\n"
        "A FAIL line naming this file.\n", ""),
        None, False, 'missing Method part "**falsifier**"')
    record("subheading commands removed", SUBHEADING_GOOD.replace(
        "### 2. Commands\n"
        "`python3 tools/exp_check.py docs/experiments`\n\n", ""),
        None, False, 'missing Method part "**commands**"')
    record("no runnable command", GOOD.replace(
        "2. **Commands.** `python3 tools/exp_check.py docs/experiments`",
        "2. **Commands.** The commands are not listed here."),
        None, False, "has no runnable command")
    record("subheading elided command", SUBHEADING_GOOD.replace(
        "`python3 tools/exp_check.py docs/experiments`",
        "`python3 tools/x.py IMG  # ...`"),
        None, False, "elided command")

    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="exp_check_selftest_") as td:
        tmp = Path(td)
        extra = tmp / "TEMPLATE-extra.md"
        extra.write_text(template_text + "\n## Audit\ntext\n", encoding="utf-8")
        record("template heading drift", GOOD,
               load_requirements(extra), False, 'missing heading "## audit"')
        renamed = tmp / "TEMPLATE-renamed.md"
        renamed.write_text(
            template_text.replace("4. **Scope.**", "4. **Coverage.**"),
            encoding="utf-8",
        )
        record("template part drift", GOOD,
               load_requirements(renamed), False,
               'missing Method part "**coverage**"')

    bad = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if not ok else ""))
    print(f"exp_check selftest: {'OK' if not bad else 'FAILED'} "
          f"({len(checks) - len(bad)}/{len(checks)} checks, "
          f"{len(req.headings)} headings, {len(req.parts)} parts)")
    return 0 if not bad else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="lint EXP-*.md records against docs/experiments/TEMPLATE.md"
    )
    parser.add_argument("root", nargs="?", default="docs/experiments",
                        help="directory of EXP-*.md files, or one EXP file")
    parser.add_argument("--json", action="store_true",
                        help="print the same verdict as machine-readable JSON")
    parser.add_argument("--selftest", action="store_true",
                        help="run the built-in synthetic checks")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    req = load_requirements(TEMPLATE_PATH)
    code, results = run_checks(Path(args.root), req, emit=not args.json)
    if args.json:
        doc = {
            "template_headings": len(req.headings),
            "template_parts": len(req.parts),
            "total": len(results),
            "failed": sum(1 for r in results if r["verdict"] == "FAIL"),
            "ok": code == 0,
            "files": results,
        }
        print(json.dumps(doc, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
