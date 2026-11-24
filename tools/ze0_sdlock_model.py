#!/usr/bin/env python3
"""Offline checks for the M2.23 fixed-password SD card option.

Verifies the ze0-m223 patch text exposes the fixed-pwd/fixed-locked card
properties and the sd-fixed-pwd/sd-fixed-locked machine options, that the
reset path installs the password into the card's existing pwd[16]/pwd_len,
and that a fixed pwd of any length <= 16 is accepted while longer values
are clamped.  No QEMU binary or vendor data is needed.
"""
import argparse
import re
from pathlib import Path

PATCH = "ze0-0020-sd-fixed-pwd.patch"


def check(got, want, label):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + label)
    return ok


def read_patch(root):
    path = Path(root) / "tools/qemu-ze0/patches" / PATCH
    return path.read_text(encoding="utf-8")


def selftest(root):
    patch = read_patch(root)
    fails = 0
    checks = [
        ("card fixed-pwd prop", 'DEFINE_PROP_STRING("fixed-pwd"' in patch, True),
        ("card fixed-locked prop", 'DEFINE_PROP_BOOL("fixed-locked"' in patch, True),
        ("machine sd-fixed-pwd option",
         'object_property_add_str(obj, "sd-fixed-pwd"' in patch, True),
        ("machine sd-fixed-locked option",
         'object_property_add_bool(obj, "sd-fixed-locked"' in patch, True),
        ("forward to card fixed-pwd",
         'qdev_prop_set_string(card, "fixed-pwd"' in patch, True),
        ("forward to card fixed-locked",
         'qdev_prop_set_bit(card, "fixed-locked"' in patch, True),
        ("reset copies into pwd[16]",
         "memcpy(sd->pwd, sd->fixed_pwd, n)" in patch, True),
        ("reset clamps to 16 bytes", "if (n > 16)" in patch, True),
        ("reset sets pwd_len", "sd->pwd_len = n" in patch, True),
        ("reset sets CARD_IS_LOCKED for fixed",
         "sd->fixed_locked" in patch and "CARD_IS_LOCKED" in patch, True),
        ("no TOFU default change",
         "s->sd_pwd_tofu = true" not in patch, True),
        ("no real password literal", "Clarion" not in patch, True),
    ]
    for label, got, want in checks:
        if not check(got, want, label):
            fails += 1
    print("sd-fixed-pwd selftest: %d checks, %d failed" % (len(checks), fails))
    return 1 if fails else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = p.parse_args()
    if args.selftest:
        return selftest(args.root)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
