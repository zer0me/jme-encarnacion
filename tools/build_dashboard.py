"""Regenerate dynamic tables inside DASHBOARD.md from vault state.

Reads the vault (Google Drive) and rewrites the three blocks marked with
HTML comment fences inside DASHBOARD.md:

    <!-- DASHBOARD:BEGIN metricas-vault -->
    ...table...
    <!-- DASHBOARD:END metricas-vault -->

Blocks regenerated:
- metricas-vault: file counts per folder.
- mocs-estado: table of MOCs with frontmatter `estado` and `periodo`.
- ultimas-actas: last 10 actas (most recent by date in filename).

The script is idempotent: running it twice on a clean vault produces no diff.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

VAULT = Path("G:/Mi unidad/JME")
DASHBOARD = VAULT / "DASHBOARD.md"

DOC_FOLDERS = [
    "actas",
    "minutas",
    "resoluciones",
    "informe-gestion",
    "informe-2024",
    "presupuesto",
]

ENTITY_FOLDERS = [
    "personas",
    "instituciones",
    "empresas",
    "normativa",
    "temas",
    "lugares",
]


def split_frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        return yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None


def count_md(folder: str) -> int:
    p = VAULT / folder
    if not p.is_dir():
        return 0
    return len(list(p.glob("*.md")))


def build_metricas_vault() -> str:
    lines = ["| Carpeta | Items |", "|---|---:|"]
    doc_total = 0
    for folder in DOC_FOLDERS:
        n = count_md(folder)
        doc_total += n
        if n > 0:
            lines.append(f"| `{folder}/` | {n} |")
    lines.append(f"| **Total documentos curados** | **{doc_total}** |")

    ent_total = 0
    for folder in ENTITY_FOLDERS:
        n = count_md(folder)
        ent_total += n
        if n > 0:
            lines.append(f"| `{folder}/` | {n} |")
        else:
            lines.append(f"| `{folder}/` | — |")
    lines.append(f"| **Total stubs de entidades** | **{ent_total}+** |")

    moc_count = len(list((VAULT / "_MOCs").glob("MOC *.md")))
    lines.append(f"| `_MOCs/` | {moc_count} MOCs + README |")
    return "\n".join(lines)


def build_mocs_estado() -> str:
    moc_dir = VAULT / "_MOCs"
    rows: list[tuple[str, str, str]] = []
    for moc_file in sorted(moc_dir.glob("MOC *.md")):
        fm = split_frontmatter(moc_file.read_text(encoding="utf-8"))
        if not fm:
            continue
        estado = str(fm.get("estado", "—")).strip()
        periodo = str(fm.get("periodo", "—")).strip()
        rows.append((moc_file.stem, estado, periodo))

    # Sort: activos first, watch second, cerrados/other last; stable secondary
    # by name for deterministic output.
    estado_order = {"activo": 0, "watch": 1, "cerrado": 2}
    rows.sort(key=lambda r: (estado_order.get(r[1], 9), r[0]))

    lines = ["| MOC | Estado | Período |", "|---|---|---|"]
    for name, estado, periodo in rows:
        lines.append(f"| [[{name}]] | {estado} | {periodo} |")
    return "\n".join(lines)


def build_ultimas_actas(n: int = 10) -> str:
    acta_dir = VAULT / "actas"
    actas = sorted(
        (p for p in acta_dir.glob("*.md") if re.match(r"^\d{4}-\d{2}-\d{2} - ", p.stem)),
        key=lambda p: p.stem,
        reverse=True,
    )[:n]

    lines = ["| Fecha | Acta |", "|---|---|"]
    for acta in actas:
        m = re.match(r"^(\d{4}-\d{2}-\d{2}) - ", acta.stem)
        fecha = m.group(1) if m else "?"
        lines.append(f"| {fecha} | [[{acta.stem}]] |")
    return "\n".join(lines)


def replace_block(text: str, name: str, content: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"(<!-- DASHBOARD:BEGIN {re.escape(name)} -->)(.*?)(<!-- DASHBOARD:END {re.escape(name)} -->)",
        re.DOTALL,
    )
    if not pattern.search(text):
        print(f"  WARN: marker '{name}' not found in DASHBOARD.md — skipped")
        return text, False
    new = pattern.sub(rf"\1\n\n{content}\n\n\3", text)
    return new, new != text


def main() -> int:
    if not DASHBOARD.exists():
        print(f"ERROR: {DASHBOARD} not found.", file=sys.stderr)
        return 1

    text = DASHBOARD.read_text(encoding="utf-8")
    new = text

    print("Regenerating dynamic blocks...")
    for block_name, builder in [
        ("metricas-vault", build_metricas_vault),
        ("mocs-estado", build_mocs_estado),
        ("ultimas-actas", build_ultimas_actas),
    ]:
        content = builder()
        new, changed = replace_block(new, block_name, content)
        marker = "updated" if changed else "no change"
        print(f"  {block_name:18s} {marker}")

    if new == text:
        print("DASHBOARD.md already up to date.")
        return 0

    DASHBOARD.write_text(new, encoding="utf-8")
    print(f"DASHBOARD.md updated ({DASHBOARD}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
