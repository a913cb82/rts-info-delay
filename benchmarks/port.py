"""Explicit port tool: copy code between personality packages.

Usage:
  python benchmarks/port.py --from pro --to turtle --file core.py
  python benchmarks/port.py --from pro --to turtle --show pack_print

File mode copies src/bots/<from>/<file> over src/bots/<to>/<file>
(.bak written). --show prints a symbol's source (function/class) from a
package file for manual porting — symbol-level merges are deliberate
surgery, not automation (dependencies differ per era).

Rationale: packages share NOTHING by default; every cross-personality
change is an explicit copy recorded here (and in the commit message).
"""
import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKGS = ["pro", "aggressive", "expander", "turtle", "greedy"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, choices=PKGS)
    ap.add_argument("--to", dest="dst", required=True, choices=PKGS)
    ap.add_argument("--file", default="core.py")
    ap.add_argument("--show", default=None, help="print a symbol's source (no copy)")
    args = ap.parse_args(argv)
    src = ROOT / "src" / "bots" / args.src / args.file
    if not src.exists():
        print(f"missing {src}")
        return 1
    if args.show:
        text = src.read_text()
        m = re.search(rf"^(def {re.escape(args.show)}\(.*?)(?=^\S|\Z)",
                      text, re.M | re.S)
        if not m:
            m = re.search(rf"^(class {re.escape(args.show)}\b.*?)(?=^\S|\Z)",
                          text, re.M | re.S)
        print(m.group(1) if m else f"symbol {args.show} not found in {src}")
        return 0
    dst = ROOT / "src" / "bots" / args.dst / args.file
    if dst.exists():
        shutil.copy2(dst, dst.with_suffix(dst.suffix + ".bak"))
    shutil.copy2(src, dst)
    print(f"ported {args.src}/{args.file} -> {args.dst}/{args.file} (.bak kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
