"""Re-sincroniza embeddings.json contra docs.json tolerando inserciones,
borrados y reordenamientos de docs (no solo cambios de texto in-place).

A diferencia de _reembed_changed.py (que exige misma longitud y empalma por
índice), esto reconstruye el array de embeddings en el ORDEN nuevo de docs.json,
reutilizando el embedding viejo para cada doc cuyo (path, text) no cambió y
llamando a la API SOLO por los docs nuevos o modificados. Preserva la quota
diaria de Workers AI cuando agregás/quitás pocas notas.

Source of truth del estado viejo: HEAD:worker-preguntar/data/docs.json alineado
1:1 con el embeddings.json actual en disco (ambos commiteados juntos).

Uso: python tools/_reembed_sync.py
"""
from __future__ import annotations

import json
import subprocess
import sys

from build_embeddings import DOCS, OUT, ENV, embed_batch, load_env


def main() -> int:
    env = load_env(ENV)
    account_id = env.get("JME_CF_ACCOUNT_ID") or env.get("CF_ACCOUNT_ID")
    token = env.get("JME_CF_API_TOKEN") or env.get("CF_API_TOKEN")
    if not account_id or not token:
        print("Falta JME_CF_ACCOUNT_ID o JME_CF_API_TOKEN en worker-preguntar/.env", file=sys.stderr)
        return 1

    new = json.loads(DOCS.read_text(encoding="utf-8"))
    old_emb = json.loads(OUT.read_text(encoding="utf-8"))

    git = subprocess.run(
        ["git", "show", "HEAD:worker-preguntar/data/docs.json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if git.returncode != 0:
        print(f"git show falló: {git.stderr}", file=sys.stderr)
        return 1
    old_docs = json.loads(git.stdout)

    if len(old_docs) != len(old_emb):
        print(
            f"HEAD docs.json ({len(old_docs)}) no alinea con embeddings.json en disco "
            f"({len(old_emb)}). Corré un rebuild completo.", file=sys.stderr,
        )
        return 1

    # path -> (text, embedding) del estado viejo (paths son únicos por entry)
    old_by_path = {d["path"]: (d["text"], emb) for d, emb in zip(old_docs, old_emb)}

    result: list[list[float] | None] = []
    to_embed_idx: list[int] = []
    reused = 0
    for i, d in enumerate(new):
        prev = old_by_path.get(d["path"])
        if prev is not None and prev[0] == d["text"]:
            result.append(prev[1])
            reused += 1
        else:
            result.append(None)
            to_embed_idx.append(i)

    if not to_embed_idx:
        # Puede que solo haya cambiado el ORDEN (reuso 100%) -> reescribir igual
        # para realinear, pero avisamos.
        if result == old_emb:
            print("Nada que re-embeber y el orden no cambió. No escribo.")
            return 0
        print(f"Reordenamiento puro: {reused} embeddings reutilizados, 0 llamadas a la API.")
    else:
        print(f"Reutilizo {reused} embeddings; embebo {len(to_embed_idx)} docs nuevos/cambiados:")
        for i in to_embed_idx:
            print(f"  [{i}] {new[i]['path']}")
        texts = [new[i]["text"] for i in to_embed_idx]
        vecs = embed_batch(texts, account_id, token)
        if len(vecs) != len(to_embed_idx):
            print(f"API devolvió {len(vecs)} vectores, esperaba {len(to_embed_idx)}", file=sys.stderr)
            return 1
        for j, i in enumerate(to_embed_idx):
            result[i] = vecs[j]

    # Validación final: sin huecos, dimensión consistente.
    dim = len(old_emb[0]) if old_emb else (len(result[0]) if result and result[0] else 0)
    for i, v in enumerate(result):
        if v is None:
            print(f"Hueco en índice {i} ({new[i]['path']}) — abortando.", file=sys.stderr)
            return 1
        if len(v) != dim:
            print(f"Dimensión inconsistente en índice {i}: {len(v)} != {dim} — abortando.", file=sys.stderr)
            return 1

    if len(result) != len(new):
        print(f"Resultado {len(result)} != docs {len(new)} — abortando.", file=sys.stderr)
        return 1

    OUT.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print(f"OK - embeddings.json re-sincronizado: {len(result)} docs, dim {dim} "
          f"({reused} reutilizados, {len(to_embed_idx)} embebidos).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
