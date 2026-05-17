"""Extract docs from content/ into worker-preguntar/data/docs.json.

Each doc entry:
    {
        "path": "actas/2025-01-22 - Acta 155-2025 (...)",
        "titulo": "Acta de la Sesión Ordinaria N° 155/2025 — ...",
        "tipo": "acta",
        "fecha": "2025-01-22",
        "url": "actas/2025-01-22-acta-155-2025...",
        "text": "<frontmatter-summary>\n\n<first ~4000 chars of body>"
    }

The "text" field is what gets embedded and shown to the LLM as context.
We include a structured summary derived from frontmatter (titulo, fecha,
asistentes, votaciones, temas) plus the first chunk of the markdown body.
This gives the embedding model a high-signal representation even for actas
that are tens of KB long (we only embed the first ~2000 chars effectively
due to bge-base 512-token context).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path("C:/Users/Alejandro/projects/jme-encarnacion")
CONTENT = REPO / "content"
OUT = REPO / "worker-preguntar" / "data" / "docs.json"

INCLUDE_FOLDERS = [
    "actas",
    "minutas",
    "resoluciones",
    "informe-gestion",
    "informe-2024",
    "presupuesto",
    "personas",
    "instituciones",
    "empresas",
    "normativa",
    "temas",
    "lugares",
]

MAX_TEXT_CHARS = 4000


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


def slugify_path(path: Path) -> str:
    rel = path.relative_to(CONTENT).with_suffix("")
    return str(rel).replace("\\", "/")


def _humanize_slug(s: str) -> str:
    return str(s).replace("-", " ").replace("_", " ")


def summarize_frontmatter(fm: dict) -> str:
    """Prose-style summary optimized for embedding retrieval.

    Uses natural sentences instead of YAML-style keys, so the embedding model
    sees coherent language. Front-loads the most discriminating signal
    (titulo + numero + fecha + temas) in the first ~200 chars.
    """
    if not fm:
        return ""

    titulo = fm.get("titulo") or fm.get("title") or ""
    tipo = fm.get("tipo") or ""
    numero = fm.get("numero") or ""
    fecha = fm.get("fecha") or fm.get("fecha_sesion") or ""

    parts = []

    # Punchy first line: titulo (already includes type/number) + fecha
    header_bits = []
    if titulo:
        header_bits.append(str(titulo))
    if fecha and str(fecha) not in str(titulo):
        header_bits.append(f"Fecha: {fecha}")
    if header_bits:
        parts.append(" — ".join(header_bits) + ".")

    # Temas as natural prose
    temas = fm.get("temas")
    if isinstance(temas, list) and temas:
        humanized = [_humanize_slug(t) for t in temas]
        parts.append("Temas tratados: " + ", ".join(humanized) + ".")

    # Votaciones as prose
    votaciones = fm.get("votaciones_clave") or fm.get("votaciones")
    if isinstance(votaciones, list) and votaciones:
        v_strs = []
        for v in votaciones[:8]:
            if isinstance(v, dict):
                t = v.get("tema") or v.get("descripcion") or ""
                r = v.get("resultado") or ""
                if t:
                    v_strs.append(f"{t}{f' ({r})' if r else ''}")
        if v_strs:
            parts.append("Votaciones clave: " + "; ".join(v_strs) + ".")

    # Minutas tratadas as prose
    minutas = fm.get("minutas_tratadas")
    if isinstance(minutas, list) and minutas:
        m_strs = []
        for m in minutas[:6]:
            if isinstance(m, dict):
                t = m.get("tema") or ""
                if t:
                    m_strs.append(t)
        if m_strs:
            parts.append("Minutas tratadas: " + "; ".join(m_strs) + ".")

    # Concejales (less discriminating, put late)
    presentes = fm.get("concejales_presentes")
    if isinstance(presentes, list) and presentes:
        parts.append("Concejales presentes: " + ", ".join(str(p) for p in presentes) + ".")
    ausentes = fm.get("concejales_ausentes")
    if isinstance(ausentes, list) and ausentes:
        parts.append("Concejales ausentes: " + ", ".join(str(p) for p in ausentes) + ".")

    return "\n\n".join(parts)


def strip_md_noise(body: str) -> str:
    # Collapse multiple blank lines + remove HTML comments + strip wikilink decorations
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def build_doc_entry(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[skip] {path.name}: {e}", file=sys.stderr)
        return None

    fm, body = split_frontmatter(text)
    fm = fm or {}

    titulo = fm.get("titulo") or fm.get("title") or path.stem
    tipo = fm.get("tipo") or path.parent.name.rstrip("s")
    fecha = fm.get("fecha") or fm.get("fecha_sesion") or ""

    body = strip_md_noise(body)
    summary = summarize_frontmatter(fm)
    parts = []
    if summary:
        parts.append(summary)
    if body:
        parts.append(body)
    combined = "\n\n".join(parts)
    if len(combined) > MAX_TEXT_CHARS:
        combined = combined[:MAX_TEXT_CHARS] + "\n[...truncado...]"

    return {
        "path": slugify_path(path),
        "titulo": str(titulo),
        "tipo": str(tipo),
        "fecha": str(fecha) if fecha else None,
        "url": slugify_path(path),
        "text": combined,
    }


def main() -> int:
    if not CONTENT.exists():
        print(f"No existe {CONTENT}", file=sys.stderr)
        return 1

    docs = []
    for folder in INCLUDE_FOLDERS:
        d = CONTENT / folder
        if not d.exists():
            continue
        for md in sorted(d.rglob("*.md")):
            entry = build_doc_entry(md)
            if entry and entry["text"].strip():
                docs.append(entry)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(docs, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    total_chars = sum(len(d["text"]) for d in docs)
    print(f"OK - {len(docs)} docs -> {OUT}")
    print(f"     {total_chars / 1024:.1f} KB de texto total")
    print(f"     archivo: {OUT.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
