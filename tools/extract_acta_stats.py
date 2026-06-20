"""Extract per-concejal statistics from the 177 actas frontmatter.

The actas carry the richest structured signal of the whole corpus:

    concejales_presentes:  [nombres...]      # 177/177 actas
    concejales_ausentes:   [nombres...]
    votaciones:            [{tema, resultado, a_favor, en_contra, abstenciones}, ...]
    intervenciones:        [{concejal, tema, postura}, ...]   # 172/177 actas

`build_concejal_cards.py` historically derived asistencia from the persona-page
section headers (`### Como presente (N)`), which were themselves hand-maintained
and lagged the actas. This module recomputes asistencia directly from every acta
(authoritative), tallies intervenciones per concejal, and best-effort attributes
documented dissent (votos en contra / abstenciones that name a concejal).

Two roles:
  * imported: `scan_actas(canon, slugs)` returns the aggregates for card building.
  * standalone: `python tools/extract_acta_stats.py` prints a validation report.

Run before build_concejal_cards.py (which imports scan_actas).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

VAULT = Path("G:/Mi unidad/JME")
ACTAS_DIR = VAULT / "actas"


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


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    """Lowercase + strip accents for forgiving comparison."""
    return _strip_accents(str(s)).lower().strip()


def _name_of(raw):
    """An acta entry may be a plain name string or a dict {nombre, motivo}."""
    if isinstance(raw, dict):
        return str(raw.get("nombre") or "").strip(), str(raw.get("motivo") or "").strip()
    return str(raw or "").strip(), ""


def _canonize_name(raw, canon: dict[str, str], tokens: dict[str, str] | None = None) -> str | None:
    """Map a name as written in an acta to a canonical slug, or None.

    Tries exact (lowercased) → accent-insensitive full match → surname-token
    fallback (e.g. "Marino Fernández" → "Carlos Marino Fernández").
    """
    key, _ = _name_of(raw)
    if not key:
        return None
    # exact (lowercased) first
    slug = canon.get(key.lower())
    if slug:
        return slug
    # accent-insensitive full match
    n = _norm(key)
    for name, s in canon.items():
        if _norm(name) == n:
            return s
    # surname-token fallback
    if tokens:
        if n in tokens:
            return tokens[n]
        parts = key.split()
        if len(parts) >= 2 and _norm(" ".join(parts[-2:])) in tokens:
            return tokens[_norm(" ".join(parts[-2:]))]
        if parts and _norm(parts[-1]) in tokens:
            return tokens[_norm(parts[-1])]
        # subset-token fallback: handles full legal names in roll-calls, e.g.
        # "Nehemías Cuevas Trinidad" → "Nehemías Cuevas", "Diego Rafael Aquino
        # Mercado" → "Diego Aquino". Match when every word of a canonical slug
        # appears in the input (the 12 slugs are pairwise distinct on this test).
        words = {_norm(w) for w in parts}
        for slug in set(tokens.values()):
            slug_words = {_norm(w) for w in slug.split()}
            if slug_words and slug_words <= words:
                return slug
    return None


def build_dissent_tokens(slugs: list[str], canon: dict[str, str]) -> dict[str, str]:
    """Map a lowercased match-token (surname, full name, alias) -> slug.

    Used to attribute free-text dissent like `en_contra: "2 (Morel, Florentín)"`
    or `abstenciones: ["Eduardo Florentín", ...]`. The 12 concejales have unique
    surnames, so the last name token is a safe key.
    """
    tokens: dict[str, str] = {}
    # canon already maps full names + aliases -> slug
    for name, slug in canon.items():
        tokens[_norm(name)] = slug
    for slug in slugs:
        parts = slug.split()
        # last token (surname) and last two tokens
        if parts:
            tokens.setdefault(_norm(parts[-1]), slug)
        if len(parts) >= 2:
            tokens.setdefault(_norm(" ".join(parts[-2:])), slug)
    return tokens


def names_in_vote_field(value, dissent_tokens: dict[str, str]) -> set[str]:
    """Extract the set of concejal slugs named inside a votacion field.

    Handles: YAML list of names, or a free-text string with names (often in
    parentheses). Returns empty set when the field is just a count / null.
    """
    found: set[str] = set()
    if value is None:
        return found
    if isinstance(value, list):
        for item in value:
            slug = None
            n = _norm(item)
            slug = dissent_tokens.get(n)
            if not slug:
                # try last token of the item
                parts = str(item).split()
                if parts:
                    slug = dissent_tokens.get(_norm(parts[-1]))
            if slug:
                found.add(slug)
        return found
    if isinstance(value, (int, float)):
        return found
    # string: only attribute if it actually contains letters (names), not just a count
    text = str(value)
    if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", text):
        return found
    text_norm = _norm(text)
    # match each token as a whole word (token may be multi-word)
    for token, slug in dissent_tokens.items():
        if len(token) < 4:  # avoid spurious short tokens
            continue
        if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", text_norm):
            found.add(slug)
    return found


_MINUTA_HEADING = re.compile(r"^##[^\n]*[Mm]inutas[^\n]*$", re.MULTILINE)
# Un ítem de minuta empieza de 3 formas según la época de curación del acta:
#   "**N)"            (2024-2026)
#   "### Minuta N — " (formato granular 2022-2023, H3)
#   "**Minuta N**"    (formato granular 2022-2023, negrita)
# Los tres se cuentan. Los dos últimos son "heading-style" (autores en el encabezado).
_MINUTA_ITEM = re.compile(
    r"(?=^(?:\*\*\d+\)|\*\*[Mm]inuta|###\s+\d+\)|###\s+[Mm]inuta|\d+[.)]\s))",
    re.MULTILINE,
)
# "heading-style" = autores en el encabezado ("### Minuta N (A / B)", "**Minuta N** (A/B)").
_MINUTA_D_HEADING = re.compile(r"^(?:###\s+|\*\*)[Mm]inuta\b", re.IGNORECASE)
# "attribution-style" = autor en la 1ª atribución "**[[X]] propuso**" del cuerpo
# ("**N)", "### N) Título", "N. ", "N) ").
_MINUTA_A_START = re.compile(r"^(?:\*\*\d+\)|###\s+\d+\)|\d+[.)]\s)")
_BOLD_SPAN = re.compile(r"\*\*([^*]+)\*\*")
_PROPOSE_VERB = re.compile(r"\b(propus\w*|present[oó]\w*|presentaron|mocion\w*)\b", re.IGNORECASE)
# Verbos de proposición para el fallback por atribución (incluye "planteó"); excluye
# verbos de debate (opinó/expresó/aportó/aclaró/respondió/solicitó).
_ATTRIB_VERB = re.compile(r"\b(propus\w*|present[oó]\w*|presentaron|plante[oó]|mocion\w*)", re.IGNORECASE)
# Verbos de proposición buscados DENTRO de una atribución en negrita "**[[X]] verbo**"
# (incluye solicitó/planteó; seguro porque solo se evalúa dentro del span en negrita,
# no en títulos ni petición).
_BOLD_PROPOSE = re.compile(r"(propus|present[oó]|presentaron|plante[oó]|mocion|solicit)", re.IGNORECASE)
# Una minuta es "proyecto de ordenanza" (iniciativa con impacto normativo) si su texto
# contiene esta frase. Distingue las ordenanzas de menciones, pedidos de informe, etc.
_ORDENANZA = re.compile(r"proyecto de (?:ordenanza|modificaci[oó]n\b)", re.IGNORECASE)
_SECUNDADO = re.compile(r"secundad[oa]s?\s+por\s+([^).]*)", re.IGNORECASE)
_WIKILINK = re.compile(r"\[\[([^\]|]+)")


def _wikilink_slugs(text: str, canon: dict[str, str], tokens: dict[str, str]) -> list[str]:
    """Canonical concejal slugs for every [[wikilink]] found in `text` (deduped, in order)."""
    seen: list[str] = []
    for raw in _WIKILINK.findall(text):
        slug = _canonize_name(raw, canon, tokens)
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def _minuta_desc(item: str) -> str:
    """Compact one-line description of a minuta item: just the petición.

    Strips the leading "Proposer(s) propuso (secundado por X)" so the snippet is
    the substance (the card already says whose minuta it is by its section).
    """
    s = re.sub(r"^###\s+[Mm]inuta\s+\d*\s*[—–-]?\s*", "", item.strip())  # "### Minuta N —"
    s = re.sub(r"^\*\*[Mm]inuta\s+\d*\*\*\s*", "", s)  # "**Minuta N**"
    s = re.sub(r"^\*\*\d+\)\s*", "", s)  # "**N)"
    s = s.replace("**", "")
    s = re.sub(r"\s+", " ", s).strip()
    m = _PROPOSE_VERB.search(s)
    if m:
        rest = s[m.end():].lstrip()
        rest = re.sub(r"^\(secundad[oa]s?\s+por[^)]*\)\s*", "", rest, flags=re.IGNORECASE).lstrip()
        if len(rest) > 15:
            s = rest
    cut = s.find(". ", 40)
    if cut == -1 or cut > 180:
        cut = 180
    return s[:cut].rstrip(" .,;:")


def _dedup_minutas(entries: list[tuple]) -> list[tuple]:
    """Drop duplicate minutas (same petición re-presentada en otra sesión).

    Dedup por descripción completa; conserva la primera ocurrencia (la lista llega
    ordenada newest-first, así que se queda la más reciente).
    """
    seen: set[str] = set()
    out: list[tuple] = []
    for fecha, acta_stem, desc in entries:
        key = re.sub(r"\s+", " ", desc).strip().lower()
        if key and key in seen:
            continue
        seen.add(key)
        out.append((fecha, acta_stem, desc))
    return out


def _split_by_slash(segment: str, canon: dict[str, str], tokens: dict[str, str]) -> tuple[list[str], list[str]]:
    """Separar proponentes: convención "[[Autor]] / [[Secunda]]" del archivo JME.

    Los nombres antes del primer "/" son autores (co-autores si van con ","/"y");
    los que siguen al "/" son secundantes. Sin "/", todos son autores.
    """
    parts = segment.split("/")
    autor = _wikilink_slugs(parts[0], canon, tokens)
    secunda: list[str] = []
    for p in parts[1:]:
        secunda += _wikilink_slugs(p, canon, tokens)
    secunda = [s for s in dict.fromkeys(secunda) if s not in autor]
    return autor, secunda


def parse_acta_minutas(
    body: str,
    fecha: str,
    acta_stem: str,
    canon: dict[str, str],
    tokens: dict[str, str],
    out: dict[str, dict],
) -> None:
    """Attribute each minuta item in an acta body to its proposer(s) and seconder(s).

    Minutas live in the acta body under a `## ... Minutas` heading as numbered items
    `**N) [[Proposer]] propuso** (secundado por [[X]]) ...`. The standalone `minutas/`
    folder is radically incomplete, so the actas are the authoritative source for who
    presented what. Appends (fecha, acta_stem, desc) to out[slug]["minuta_autor"/"_secunda"].
    """
    for hm in _MINUTA_HEADING.finditer(body):
        start = hm.end()
        nxt = re.search(r"^## ", body[start:], re.MULTILINE)
        section = body[start : start + nxt.start()] if nxt else body[start:]
        matched = 0
        for item in _MINUTA_ITEM.split(section):
            st = item.strip()
            is_d = bool(_MINUTA_D_HEADING.match(st))
            if not is_d and not _MINUTA_A_START.match(st):
                continue
            matched += 1
            # 1. Segmento donde figuran los proponentes.
            if is_d:
                # Heading-style ("### Minuta N — Título (autor / secunda)" o
                # "**Minuta N** (autor / secunda): petición"): nombres en el encabezado
                # (cortado en ":" para no tomar nombres de la petición), o en la 1ª
                # atribución en negrita CON wikilink si el encabezado no los tiene
                # (p.ej. encabezado con nombres en texto plano + cuerpo "**[[X]] propuso**").
                heading = item.split("\n", 1)[0].split(":", 1)[0]
                seg = heading
                if not _WIKILINK.search(heading):
                    seg = heading
                    for mb in _BOLD_SPAN.finditer(item):
                        if _WIKILINK.search(mb.group(1)):
                            seg = mb.group(1)
                            break
            else:
                # Attribution-style ("**N)", "### N) Título", "N. ", "N) "): el proponente
                # es la 1ª negrita "**[[X]] <verbo>**" (propuso/presentó/planteó/solicitó/
                # mocionó). Usar la negrita (no los 110 chars) evita capturar concejales
                # mencionados en la petición.
                seg = ""
                for mb in _BOLD_SPAN.finditer(item):
                    span = mb.group(1)
                    if _WIKILINK.search(span) and _BOLD_PROPOSE.search(span):
                        seg = span
                        break
                if not seg:
                    # Fallback formato B "Minuta [[A]] / [[B]] — Título: **[[C]] opinó**"
                    # (proponentes antes del guión, sin verbo proponente propio).
                    vm = _PROPOSE_VERB.search(item)
                    dm = re.search(r"[—–]", item)
                    seg = item[: vm.start()] if vm else item[:110]
                    if dm and (vm is None or dm.start() < vm.start()):
                        hd = item[: dm.start()]
                        if _WIKILINK.search(hd):
                            seg = hd
            # 2. "[[A]] / [[B]]" = autor (antes del 1er "/") / secunda (después).
            #    Sin "/" → todos co-autores ("[[A]], [[B]] y [[C]] propusieron").
            autor_seg, secunda_slash = _split_by_slash(seg, canon, tokens)
            # 3. secunda explícito "(secundado por …)".
            sm = _SECUNDADO.search(item)
            secunda_clause = _wikilink_slugs(sm.group(1), canon, tokens) if sm else []
            # El autor NUNCA es alguien marcado como secunda. Esto corrige los ítems con
            # verbos no listados ("planteó", "solicitó") donde el segmento llegaba a
            # incluir la cláusula "(secundada por X)" y contaba a X como falso co-autor.
            secunda_slugs = list(dict.fromkeys(secunda_slash + secunda_clause))
            autor_slugs = [s for s in autor_seg if s not in secunda_slugs]
            desc = _minuta_desc(item)
            is_ord = bool(_ORDENANZA.search(item))
            for s in autor_slugs:
                if s in out:
                    out[s]["minuta_autor"].append((fecha, acta_stem, desc))
                    if is_ord:
                        out[s]["ordenanza_autor"].append((fecha, acta_stem, desc))
            for s in secunda_slugs:
                if s in out:
                    out[s]["minuta_secunda"].append((fecha, acta_stem, desc))
                    if is_ord:
                        out[s]["ordenanza_secunda"].append((fecha, acta_stem, desc))

        # Fallback sin marcadores: secciones que listan minutas como párrafos
        # "**[[X]] propuso:** petición" sin numeración ni "### Minuta". Solo si la
        # sección no tuvo NINGÚN ítem con marcador (para no duplicar ni meter debate).
        if matched == 0:
            for mb in _BOLD_SPAN.finditer(section):
                span = mb.group(1)
                if not _ATTRIB_VERB.search(span):
                    continue
                autor_slugs = _wikilink_slugs(span, canon, tokens)
                if not autor_slugs:
                    continue
                tail = span + section[mb.end() : mb.end() + 120]
                sm = _SECUNDADO.search(tail)
                secunda_slugs = (
                    [s for s in _wikilink_slugs(sm.group(1), canon, tokens) if s not in autor_slugs]
                    if sm else []
                )
                desc = _minuta_desc(span)
                is_ord = bool(_ORDENANZA.search(span + section[mb.end() : mb.end() + 200]))
                for s in autor_slugs:
                    if s in out:
                        out[s]["minuta_autor"].append((fecha, acta_stem, desc))
                        if is_ord:
                            out[s]["ordenanza_autor"].append((fecha, acta_stem, desc))
                for s in secunda_slugs:
                    if s in out:
                        out[s]["minuta_secunda"].append((fecha, acta_stem, desc))
                        if is_ord:
                            out[s]["ordenanza_secunda"].append((fecha, acta_stem, desc))


def scan_actas(canon: dict[str, str], slugs: list[str]) -> dict[str, dict]:
    """Return per-slug aggregates from every acta in the vault.

    Per slug:
        presente:           int
        ausente:            int
        sesiones_conocidas: int   (presente + ausente)
        asistencia_pct:     int | None
        fechas_presente:    [str]
        fechas_ausente:     [str]
        intervenciones:     [(fecha, acta_num, tema, postura)]
        n_intervenciones:   int
        temas_intervenidos: Counter(tema -> n)
        votos_en_contra:    [(fecha, acta_num, tema, resultado)]
        abstenciones:       [(fecha, acta_num, tema, resultado)]
    """
    out: dict[str, dict] = {
        slug: {
            "presente": 0,
            "ausente": 0,
            "fechas_presente": [],
            "fechas_ausente": [],
            "intervenciones": [],
            "temas_intervenidos": Counter(),
            "votos_en_contra": [],
            "abstenciones": [],
            "ausente_con_aviso": 0,
            "minuta_autor": [],
            "minuta_secunda": [],
            "ordenanza_autor": [],
            "ordenanza_secunda": [],
        }
        for slug in slugs
    }
    dissent_tokens = build_dissent_tokens(slugs, canon)

    n_actas = 0
    unmatched_present: Counter = Counter()
    unmatched_interv: Counter = Counter()

    for doc in sorted(ACTAS_DIR.glob("*.md")):
        fm, body = split_frontmatter(doc.read_text(encoding="utf-8"))
        if not fm:
            continue
        n_actas += 1
        fecha = str(fm.get("fecha") or fm.get("fecha_sesion") or "").strip()
        acta_num = str(fm.get("numero") or doc.stem).strip()

        # --- Minutas presentadas en sesión (parseadas del cuerpo del acta) ---
        parse_acta_minutas(body, fecha, doc.stem, canon, dissent_tokens, out)

        # --- Asistencia ---
        for raw in fm.get("concejales_presentes") or []:
            slug = _canonize_name(raw, canon, dissent_tokens)
            if slug and slug in out:
                out[slug]["presente"] += 1
                out[slug]["fechas_presente"].append(fecha)
            else:
                name, _ = _name_of(raw)
                if name:
                    unmatched_present[name] += 1
        for raw in fm.get("concejales_ausentes") or []:
            slug = _canonize_name(raw, canon, dissent_tokens)
            name, motivo = _name_of(raw)
            if slug and slug in out:
                out[slug]["ausente"] += 1
                out[slug]["fechas_ausente"].append(fecha)
                if "aviso" in motivo.lower() or "justific" in motivo.lower():
                    out[slug]["ausente_con_aviso"] += 1
            elif name:
                unmatched_present[name] += 1

        # --- Intervenciones ---
        for it in fm.get("intervenciones") or []:
            if not isinstance(it, dict):
                continue
            slug = _canonize_name(it.get("concejal"), canon, dissent_tokens)
            tema = str(it.get("tema") or "").strip()
            postura = str(it.get("postura") or "").strip()
            if slug and slug in out:
                out[slug]["intervenciones"].append((fecha, acta_num, tema, postura))
                if tema:
                    out[slug]["temas_intervenidos"][tema] += 1
            elif it.get("concejal"):
                unmatched_interv[str(it.get("concejal")).strip()] += 1

        # --- Votaciones: documented dissent ---
        for v in fm.get("votaciones") or []:
            if not isinstance(v, dict):
                continue
            tema = str(v.get("tema") or "").strip()
            resultado = str(v.get("resultado") or "").strip()
            for slug in names_in_vote_field(v.get("en_contra"), dissent_tokens):
                if slug in out:
                    out[slug]["votos_en_contra"].append((fecha, acta_num, tema, resultado))
            for slug in names_in_vote_field(v.get("abstenciones"), dissent_tokens):
                if slug in out:
                    out[slug]["abstenciones"].append((fecha, acta_num, tema, resultado))

    # Derived fields
    for slug, agg in out.items():
        p, a = agg["presente"], agg["ausente"]
        agg["sesiones_conocidas"] = p + a
        agg["asistencia_pct"] = round(100 * p / (p + a)) if (p + a) else None
        agg["n_intervenciones"] = len(agg["intervenciones"])
        agg["fechas_presente"].sort()
        agg["fechas_ausente"].sort()
        agg["intervenciones"].sort(key=lambda x: x[0], reverse=True)
        agg["votos_en_contra"].sort(key=lambda x: x[0], reverse=True)
        agg["abstenciones"].sort(key=lambda x: x[0], reverse=True)
        agg["minuta_autor"].sort(key=lambda x: x[0], reverse=True)
        agg["minuta_secunda"].sort(key=lambda x: x[0], reverse=True)
        # Dedup minutas re-presentadas entre sesiones (misma petición contada >1 vez).
        agg["minuta_autor"] = _dedup_minutas(agg["minuta_autor"])
        agg["minuta_secunda"] = _dedup_minutas(agg["minuta_secunda"])
        agg["n_minuta_autor"] = len(agg["minuta_autor"])
        agg["n_minuta_secunda"] = len(agg["minuta_secunda"])
        agg["ordenanza_autor"] = _dedup_minutas(agg["ordenanza_autor"])
        agg["ordenanza_secunda"] = _dedup_minutas(agg["ordenanza_secunda"])
        agg["n_ordenanza_autor"] = len(agg["ordenanza_autor"])
        agg["n_ordenanza_secunda"] = len(agg["ordenanza_secunda"])

    out["_meta"] = {
        "n_actas": n_actas,
        "unmatched_present": dict(unmatched_present),
        "unmatched_interv": dict(unmatched_interv),
    }
    return out


def main() -> int:
    if not ACTAS_DIR.is_dir():
        print(f"ERROR: {ACTAS_DIR} no existe.", file=sys.stderr)
        return 1

    # Lazy import to avoid a circular dependency (build_concejal_cards imports us).
    from build_concejal_cards import CONCEJAL_ORDER, build_name_index

    canon = build_name_index()
    data = scan_actas(canon, CONCEJAL_ORDER)
    meta = data.pop("_meta")

    print(f"\n=== Estadísticas por concejal — {meta['n_actas']} actas procesadas ===\n")
    header = f"{'Concejal':28s} {'Pres':>5s} {'%':>4s} {'Interv':>7s} {'MinAut':>7s} {'MinSec':>7s} {'Abst':>5s}"
    print(header)
    print("-" * len(header))
    for slug in CONCEJAL_ORDER:
        a = data[slug]
        pct = f"{a['asistencia_pct']}%" if a["asistencia_pct"] is not None else "s/d"
        print(
            f"{slug:28s} {a['presente']:>5d} {pct:>4s} "
            f"{a['n_intervenciones']:>7d} {a['n_minuta_autor']:>7d} {a['n_minuta_secunda']:>7d} {len(a['abstenciones']):>5d}"
        )

    print("\n=== Top 5 temas de intervención por concejal ===")
    for slug in CONCEJAL_ORDER:
        top = data[slug]["temas_intervenidos"].most_common(5)
        if top:
            temas = ", ".join(f"{t} ({n})" for t, n in top)
            print(f"  {slug}: {temas}")

    if meta["unmatched_present"]:
        print("\n[WARN] Nombres en concejales_presentes/ausentes sin slug canónico:")
        for name, n in sorted(meta["unmatched_present"].items(), key=lambda x: -x[1]):
            print(f"    {name!r}: {n}")
    if meta["unmatched_interv"]:
        print("\n[WARN] Nombres en intervenciones sin slug canónico:")
        for name, n in sorted(meta["unmatched_interv"].items(), key=lambda x: -x[1]):
            print(f"    {name!r}: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
