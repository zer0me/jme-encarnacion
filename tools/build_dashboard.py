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
CONCEJALES_PAGE = VAULT / "concejales" / "index.md"

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

# Orden canónico de los 12 concejales del período 2021-2026.
# Mesa Directiva primero, luego construir → pivote → contralor.
CONCEJAL_ORDER = [
    "Diego Aquino",
    "Juan Augusto Lichi",
    "Nehemías Cuevas",
    "Keiji Ishibashi",
    "Carlos Marino Fernández",
    "Zulma Memmel",
    "Natalia Enciso",
    "Gloria Arregui",
    "Andrés Morel",
    "Fredy Ortega",
    "Eduardo Florentín",
    "Eduardo Rebruk",
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


def read_concejal(name: str) -> dict | None:
    """Lee una ficha de concejal y devuelve frontmatter + métricas calculadas
    desde las secciones del cuerpo (### Como presente, ### Como ausente, etc.).
    """
    path = VAULT / "personas" / f"{name}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    fm = split_frontmatter(text)
    if not fm:
        return None

    def section_count(label: str) -> int:
        m = re.search(
            rf"^###\s+Como\s+{re.escape(label)}\s*\((\d+)\)",
            text,
            re.MULTILINE,
        )
        return int(m.group(1)) if m else 0

    presente = section_count("presente")
    ausente = section_count("ausente")
    autor = section_count("autor")
    pte_mesa = section_count("presidente de mesa")
    pte_sesion = section_count("presidente de sesión")

    asistencia_pct: int | None = None
    if presente + ausente > 0:
        asistencia_pct = round(100 * presente / (presente + ausente))

    return {
        "nombre": fm.get("nombre", name),
        "slug": name,
        "cargo": fm.get("cargo", "—"),
        "bancada": fm.get("bancada", "s/d"),
        "bloque": fm.get("bloque", "—"),
        "rasgo": fm.get("rasgo", ""),
        "votos_clave": fm.get("votos_clave") or [],
        "apariciones": fm.get("apariciones", 0),
        "presente": presente,
        "ausente": ausente,
        "asistencia_pct": asistencia_pct,
        "autor": autor,
        "presidente_mesa": pte_mesa,
        "presidente_sesion": pte_sesion,
    }


def load_concejales() -> list[dict]:
    out: list[dict] = []
    for name in CONCEJAL_ORDER:
        c = read_concejal(name)
        if c is None:
            print(f"  WARN: ficha de concejal '{name}' no encontrada", file=sys.stderr)
            continue
        out.append(c)
    return out


def _cargo_line(c: dict) -> str:
    """Compone «Cargo · Bancada» para el subtítulo de la tarjeta."""
    cargo = c["cargo"]
    bancada = c["bancada"]
    if bancada in ("s/d", "—", "", None):
        return cargo
    return f"{cargo} · {bancada}"


def build_grilla_concejales() -> str:
    """Grilla compacta de 12 tarjetas mini para el DASHBOARD."""
    concejales = load_concejales()
    out: list[str] = ['<div class="jme-concejales-grid">', ""]

    for c in concejales:
        bloque = c["bloque"]
        ratio_total = c["presente"] + c["ausente"]
        if ratio_total > 0:
            asis = f'{c["asistencia_pct"]}%'
            ratio = f'{c["presente"]}/{ratio_total}'
        else:
            asis = "—"
            ratio = "—"

        out.append(f'<div class="jme-concejal-card mini bloque-{bloque}">')
        out.append("")
        out.append(f'**[[{c["slug"]}]]**')
        out.append(f'<small>{_cargo_line(c)}</small>')
        out.append("")
        out.append(f'📊 Asistencia {asis} ({ratio})  ')
        out.append(f'✍ Autorías: {c["autor"]}  ')
        out.append(f'🪑 Pte de mesa: {c["presidente_mesa"]}')
        if c["rasgo"]:
            out.append("")
            out.append(f'<small class="jme-concejal-rasgo">{c["rasgo"]}</small>')
        out.append("")
        out.append("</div>")
        out.append("")

    out.append("</div>")
    return "\n".join(out).rstrip()


def build_tarjetas_concejales() -> str:
    """Tarjetas completas (con votos clave) para concejales/index.md."""
    concejales = load_concejales()
    out: list[str] = ['<div class="jme-concejales-grid full">', ""]

    for c in concejales:
        bloque = c["bloque"]
        ratio_total = c["presente"] + c["ausente"]
        if ratio_total > 0:
            asis = f'{c["asistencia_pct"]}%'
            ratio_str = f'{c["presente"]} presente · {c["ausente"]} ausente'
        else:
            asis = "—"
            ratio_str = "—"

        bancada_str = "" if c["bancada"] in ("s/d", "—", "", None) else f' · {c["bancada"]}'
        bloque_str = "" if bloque in ("—", "", None) else f' · Bloque «{bloque}»'

        out.append(f'<div class="jme-concejal-card full bloque-{bloque}">')
        out.append("")
        out.append(f'### [[{c["slug"]}]]')
        out.append(f'*{c["cargo"]}{bancada_str}{bloque_str}*')
        out.append("")
        if c["rasgo"]:
            out.append(f'> {c["rasgo"]}')
            out.append("")
        out.append(f'**Asistencia plenaria** · {asis} ({ratio_str})  ')
        out.append(f'**Productividad legislativa** · {c["autor"]} minutas/resoluciones como autor  ')
        rol_extra = []
        if c["presidente_mesa"]:
            rol_extra.append(f'{c["presidente_mesa"]}× pte de mesa')
        if c["presidente_sesion"]:
            rol_extra.append(f'{c["presidente_sesion"]}× pte de sesión')
        rol_line = " · ".join(rol_extra) if rol_extra else "—"
        out.append(f'**Rol de mesa** · {rol_line}')
        out.append("")

        votos = c["votos_clave"]
        if votos:
            out.append("**Votos clave**")
            out.append("")
            out.append("| Acta | Fecha | Tema | Voto |")
            out.append("|---|---|---|---|")
            for v in votos:
                out.append(
                    f'| {v.get("acta", "—")} '
                    f'| {v.get("fecha", "—")} '
                    f'| {v.get("tema", "—")} '
                    f'| {v.get("voto", "—")} |'
                )
            out.append("")

        out.append("</div>")
        out.append("")

    out.append("</div>")
    return "\n".join(out).rstrip()


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


def process_file(target: Path, blocks: list[tuple[str, callable]]) -> bool:
    """Aplica builders a un archivo destino. Devuelve True si hubo cambios."""
    if not target.exists():
        print(f"  WARN: {target} no existe — bloques salteados", file=sys.stderr)
        return False

    text = target.read_text(encoding="utf-8")
    new = text
    for block_name, builder in blocks:
        content = builder()
        new, changed = replace_block(new, block_name, content)
        marker = "updated" if changed else "no change"
        print(f"  {target.name:24s} {block_name:22s} {marker}")

    if new == text:
        return False
    target.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    if not DASHBOARD.exists():
        print(f"ERROR: {DASHBOARD} not found.", file=sys.stderr)
        return 1

    print("Regenerating dynamic blocks...")

    targets: list[tuple[Path, list[tuple[str, callable]]]] = [
        (
            DASHBOARD,
            [
                ("metricas-vault", build_metricas_vault),
                ("mocs-estado", build_mocs_estado),
                ("ultimas-actas", build_ultimas_actas),
                ("grilla-concejales", build_grilla_concejales),
            ],
        ),
        (
            CONCEJALES_PAGE,
            [
                ("tarjetas-concejales", build_tarjetas_concejales),
            ],
        ),
    ]

    any_changes = False
    for target, blocks in targets:
        changed = process_file(target, blocks)
        any_changes = any_changes or changed

    if not any_changes:
        print("Todo al día — sin cambios.")
        return 0
    print("OK — archivos actualizados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
