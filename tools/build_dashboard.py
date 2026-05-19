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
import unicodedata
from pathlib import Path

import yaml

VAULT = Path("G:/Mi unidad/JME")
DASHBOARD = VAULT / "DASHBOARD.md"
CONCEJALES_PAGE = VAULT / "concejales" / "index.md"
PHOTO_DIR = VAULT / "concejales" / "fotos"
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")
SITE_BASE = "https://zer0me.github.io/jme-encarnacion"


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _find_photo_url(slug: str) -> str | None:
    """Return the Quartz-served URL for the concejal's photo, or None."""
    if not PHOTO_DIR.exists():
        return None
    target = None
    for ext in PHOTO_EXTS:
        candidate = PHOTO_DIR / f"{slug}{ext}"
        if candidate.exists():
            target = candidate.name
            break
    if target is None:
        slug_ascii = _strip_accents(slug).lower()
        for f in PHOTO_DIR.iterdir():
            if f.suffix.lower() in PHOTO_EXTS and _strip_accents(f.stem).lower() == slug_ascii:
                target = f.name
                break
    if target is None:
        return None
    return f"{SITE_BASE}/concejales/fotos/{target.replace(' ', '-')}"

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


def _build_name_index() -> dict[str, str]:
    """Mapping `nombre lowercased → slug canónico` que incluye el slug,
    los aliases y los apodos de cada concejal. Permite detectar autorías
    aunque el frontmatter de la minuta use una variante del nombre.
    """
    idx: dict[str, str] = {}
    for slug in CONCEJAL_ORDER:
        path = VAULT / "personas" / f"{slug}.md"
        if not path.exists():
            idx[slug.strip().lower()] = slug
            continue
        fm = split_frontmatter(path.read_text(encoding="utf-8")) or {}
        names: list[str] = [slug]
        for variants_key in ("aliases", "apodos"):
            for v in fm.get(variants_key) or []:
                if isinstance(v, str) and v.strip():
                    names.append(v.strip())
        for n in names:
            idx[n.lower()] = slug
    return idx


def _authorship_counts() -> dict[str, dict[str, int]]:
    """Single-pass por minutas + resoluciones. Cuenta autor/secunda desde el
    frontmatter de cada documento (fuente canónica). Es la métrica honesta:
    refleja iniciativa formalmente documentada en el archivo.

    Resuelve nombres por slug, aliases o apodos.
    """
    canon = _build_name_index()
    counts: dict[str, dict[str, int]] = {
        name: {"autor": 0, "secunda": 0} for name in CONCEJAL_ORDER
    }

    for folder in ("minutas", "resoluciones"):
        folder_path = VAULT / folder
        if not folder_path.is_dir():
            continue
        for doc in folder_path.glob("*.md"):
            fm = split_frontmatter(doc.read_text(encoding="utf-8"))
            if not fm:
                continue
            autor = fm.get("autor")
            if isinstance(autor, str):
                slug = canon.get(autor.strip().lower())
                if slug:
                    counts[slug]["autor"] += 1
            secunda = fm.get("secunda")
            if isinstance(secunda, str):
                # Puede ser un único nombre o varios separados por coma.
                for piece in secunda.split(","):
                    slug = canon.get(piece.strip().lower())
                    if slug:
                        counts[slug]["secunda"] += 1
    return counts


def read_concejal(name: str, authorship: dict[str, dict[str, int]]) -> dict | None:
    """Lee una ficha de concejal y compone el dict de datos para la tarjeta.

    Asistencia y rol de mesa salen de las secciones del cuerpo de la ficha.
    Productividad legislativa (autor + secunda) viene del scan canónico de
    minutas + resoluciones — NO de las secciones del cuerpo (que están
    desactualizadas para varios concejales).
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
    pte_mesa = section_count("presidente de mesa")
    pte_sesion = section_count("presidente de sesión")

    asistencia_pct: int | None = None
    if presente + ausente > 0:
        asistencia_pct = round(100 * presente / (presente + ausente))

    ac = authorship.get(name, {"autor": 0, "secunda": 0})

    return {
        "nombre": fm.get("nombre", name),
        "slug": name,
        "titulo": fm.get("titulo", ""),
        "apodos": [a for a in (fm.get("apodos") or []) if isinstance(a, str) and a.strip()],
        "cargo": fm.get("cargo", "—"),
        "bancada": fm.get("bancada", "s/d"),
        "rasgo": fm.get("rasgo", ""),
        "votos_clave": fm.get("votos_clave") or [],
        "apariciones": fm.get("apariciones", 0),
        "presente": presente,
        "ausente": ausente,
        "asistencia_pct": asistencia_pct,
        "autor": ac["autor"],
        "secunda": ac["secunda"],
        "propuestas_total": ac["autor"] + ac["secunda"],
        "presidente_mesa": pte_mesa,
        "presidente_sesion": pte_sesion,
    }


def load_concejales() -> list[dict]:
    authorship = _authorship_counts()
    out: list[dict] = []
    for name in CONCEJAL_ORDER:
        c = read_concejal(name, authorship)
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


def _nombre_completo(c: dict) -> str:
    """Compone «Título Nombre» si hay título, sino solo nombre."""
    titulo = c.get("titulo", "").strip()
    if titulo:
        return f"{titulo} {c['slug']}"
    return c["slug"]


def _apodos_line(c: dict) -> str:
    """«Apodos: X, Y» o cadena vacía si no hay."""
    apodos = c.get("apodos") or []
    if not apodos:
        return ""
    return "Apodo" + ("s" if len(apodos) > 1 else "") + ": " + ", ".join(apodos)


def _initials(name: str) -> str:
    """Iniciales de hasta 2 palabras para el avatar de la tarjeta."""
    parts = [p for p in name.split() if p and p[0].isalpha()]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[1][0]).upper()


def build_grilla_concejales() -> str:
    """Grilla compacta de 12 tarjetas mini para el DASHBOARD."""
    concejales = load_concejales()
    out: list[str] = ['<div class="jme-concejales-grid">', ""]

    for c in concejales:
        ratio_total = c["presente"] + c["ausente"]
        asis = f'{c["asistencia_pct"]}%' if ratio_total > 0 else "—"
        ratio = f'{c["presente"]}/{ratio_total}' if ratio_total > 0 else "—"

        out.append('<div class="jme-concejal-card mini">')
        out.append("")
        out.append(f'**[[{c["slug"]}]]**')
        out.append(f'<small>{_cargo_line(c)}</small>')
        out.append("")
        out.append(f'📊 Asistencia {asis} ({ratio})  ')
        out.append(
            f'✍ Propuestas: {c["propuestas_total"]} '
            f'<small>({c["autor"]} autor · {c["secunda"]} secunda)</small>  '
        )
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
    """Tarjetas completas con header, stat tiles y votos clave en lista."""
    concejales = load_concejales()
    out: list[str] = ['<div class="jme-concejales-grid full">', ""]

    for c in concejales:
        ratio_total = c["presente"] + c["ausente"]
        asis = f'{c["asistencia_pct"]}%' if ratio_total > 0 else "—"
        ratio_sub = f'{c["presente"]}/{ratio_total}' if ratio_total > 0 else "—"

        bancada_str = "" if c["bancada"] in ("s/d", "—", "", None) else f' · {c["bancada"]}'
        titulo_prefix = (c.get("titulo", "").strip() + " ") if c.get("titulo") else ""
        meta_line = f'{titulo_prefix}{c["cargo"]}{bancada_str}'.strip()
        apodos_line = _apodos_line(c)

        votos = c["votos_clave"]
        votos_count = len(votos)

        out.append('<div class="jme-concejal-card full">')
        out.append("")
        # Header con foto (o iniciales como fallback) + identidad
        out.append('<div class="jme-concejal-header">')
        photo_url = _find_photo_url(c["slug"])
        if photo_url:
            out.append(
                f'<img class="jme-concejal-avatar" src="{photo_url}" '
                f'alt="Foto de {c["slug"]}" loading="lazy" />'
            )
        else:
            out.append(f'<div class="jme-concejal-avatar">{_initials(c["slug"])}</div>')
        out.append('<div class="jme-concejal-id">')
        out.append("")
        out.append(f'### [[{c["slug"]}]]')
        out.append(f'<div class="jme-concejal-meta">{meta_line}</div>')
        if apodos_line:
            out.append(f'<div class="jme-concejal-apodos">{apodos_line}</div>')
        out.append("")
        out.append('</div>')
        out.append('</div>')
        out.append("")

        if c["rasgo"]:
            out.append(f'> {c["rasgo"]}')
            out.append("")

        # Stat tiles
        out.append('<div class="jme-stat-row">')
        out.append("")
        out.append('<div class="jme-stat">')
        out.append(f'<div class="jme-stat-value">{asis}</div>')
        out.append(f'<div class="jme-stat-label">Asistencia<br><small>{ratio_sub}</small></div>')
        out.append('</div>')
        out.append("")
        out.append('<div class="jme-stat">')
        out.append(f'<div class="jme-stat-value">{c["propuestas_total"]}</div>')
        out.append(
            f'<div class="jme-stat-label">Propuestas<br>'
            f'<small>{c["autor"]} autor · {c["secunda"]} secunda</small></div>'
        )
        out.append('</div>')
        out.append("")
        out.append('<div class="jme-stat">')
        out.append(f'<div class="jme-stat-value">{c["presidente_mesa"]}</div>')
        out.append('<div class="jme-stat-label">Pte de mesa<br><small>plenarias</small></div>')
        out.append('</div>')
        out.append("")
        out.append('<div class="jme-stat">')
        out.append(f'<div class="jme-stat-value">{votos_count}</div>')
        out.append('<div class="jme-stat-label">Votos clave<br><small>documentados</small></div>')
        out.append('</div>')
        out.append("")
        out.append('</div>')
        out.append("")

        # Votos clave como lista vertical (más legible que tabla)
        if votos:
            out.append('<div class="jme-concejal-votos">')
            out.append("")
            out.append('**Votos clave**')
            out.append("")
            for v in votos:
                fecha = v.get("fecha", "—")
                tema = v.get("tema", "—")
                voto = v.get("voto", "—")
                acta = v.get("acta", "")
                acta_ref = f' <small>(Acta {acta})</small>' if acta else ""
                out.append(
                    f'- **{fecha}** · {tema}{acta_ref}<br>'
                    f'<span class="jme-voto">→ {voto}</span>'
                )
            out.append("")
            out.append('</div>')
            out.append("")

        # Footer link a ficha completa. Usamos <a> HTML directo (no markdown)
        # porque Quartz no procesa markdown dentro de un <div> en una sola línea.
        # Quartz convierte espacios a guiones en URLs de wiki.
        slug_url = c["slug"].replace(" ", "-")
        out.append(
            f'<div class="jme-concejal-footer">'
            f'<a href="../personas/{slug_url}">→ Ver ficha completa de {c["slug"]}</a>'
            f'</div>'
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
