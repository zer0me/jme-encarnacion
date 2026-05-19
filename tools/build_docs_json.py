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
    "concejales",
    "dictamenes",
]

MAX_TEXT_CHARS = 6500
# Per-chunk budget for already-chunked normativa entries. Larger than the
# legacy default because Capítulo-level chunks are coherent legal sections
# and bge-m3 has 8192-token context (~24K chars). 14000c keeps us under
# half the model budget with plenty of headroom for the prepended title scope.
NORMATIVA_CHUNK_MAX_CHARS = 14000


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
    # Collapse multiple blank lines + remove HTML comments + strip image embeds
    # (markdown ![alt](src) and Obsidian ![[file]]) so embeddings see prose only.
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"!\[\[[^\]]+\]\]", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


TITULO_HEADING_RE = re.compile(r"^## (TÍTULO[^\n]+)$", re.MULTILINE)
CAPITULO_HEADING_RE = re.compile(r"^### (Capítulo[^\n]+)$", re.MULTILINE)
SECCION_HEADING_RE = re.compile(r"^#### (Sección[^\n]+)$", re.MULTILINE)


def chunk_long_normativa(body: str, base_titulo: str) -> list[tuple[str, str, str]]:
    """Split a long structured law body into per-Sección (or per-Capítulo) chunks.

    Returns a list of (suffix, chunk_titulo, chunk_text) tuples. The suffix is a
    short slug appended to the doc path to keep entries unique. chunk_titulo is
    the human-readable scoped title shown in citations. chunk_text is the body
    fragment, with the parent Título/Capítulo prepended so embeddings have orientation.

    Splits at the deepest available level: Sección > Capítulo > Título. Returns
    [] if the body has fewer than 2 Capítulos (caller falls back to single-doc).
    """
    if len(CAPITULO_HEADING_RE.findall(body)) < 2:
        return []

    lines = body.split("\n")
    cur_titulo = ""
    cur_cap = ""
    cur_sec = ""
    buf: list[str] = []
    chunks: list[tuple[str, str, str]] = []

    def flush():
        if not buf or not (cur_cap or cur_titulo or cur_sec):
            return
        if not any(ln.strip() for ln in buf):
            return  # skip empty chunks (heading-only blocks)
        scope_parts = [base_titulo]
        if cur_titulo:
            scope_parts.append(cur_titulo)
        if cur_cap:
            scope_parts.append(cur_cap)
        if cur_sec:
            scope_parts.append(cur_sec)
        chunk_title = " — ".join(scope_parts)

        header_lines = []
        if cur_titulo:
            header_lines.append(f"## {cur_titulo}")
        if cur_cap:
            header_lines.append(f"### {cur_cap}")
        if cur_sec:
            header_lines.append(f"#### {cur_sec}")
        body_text = "\n".join(header_lines + buf).strip()

        # Slug from deepest scope.
        slug_src = cur_sec or cur_cap or cur_titulo
        slug = re.sub(r"[^a-z0-9]+", "-", slug_src.lower()).strip("-")[:80]
        chunks.append((slug, chunk_title, body_text))

    for ln in lines:
        m_tit = TITULO_HEADING_RE.match(ln)
        m_cap = CAPITULO_HEADING_RE.match(ln)
        m_sec = SECCION_HEADING_RE.match(ln)
        if m_tit:
            flush()
            buf = []
            cur_titulo = m_tit.group(1).strip()
            cur_cap = ""
            cur_sec = ""
        elif m_cap:
            flush()
            buf = []
            cur_cap = m_cap.group(1).strip()
            cur_sec = ""
        elif m_sec:
            flush()
            buf = []
            cur_sec = m_sec.group(1).strip()
        else:
            buf.append(ln)
    flush()

    # Sub-split any chunk still too big by article ranges (for Capítulos with no Secciones).
    ARTICULO_RE = re.compile(r"^##### Artículo (\d+)\.-", re.MULTILINE)
    expanded: list[tuple[str, str, str]] = []
    for slug, title, txt in chunks:
        if len(txt) <= NORMATIVA_CHUNK_MAX_CHARS:
            expanded.append((slug, title, txt))
            continue
        # Split on article boundaries into pieces ≤ NORMATIVA_CHUNK_MAX_CHARS.
        art_starts = [m.start() for m in ARTICULO_RE.finditer(txt)]
        if len(art_starts) < 2:
            expanded.append((slug, title, txt))
            continue
        # Preserve the chunk header (everything before the first Artículo).
        header = txt[: art_starts[0]].rstrip()
        boundaries = art_starts + [len(txt)]
        sub_buf = header
        sub_start_art = None
        sub_end_art = None
        sub_idx = 1

        def emit_sub(buf_text, start_n, end_n, idx):
            sub_slug = f"{slug}-arts-{start_n}-{end_n}"
            sub_title = f"{title} (arts. {start_n}-{end_n})"
            expanded.append((sub_slug, sub_title, buf_text.strip()))

        for k in range(len(boundaries) - 1):
            art_text = txt[boundaries[k]:boundaries[k + 1]]
            art_n = int(ARTICULO_RE.match(art_text).group(1))
            if sub_start_art is None:
                sub_start_art = art_n
            # Would adding this article overflow the budget?
            candidate = (sub_buf + "\n\n" + art_text).strip()
            if len(candidate) > NORMATIVA_CHUNK_MAX_CHARS and sub_end_art is not None:
                emit_sub(sub_buf, sub_start_art, sub_end_art, sub_idx)
                sub_idx += 1
                sub_buf = header + "\n\n" + art_text
                sub_start_art = art_n
                sub_end_art = art_n
            else:
                sub_buf = candidate
                sub_end_art = art_n
        if sub_start_art is not None:
            emit_sub(sub_buf, sub_start_art, sub_end_art, sub_idx)

    # Deduplicate slugs (e.g. "secci-n-1" appears in multiple Capítulos).
    seen: dict[str, int] = {}
    out: list[tuple[str, str, str]] = []
    for slug, t, txt in expanded:
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        suffix = slug if n == 0 else f"{slug}-{n + 1}"
        out.append((suffix, t, txt))
    return out


def build_doc_entries(path: Path) -> list[dict]:
    """Return one or more doc entries for a markdown file.

    Long structured normativa files are split into per-Capítulo chunks so each
    section is independently retrievable. Everything else uses the legacy
    single-entry / truncate-to-MAX path.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[skip] {path.name}: {e}", file=sys.stderr)
        return []

    fm, body = split_frontmatter(text)
    fm = fm or {}

    titulo = fm.get("titulo") or fm.get("title") or path.stem
    tipo = fm.get("tipo") or path.parent.name.rstrip("s")
    fecha = fm.get("fecha") or fm.get("fecha_sesion") or ""

    body = strip_md_noise(body)
    summary = summarize_frontmatter(fm)
    base_path = slugify_path(path)

    # Chunking branch: long normativa with ### Capítulo structure.
    is_normativa = path.parent.name == "normativa" or "normativa" in path.parts
    if is_normativa and len(body) > MAX_TEXT_CHARS:
        chunks = chunk_long_normativa(body, str(titulo))
        if chunks:
            entries: list[dict] = []
            # First entry: the prelude (frontmatter summary + everything before the first ## TÍTULO).
            prelude_end = body.find("\n## TÍTULO")
            prelude_body = body[:prelude_end].strip() if prelude_end > 0 else ""
            prelude_parts = []
            if summary:
                prelude_parts.append(summary)
            if prelude_body:
                prelude_parts.append(prelude_body)
            prelude_text = "\n\n".join(prelude_parts).strip()
            if len(prelude_text) > MAX_TEXT_CHARS:
                prelude_text = prelude_text[:MAX_TEXT_CHARS] + "\n[...truncado...]"
            if prelude_text:
                entries.append({
                    "path": f"{base_path}#prelude",
                    "titulo": f"{titulo} — Índice y variantes",
                    "tipo": str(tipo),
                    "fecha": str(fecha) if fecha else None,
                    "url": base_path,
                    "text": prelude_text,
                })
            # Per-Capítulo entries.
            for suffix, chunk_title, chunk_text in chunks:
                if len(chunk_text) > NORMATIVA_CHUNK_MAX_CHARS:
                    chunk_text = chunk_text[:NORMATIVA_CHUNK_MAX_CHARS] + "\n[...truncado...]"
                entries.append({
                    "path": f"{base_path}#{suffix}",
                    "titulo": chunk_title,
                    "tipo": str(tipo),
                    "fecha": str(fecha) if fecha else None,
                    "url": base_path,
                    "text": chunk_text,
                })
            return entries

    # Default branch: single entry, truncated.
    parts = []
    if summary:
        parts.append(summary)
    if body:
        parts.append(body)
    combined = "\n\n".join(parts)
    if len(combined) > MAX_TEXT_CHARS:
        combined = combined[:MAX_TEXT_CHARS] + "\n[...truncado...]"

    return [{
        "path": base_path,
        "titulo": str(titulo),
        "tipo": str(tipo),
        "fecha": str(fecha) if fecha else None,
        "url": base_path,
        "text": combined,
    }]


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
            for entry in build_doc_entries(md):
                if entry["text"].strip():
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
