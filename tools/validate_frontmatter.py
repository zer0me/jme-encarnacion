"""Validate YAML frontmatter of every .md under content/.

Reports every file whose frontmatter fails to parse so we can fix the source
in the vault before publishing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent / "content"


def split_frontmatter(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end].strip("\n")


def main() -> int:
    failures: list[tuple[Path, str]] = []
    parsed = 0
    skipped = 0

    for md in ROOT.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        fm = split_frontmatter(text)
        if fm is None:
            skipped += 1
            continue
        try:
            yaml.safe_load(fm)
            parsed += 1
        except yaml.YAMLError as exc:
            failures.append((md, str(exc).split("\n")[0]))

    print(f"Parsed OK: {parsed}")
    print(f"No frontmatter (skipped): {skipped}")
    print(f"Failures: {len(failures)}")
    print()

    for path, err in failures:
        rel = path.relative_to(ROOT.parent)
        print(f"  {rel}")
        print(f"    -> {err}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
