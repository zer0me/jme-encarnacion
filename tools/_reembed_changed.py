"""Re-embed SOLO los docs cuyo texto cambió respecto a HEAD (git), empalmándolos
en embeddings.json en sus índices originales. Evita un rebuild completo (1318 docs)
que quemaría la quota diaria de Workers AI. Idempotente: si nada cambió, no llama a la API.

Uso: python tools/_reembed_changed.py
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
    embeddings = json.loads(OUT.read_text(encoding="utf-8"))
    if len(embeddings) != len(new):
        print(f"Desalineado: docs={len(new)} embeddings={len(embeddings)}. Corré un rebuild completo.", file=sys.stderr)
        return 1

    git = subprocess.run(
        ["git", "show", "HEAD:worker-preguntar/data/docs.json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    old = json.loads(git.stdout)
    oldm = {d["path"]: d["text"] for d in old}

    changed_idx = [i for i, d in enumerate(new) if oldm.get(d["path"]) != d["text"]]
    if not changed_idx:
        print("Nada cambió respecto a HEAD. No re-embebo.")
        return 0

    print(f"Re-embebiendo {len(changed_idx)} docs cambiados:")
    for i in changed_idx:
        print(f"  [{i}] {new[i]['path']}")

    texts = [new[i]["text"] for i in changed_idx]
    vecs = embed_batch(texts, account_id, token)
    if len(vecs) != len(changed_idx):
        print(f"API devolvió {len(vecs)} vectores, esperaba {len(changed_idx)}", file=sys.stderr)
        return 1

    dim_old = len(embeddings[changed_idx[0]])
    dim_new = len(vecs[0])
    if dim_old != dim_new:
        print(f"Dimensión cambió ({dim_old}->{dim_new}). Abortando para no corromper el índice.", file=sys.stderr)
        return 1

    for j, i in enumerate(changed_idx):
        embeddings[i] = vecs[j]

    OUT.write_text(json.dumps(embeddings, separators=(",", ":")), encoding="utf-8")
    print(f"OK - {len(changed_idx)} embeddings actualizados in-place ({len(embeddings)} total, dim {dim_new}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
