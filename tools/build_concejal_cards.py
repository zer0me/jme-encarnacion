"""Generate one indexable performance card per concejal at VAULT/concejales/<slug>.md.

Each card aggregates:
- Asistencia (presente/ausente) from the persona MD section headers.
- Productividad legislativa (autor/secunda) scanning minutas + resoluciones.
- Per-tema breakdown of every doc where the concejal figures as autor or secunda.
- Votos clave from the persona FM.
- Bancada and rasgo from the persona FM. Bloque is intentionally omitted.

The cards live in the JME vault and get mirrored to content/concejales/ by
publicar.ps1. The worker build (build_docs_json.py) then indexes them so
that questions like "cuántas minutas presentó Andy" land directly on the
right doc instead of forcing the LLM to count from a truncated persona page.

Run after build_dashboard.py and before build_docs_json.py.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

VAULT = Path("G:/Mi unidad/JME")
OUT_DIR = VAULT / "concejales"

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


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None, text
    body = text[end + 4 :].lstrip("\n")
    return fm, body


def build_name_index() -> dict[str, str]:
    """Map nombre/alias/apodo (lowercased) → canonical slug."""
    idx: dict[str, str] = {}
    for slug in CONCEJAL_ORDER:
        path = VAULT / "personas" / f"{slug}.md"
        names: list[str] = [slug]
        if path.exists():
            fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
            fm = fm or {}
            for key in ("aliases", "apodos"):
                for v in fm.get(key) or []:
                    if isinstance(v, str) and v.strip():
                        names.append(v.strip())
        for n in names:
            idx[n.lower()] = slug
    return idx


def parse_secunda_field(value) -> list[str]:
    """Frontmatter `secunda` may be a string with comma-separated names, or a list."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return []


def wikilink_for(path: Path) -> str:
    """Wikilink that resolves to a doc file (filename without extension)."""
    return f"[[{path.stem}]]"


def scan_documents(canon: dict[str, str]) -> dict[str, dict]:
    """Return per-concejal aggregated data from minutas + resoluciones.

    Output schema per concejal slug:
        {
            "minuta_autor":   [(fecha, wikilink, [temas...]), ...],
            "minuta_secunda": [...],
            "resol_autor":    [...],
            "resol_secunda":  [...],
            "by_tema":        {tema: [(fecha, wikilink, tipo, rol), ...]},
        }
    """
    out: dict[str, dict] = {
        slug: {
            "minuta_autor": [],
            "minuta_secunda": [],
            "resol_autor": [],
            "resol_secunda": [],
            "by_tema": defaultdict(list),
        }
        for slug in CONCEJAL_ORDER
    }

    for folder, tipo in (("minutas", "minuta"), ("resoluciones", "resol")):
        folder_path = VAULT / folder
        if not folder_path.is_dir():
            continue
        for doc in sorted(folder_path.glob("*.md")):
            fm, _ = split_frontmatter(doc.read_text(encoding="utf-8"))
            if not fm:
                continue
            fecha = str(fm.get("fecha") or "").strip()
            temas_raw = fm.get("temas") or []
            temas = [str(t).strip() for t in temas_raw if str(t).strip()] if isinstance(temas_raw, list) else []
            link = wikilink_for(doc)
            entry = (fecha, link, temas)

            autor = fm.get("autor")
            autor_slug = canon.get(str(autor).strip().lower()) if isinstance(autor, str) else None
            if autor_slug:
                out[autor_slug][f"{tipo}_autor"].append(entry)
                for t in temas:
                    out[autor_slug]["by_tema"][t].append((fecha, link, tipo, "autor"))

            for piece in parse_secunda_field(fm.get("secunda")):
                slug = canon.get(piece.lower())
                if slug:
                    out[slug][f"{tipo}_secunda"].append(entry)
                    for t in temas:
                        out[slug]["by_tema"][t].append((fecha, link, tipo, "secunda"))

    # Sort each list newest-first
    for slug, agg in out.items():
        for key in ("minuta_autor", "minuta_secunda", "resol_autor", "resol_secunda"):
            agg[key].sort(key=lambda x: x[0], reverse=True)
    return out


def read_persona(slug: str) -> dict:
    """Pull bancada, rasgo, asistencia counts, votos_clave, apariciones, etc."""
    path = VAULT / "personas" / f"{slug}.md"
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(raw)
    fm = fm or {}

    def section_count(label: str) -> int:
        m = re.search(
            rf"^###\s+Como\s+{re.escape(label)}\s*\((\d+)\)",
            raw,
            re.MULTILINE,
        )
        return int(m.group(1)) if m else 0

    presente = section_count("presente")
    ausente = section_count("ausente")
    pct = round(100 * presente / (presente + ausente)) if (presente + ausente) > 0 else None

    # Extract first and last fecha from "Como presente" block to report range
    presente_block_match = re.search(
        r"^###\s+Como presente\s*\(\d+\)\s*\n(.*?)(?=^### |\Z)",
        raw,
        re.MULTILINE | re.DOTALL,
    )
    fechas_presente: list[str] = []
    if presente_block_match:
        fechas_presente = re.findall(r"`(\d{4}-\d{2}-\d{2})`", presente_block_match.group(1))

    return {
        "nombre": fm.get("nombre", slug),
        "titulo_pre": (fm.get("titulo") or "").strip(),
        "cargo": fm.get("cargo", "Concejal"),
        "bancada": fm.get("bancada", "s/d"),
        "rasgo": fm.get("rasgo", "") or "",
        "votos_clave": fm.get("votos_clave") or [],
        "apariciones": fm.get("apariciones", 0),
        "presente": presente,
        "ausente": ausente,
        "asistencia_pct": pct,
        "rango_fechas": (
            (min(fechas_presente), max(fechas_presente)) if fechas_presente else (None, None)
        ),
    }


DOC_LIST_LIMIT = 15
BY_TEMA_TOP = 15
BY_TEMA_DOCS_PER = 4


def render_doc_list(entries: list[tuple[str, str, list[str]]], empty_msg: str) -> str:
    """Render a list of (fecha, wikilink, [temas]) entries as bullets.

    Caps to DOC_LIST_LIMIT most recent (entries are pre-sorted newest-first).
    """
    if not entries:
        return empty_msg
    shown = entries[:DOC_LIST_LIMIT]
    rest = len(entries) - len(shown)
    lines = []
    for fecha, link, temas in shown:
        temas_part = f" · {', '.join(temas)}" if temas else ""
        lines.append(f"- {fecha} · {link}{temas_part}")
    if rest > 0:
        lines.append(
            f"- _(+ {rest} más anteriores; lista completa en la ficha de persona)_"
        )
    return "\n".join(lines)


def render_by_tema(by_tema: dict[str, list]) -> str:
    """Render per-tema breakdown: top BY_TEMA_TOP temas, up to BY_TEMA_DOCS_PER docs each."""
    if not by_tema:
        return "Sin documentos con temas tipificados."

    # Aggregate: dedup by link, keep newest entry per (tema, link).
    rows: list[tuple[str, list[tuple[str, str]]]] = []
    for tema, items in by_tema.items():
        seen: dict[str, str] = {}
        for fecha, link, _tipo, _rol in items:
            if link not in seen or fecha > seen[link]:
                seen[link] = fecha
        docs_for_tema = sorted(seen.items(), key=lambda x: x[1], reverse=True)
        rows.append((tema, [(link, fecha) for link, fecha in docs_for_tema]))

    rows.sort(key=lambda r: (-len(r[1]), r[0]))

    shown_rows = rows[:BY_TEMA_TOP]
    rest_temas = len(rows) - len(shown_rows)

    lines = []
    for tema, docs in shown_rows:
        total = len(docs)
        sample = docs[:BY_TEMA_DOCS_PER]
        sample_str = ", ".join(link for link, _ in sample)
        extra = f" (+ {total - len(sample)} más)" if total > len(sample) else ""
        lines.append(f"- **{tema}** ({total}): {sample_str}{extra}")
    if rest_temas > 0:
        lines.append(
            f"- _(+ {rest_temas} temas adicionales con menor frecuencia)_"
        )
    return "\n".join(lines)


def pluralize(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def render_votos(votos: list) -> str:
    if not votos:
        return ""
    lines = ["## Votos clave documentados", ""]
    for v in votos:
        if not isinstance(v, dict):
            continue
        fecha = v.get("fecha", "—")
        tema = v.get("tema", "—")
        voto = v.get("voto", "—")
        acta = v.get("acta", "")
        acta_ref = f" (Acta {acta})" if acta else ""
        lines.append(f"- {fecha} · {tema}{acta_ref} · voto: {voto}")
    return "\n".join(lines)


def build_card(slug: str, persona: dict, docs: dict) -> str:
    titulo_pre = persona.get("titulo_pre", "")
    nombre_full = f"{titulo_pre} {slug}".strip() if titulo_pre else slug
    cargo = persona.get("cargo", "Concejal")
    bancada = persona.get("bancada", "s/d")

    bancada_line = "" if bancada in ("s/d", "—", "", None) else f" · {bancada}"
    subtitulo = f"**{nombre_full} · {cargo}{bancada_line} · Período 2021-2026**"

    presente = persona.get("presente", 0)
    ausente = persona.get("ausente", 0)
    pct = persona.get("asistencia_pct")
    rango_min, rango_max = persona.get("rango_fechas", (None, None))
    asistencia_pct_str = f"{pct}%" if pct is not None else "s/d"
    rango_str = f"{rango_min} a {rango_max}" if rango_min and rango_max else "s/d"

    n_minuta_autor = len(docs["minuta_autor"])
    n_minuta_secunda = len(docs["minuta_secunda"])
    n_resol_autor = len(docs["resol_autor"])
    n_resol_secunda = len(docs["resol_secunda"])
    total = n_minuta_autor + n_minuta_secunda + n_resol_autor + n_resol_secunda

    today = date.today().isoformat()

    front = (
        "---\n"
        f'titulo: "{slug} — Tarjeta de desempeño Concejal JM 2021-2026"\n'
        "tipo: tarjeta-concejal\n"
        f'concejal: "{slug}"\n'
        f"bancada: {bancada}\n"
        "period: 2021-2026\n"
        f"fecha_actualizacion: {today}\n"
        "---\n"
    )

    parts = [
        front,
        f"# {slug} — Tarjeta de desempeño",
        "",
        subtitulo,
        "",
        "## Resumen cuantitativo",
        f"- Asistencia: presente en **{presente} sesiones plenarias** "
        f"({asistencia_pct_str}); ausente en **{ausente}**. Rango: {rango_str}.",
        f"- Productividad legislativa: "
        f"**{n_minuta_autor} {pluralize(n_minuta_autor, 'minuta', 'minutas')} como autor · "
        f"{n_minuta_secunda} {pluralize(n_minuta_secunda, 'minuta', 'minutas')} como secunda · "
        f"{n_resol_autor} {pluralize(n_resol_autor, 'resolución', 'resoluciones')} como autor · "
        f"{n_resol_secunda} {pluralize(n_resol_secunda, 'resolución', 'resoluciones')} como secunda**. "
        f"Total propuestas con su firma: **{total}**.",
        "",
        "## Documentos por tema (autor + secunda, minutas + resoluciones)",
        render_by_tema(docs["by_tema"]),
        "",
        "## Resoluciones",
        "",
        f"### Como autor ({n_resol_autor})",
        render_doc_list(
            docs["resol_autor"],
            f"{slug} no figura como autor de ninguna resolución entre 2021 y 2025.",
        ),
        "",
        f"### Como secunda ({n_resol_secunda})",
        render_doc_list(
            docs["resol_secunda"],
            f"{slug} no figura como secunda de ninguna resolución entre 2021 y 2025.",
        ),
        "",
    ]

    votos_block = render_votos(persona.get("votos_clave", []))
    if votos_block:
        parts.append(votos_block)
        parts.append("")

    parts += [
        "## Minutas",
        "",
        f"### Como autor principal ({n_minuta_autor})",
        render_doc_list(
            docs["minuta_autor"],
            f"{slug} no figura como autor principal de ninguna minuta entre 2021 y 2025.",
        ),
        "",
        f"### Como secunda / co-firmante ({n_minuta_secunda})",
        render_doc_list(
            docs["minuta_secunda"],
            f"{slug} no figura como co-firmante de ninguna minuta entre 2021 y 2025.",
        ),
        "",
    ]

    rasgo = persona.get("rasgo", "").strip()
    if rasgo:
        parts.append("## Rasgo político (observado en el archivo)")
        parts.append(rasgo)
        parts.append("")

    return "\n".join(parts)


def main() -> int:
    if not VAULT.exists():
        print(f"ERROR: vault {VAULT} no existe.", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(exist_ok=True)

    canon = build_name_index()
    docs_per_slug = scan_documents(canon)

    written = 0
    for slug in CONCEJAL_ORDER:
        persona = read_persona(slug)
        if not persona:
            print(f"  WARN: ficha persona '{slug}' no encontrada — skip", file=sys.stderr)
            continue
        card_md = build_card(slug, persona, docs_per_slug[slug])
        out_path = OUT_DIR / f"{slug}.md"
        out_path.write_text(card_md, encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"  {slug:30s} -> {out_path.name} ({size_kb:.1f} KB)")
        written += 1

    print(f"\nOK — {written}/{len(CONCEJAL_ORDER)} cards escritas en {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
