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
        }
        for slug in slugs
    }
    dissent_tokens = build_dissent_tokens(slugs, canon)

    n_actas = 0
    unmatched_present: Counter = Counter()
    unmatched_interv: Counter = Counter()

    for doc in sorted(ACTAS_DIR.glob("*.md")):
        fm, _ = split_frontmatter(doc.read_text(encoding="utf-8"))
        if not fm:
            continue
        n_actas += 1
        fecha = str(fm.get("fecha") or fm.get("fecha_sesion") or "").strip()
        acta_num = str(fm.get("numero") or doc.stem).strip()

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
    header = f"{'Concejal':28s} {'Pres':>5s} {'Aus':>4s} {'%':>4s} {'Interv':>7s} {'EnContra':>9s} {'Abst':>5s}"
    print(header)
    print("-" * len(header))
    for slug in CONCEJAL_ORDER:
        a = data[slug]
        pct = f"{a['asistencia_pct']}%" if a["asistencia_pct"] is not None else "s/d"
        print(
            f"{slug:28s} {a['presente']:>5d} {a['ausente']:>4d} {pct:>4s} "
            f"{a['n_intervenciones']:>7d} {len(a['votos_en_contra']):>9d} {len(a['abstenciones']):>5d}"
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
