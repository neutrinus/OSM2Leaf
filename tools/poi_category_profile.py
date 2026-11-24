#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""OSM tag -> ZE0 POI category profile (M5.73).

The profile is data, not code: ``profiles/poi-categories.json`` holds ordered
rules (tag expression -> M4.88 category code -> priority).  ``tools/osm_ingest``
emits ``poi.category = key=value`` on an IMF node; the POI writer (M5.18/M5.63)
needs that expression resolved to one byte-aligned POINT category code.  This
tool performs that resolution and validates the profile against the generated
M4.88 table.

Key rule: a code is used only if it exists in ``docs/format/poi-categories.md``
with a record count > 0.  OSM categories with no factory code are UNMAPPED
(``code: null``): the tool never invents a code, which is the task falsifier.

Commands::

    python3 tools/poi_category_profile.py --selftest
    python3 tools/poi_category_profile.py validate
    python3 tools/poi_category_profile.py map '{"amenity":"fuel"}'
    python3 tools/poi_category_profile.py fixtures
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DEFAULT_PROFILE = REPO_ROOT / "profiles" / "poi-categories.json"
DEFAULT_TABLE = REPO_ROOT / "docs" / "format" / "poi-categories.md"

CODE_RE = re.compile(r"^0x[0-9a-fA-F]{4}$")
ROW_RE = re.compile(
    r"^\|\s*`(0x[0-9a-fA-F]{4})`\s*\|\s*([\d,]+)\s*\|\s*([^|]*)\|\s*([^|]*)\|"
)


class ProfileError(ValueError):
    """The profile or the reference table is structurally unusable."""


def normalize_code(value: Any) -> str | None:
    """Return lowercase ``0xnnnn`` or None for an intentionally unmapped rule."""
    if value is None:
        return None
    if not isinstance(value, str) or not CODE_RE.match(value):
        raise ProfileError(f"bad category code {value!r}: expected 0xnnnn or null")
    return value.lower()


def load_profile(path: str | Path | None = None) -> list[dict[str, Any]]:
    data = json.loads(Path(path or DEFAULT_PROFILE).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ProfileError("profile must be an object with a 'rules' array")
    seen: set[str] = set()
    for rule in data["rules"]:
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid:
            raise ProfileError("rule has no id")
        if rid in seen:
            raise ProfileError(f"duplicate rule id {rid}")
        seen.add(rid)
        if not isinstance(rule.get("priority"), int):
            raise ProfileError(f"rule {rid}: priority must be int")
        if not isinstance(rule.get("match"), dict) or not rule["match"]:
            raise ProfileError(f"rule {rid}: match must be a non-empty object")
        rule["code"] = normalize_code(rule.get("code"))
        for key, value in rule["match"].items():
            if key == "brand_any":
                if not isinstance(value, list) or not value:
                    raise ProfileError(f"rule {rid}: brand_any must be a non-empty list")
            elif not isinstance(value, list) or not value:
                raise ProfileError(f"rule {rid}: match.{key} must be a non-empty list")
    return data["rules"]


def read_category_table(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Parse the generated M4.88 table: code -> {count, icon, name}."""
    text = Path(path or DEFAULT_TABLE).read_text(encoding="utf-8")
    # Only the "## Table" section has (code, count, icon, name); the later
    # "## Ten codes" section reuses the code column with a different layout.
    if "## Table" not in text:
        raise ProfileError("M4.88 table has no '## Table' section")
    section = text.split("## Table", 1)[1].split("## Ten codes", 1)[0]
    table: dict[str, dict[str, Any]] = {}
    for line in section.splitlines():
        match = ROW_RE.match(line)
        if not match:
            continue
        code = match.group(1).lower()
        table[code] = {
            "count": int(match.group(2).replace(",", "")),
            "icon": match.group(3).strip(),
            "name": match.group(4).strip(),
        }
    if not table:
        raise ProfileError("no category rows parsed from M4.88 table")
    return table


def _match(rule: dict[str, Any], tags: dict[str, str]) -> bool:
    for key, accepted in rule["match"].items():
        if key == "brand_any":
            brand = " ".join(
                str(tags.get(k, "")) for k in ("brand", "operator", "name")
            ).upper()
            if not any(value.upper() in brand for value in accepted):
                return False
            continue
        if str(tags.get(key, "")) not in accepted:
            return False
    return True


def resolve(tags: dict[str, str], rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    """First matching rule by ascending priority, then profile order."""
    candidates = sorted(rules, key=lambda r: (r["priority"], r["id"]))
    for rule in candidates:
        if _match(rule, tags):
            return {
                "rule": rule["id"],
                "category": rule.get("category"),
                "code": rule["code"],
                "code_label": rule.get("code_label"),
            }
    return None


def validate(rules: list[dict[str, Any]], table: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Cross-check every targeted code against the M4.88 table (the falsifier)."""
    mapped = [r for r in rules if r["code"] is not None]
    unmapped = [r for r in rules if r["code"] is None]
    bad: list[str] = []
    for rule in mapped:
        row = table.get(rule["code"])
        if row is None:
            bad.append(f"{rule['id']}: {rule['code']} absent from M4.88 table")
        elif row["count"] <= 0:
            bad.append(f"{rule['id']}: {rule['code']} has zero records (falsifier)")
    codes = [r["code"] for r in mapped]
    duplicates = sorted({c for c in codes if codes.count(c) > 1})
    return {
        "rules": len(rules),
        "mapped": len(mapped),
        "unmapped": len(unmapped),
        "table_codes": len(table),
        "targeted_codes": len(set(codes)),
        "duplicate_codes": duplicates,
        "errors": bad,
        "ok": not bad,
    }


def _fixture(rule: dict[str, Any]) -> dict[str, str]:
    """One synthetic OSM object that satisfies exactly this rule's predicate."""
    tags: dict[str, str] = {"name": "Fixture"}
    for key, value in rule["match"].items():
        if key == "brand_any":
            tags["brand"] = value[0]
        else:
            tags[key] = value[0]
    return tags


def selftest() -> int:
    rules = load_profile()
    table = read_category_table()
    checks = 0
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if ok:
            print(f"  ok   {name}")
        else:
            failures.append(name)
            print(f"  FAIL {name} {detail}".rstrip())

    report = validate(rules, table)
    check("profile validates against M4.88 table", report["ok"], str(report["errors"]))
    check("at least 11 rules cover required categories", report["rules"] >= 11,
          str(report["rules"]))
    check("every targeted code has records", not report["errors"], str(report["errors"]))
    check("no two rules share a code", not report["duplicate_codes"],
          str(report["duplicate_codes"]))

    required = {
        "fuel", "charging station", "parking", "restaurant", "hotel",
        "supermarket", "hospital", "pharmacy", "bank/ATM",
        "railway station", "airport",
    }
    covered = {rule.get("category") for rule in rules}
    check("all 11 requested categories present", required <= covered,
          str(sorted(required - covered)))

    # One synthetic object per rule: the resolved code must equal the rule's
    # declared code, or be None for an UNMAPPED rule.
    mismatches: list[str] = []
    for rule in rules:
        got = resolve(_fixture(rule), rules)
        if got is None or got["code"] != rule["code"]:
            mismatches.append(f"{rule['id']}: expected {rule['code']}, got {got}")
    check("synthetic fixture per rule maps to expected code", not mismatches,
          "; ".join(mismatches[:4]))

    # Positive controls: generic fuel/eatery/hotel and a branded hotel.
    pos = [
        ({"amenity": "fuel"}, "0x0190"),
        ({"amenity": "restaurant"}, "0x0391"),
        ({"tourism": "hotel"}, "0x0dac"),
        ({"shop": "supermarket", "brand": "CARREFOUR"}, "0x01a1"),
        ({"tourism": "hotel", "brand": "HILTON"}, "0x0db7"),
    ]
    for tags, expected in pos:
        got = resolve(tags, rules)
        check(f"positive {tags} -> {expected}",
              got is not None and got["code"] == expected, str(got))

    # Negative controls: no rule for these tags; uncovered generic supermarket
    # and a pharmacy stay UNMAPPED rather than inventing a code.
    neg = [
        {"highway": "residential"},
        {"shop": "supermarket", "name": "No Brand Store"},
        {"amenity": "pharmacy"},
        {"amenity": "parking"},
        {"amenity": "charging_station"},
    ]
    for tags in neg:
        got = resolve(tags, rules)
        check(f"negative {tags} -> no code",
              got is None or got["code"] is None, str(got))

    # Falsifier: a fabricated code must be rejected.
    mutated = [dict(r) for r in rules]
    mutated[0]["code"] = "0xffff"
    bad = validate(mutated, table)
    check("falsifier: unknown code rejected", not bad["ok"], str(bad["errors"][:2]))

    print(f"\nchecks: {checks}, failures: {len(failures)}")
    if failures:
        return 1
    print("poi_category_profile selftest: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("validate")
    p = sub.add_parser("map")
    p.add_argument("tags_json")
    sub.add_parser("fixtures")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    try:
        rules = load_profile(args.profile)
        if args.cmd == "validate":
            report = validate(rules, read_category_table())
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1
        if args.cmd == "map":
            tags = json.loads(args.tags_json)
            print(json.dumps(resolve(tags, rules)))
            return 0
        if args.cmd == "fixtures":
            for rule in sorted(rules, key=lambda r: (r["priority"], r["id"])):
                print(json.dumps({
                    "rule": rule["id"], "category": rule.get("category"),
                    "code": rule["code"], "fixture": _fixture(rule),
                }))
            return 0
    except (ProfileError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
