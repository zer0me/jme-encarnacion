"""Generate embeddings for every doc in worker-preguntar/data/docs.json.

Calls Cloudflare AI REST API (@cf/baai/bge-base-en-v1.5, 768-dim).
Reads token from worker-preguntar/.env.
Writes worker-preguntar/data/embeddings.json as a JSON array of arrays
(aligned 1-to-1 with docs.json order).

Re-runnable: skips docs already embedded if --resume is passed.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

REPO = Path("C:/Users/Alejandro/projects/jme-encarnacion")
DATA = REPO / "worker-preguntar" / "data"
DOCS = DATA / "docs.json"
OUT = DATA / "embeddings.json"
ENV = REPO / "worker-preguntar" / ".env"

MODEL = "@cf/baai/bge-m3"
BATCH_SIZE = 25  # bge-m3 supports batched input


def load_env(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def embed_batch(texts: list[str], account_id: str, token: str) -> list[list[float]]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
    payload = json.dumps({"text": texts}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e

    data = json.loads(raw)
    if not data.get("success"):
        raise RuntimeError(f"CF AI error: {data}")
    return data["result"]["data"]


def main() -> int:
    env = load_env(ENV)
    account_id = (
        env.get("JME_CF_ACCOUNT_ID")
        or env.get("CF_ACCOUNT_ID")
        or os.environ.get("JME_CF_ACCOUNT_ID")
        or os.environ.get("CF_ACCOUNT_ID")
    )
    token = (
        env.get("JME_CF_API_TOKEN")
        or env.get("CF_API_TOKEN")
        or os.environ.get("JME_CF_API_TOKEN")
        or os.environ.get("CF_API_TOKEN")
    )
    if not account_id or not token:
        print("Falta JME_CF_ACCOUNT_ID o JME_CF_API_TOKEN en worker-preguntar/.env", file=sys.stderr)
        return 1

    if not DOCS.exists():
        print(f"No existe {DOCS}. Corré primero: python tools/build_docs_json.py", file=sys.stderr)
        return 1

    docs = json.loads(DOCS.read_text(encoding="utf-8"))
    print(f"Embedando {len(docs)} docs en batches de {BATCH_SIZE}...")

    resume = "--resume" in sys.argv
    existing = []
    if resume and OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        if len(existing) >= len(docs):
            print(f"Ya están todos ({len(existing)} embeddings). Salgo.")
            return 0
        print(f"Resume: skip los primeros {len(existing)} ya hechos.")

    embeddings: list[list[float]] = list(existing)
    start = len(embeddings)
    t0 = time.time()

    for i in range(start, len(docs), BATCH_SIZE):
        batch = docs[i : i + BATCH_SIZE]
        texts = [d["text"] for d in batch]
        for attempt in range(3):
            try:
                vecs = embed_batch(texts, account_id, token)
                break
            except (RuntimeError, urllib.error.URLError) as e:
                if attempt == 2:
                    print(f"Falló batch {i}-{i+len(batch)} 3 veces: {e}", file=sys.stderr)
                    OUT.write_text(
                        json.dumps(embeddings, separators=(",", ":")),
                        encoding="utf-8",
                    )
                    return 1
                wait = 2 ** attempt
                print(f"  intento {attempt+1} falló ({e}), reintento en {wait}s...", file=sys.stderr)
                time.sleep(wait)

        embeddings.extend(vecs)
        elapsed = time.time() - t0
        rate = (len(embeddings) - start) / elapsed if elapsed > 0 else 0
        remaining = (len(docs) - len(embeddings)) / rate if rate > 0 else 0
        print(
            f"  [{len(embeddings)}/{len(docs)}] "
            f"({rate:.1f} docs/s, ~{remaining:.0f}s restante)"
        )

        if (i // BATCH_SIZE) % 5 == 0:
            OUT.write_text(
                json.dumps(embeddings, separators=(",", ":")),
                encoding="utf-8",
            )

    OUT.write_text(
        json.dumps(embeddings, separators=(",", ":")),
        encoding="utf-8",
    )
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"OK - {len(embeddings)} embeddings -> {OUT} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
