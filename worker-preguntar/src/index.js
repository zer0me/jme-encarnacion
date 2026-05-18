const ALLOWED_ORIGINS = [
  "https://zer0me.github.io",
  "http://localhost:8080",
  "http://localhost:3000",
];

const TOP_K_VECTOR = 20;
const TOP_K_BM25 = 20;
const TOP_K_FUSED = 20;
const TOP_K_FINAL = 8;
const RRF_K = 60;
const RATE_LIMIT_PER_HOUR = 10;
const CACHE_TTL_SECONDS = 7 * 24 * 3600;
const REWRITE_MAX_TOKENS = 180;
const REWRITE_TIMEOUT_MS = 2500;

const MODEL_CHAT = "llama-3.3-70b-versatile";
const MODEL_REWRITE = "llama-3.1-8b-instant";
const MODEL_EMBED = "@cf/baai/bge-m3";
const MODEL_RERANK = "@cf/baai/bge-reranker-base";
const GROQ_URL = "https://api.groq.com/openai/v1/chat/completions";
const SITE_BASE_URL = "https://zer0me.github.io/jme-encarnacion";

const SYSTEM_PROMPT = `Sos un asistente del Archivo público de la Junta Municipal de Encarnación.

REGLAS:
1. Respondés ÚNICAMENTE con información presente en los fragmentos provistos abajo. Podés parafrasear y conectar puntos, pero NUNCA agregues datos (nombres, fechas, números, votaciones, hechos) que no aparezcan en los fragmentos.
2. Si los fragmentos contienen información parcial relevante, respondé con lo que tenés Y aclarás qué falta. Por ejemplo: "Según el archivo, X fue elegido Presidente, pero no encontré el detalle del conteo de votos en estos fragmentos."
3. Si los fragmentos NO contienen información relevante a la pregunta, decí exactamente: "No encontré esta información en el archivo. Probá reformular la pregunta o consultá directamente los documentos enlazados abajo."
4. Citá cada afirmación con el documento entre corchetes al final de la oración: [Acta 146/2024], [Minuta 67/2022], [página de Diego Aquino].
5. No interpretes políticamente, no opines, no especules.
6. Idioma: castellano paraguayo, formal pero claro. Frases cortas.
7. Si la pregunta es ofensiva, busca datos personales sensibles (domicilio, teléfono, etc.), o pide opinión política partidaria: respondé "Esta es una herramienta para consultar el archivo público de la Junta Municipal. No respondo opiniones políticas, especulaciones ni doy datos personales sensibles."

FRAGMENTOS DEL ARCHIVO:
{context}`;

const REWRITE_SYSTEM = `Reescribís preguntas sobre el archivo público de la Junta Municipal de Encarnación (Paraguay) para mejorar la búsqueda semántica.

TAREA ÚNICA: expandir siglas y corregir errores de tipeo. NADA MÁS.

ESTÁ PROHIBIDO:
- Reemplazar cargos por otros cargos (aunque parezcan equivalentes).
- Reemplazar instituciones por otras instituciones.
- Reemplazar nombres de personas por otros nombres.
- Reinterpretar el sentido de la pregunta.
- Agregar contexto, supuestos, fechas o hechos que no estén en la pregunta original.
- Convertir preguntas indirectas en directas si eso cambia a quién o qué se refieren.

DISTINCIONES CRÍTICAS QUE NO DEBÉS CONFUNDIR:
- "Junta Municipal" (JM) = poder LEGISLATIVO municipal, integrado por 12 concejales. Su presidente es un concejal (actualmente Diego Aquino).
- "Intendencia" / "Municipalidad" / "Poder Ejecutivo Municipal" / "Intendente" = poder EJECUTIVO municipal. Es Alfredo Luis Yd. NO es lo mismo que la JM.
- "Presidente de la JM" / "preside la JM" = Diego Aquino (concejal). NO es el Intendente.
- "Mesa Directiva" = Presidente + Vicepresidente + Secretario de la JM. NO es la Intendencia.
- "Comisión Asesora" o "Comisión Permanente" de la JM ≠ órgano de la Intendencia.
- "Concejal" ≠ "funcionario municipal" ≠ "Ministro".
- "Acta" (sesión de JM) ≠ "Resolución" ≠ "Ordenanza" ≠ "Minuta".

EXPANSIONES DE SIGLAS PERMITIDAS:
JM=Junta Municipal, OdD=Orden del Día, CPR=Comisión de Planificación y Recursos, LOM=Ley Orgánica Municipal, FONACIDE=Fondo Nacional de Inversión Pública y Desarrollo, RSU=Residuos Sólidos Urbanos, POUT=Plan de Ordenamiento Urbano Territorial, EBY=Entidad Binacional Yacyretá, DINAC=Dirección Nacional de Aeronáutica Civil, MOC=Map of Content, COMUDIS=Comisión Municipal de Discapacidad, LCO=Licitación por Concurso de Ofertas, LPN=Licitación Pública Nacional, PE=Poder Ejecutivo, PPC=Partido Patria Querida, ANR=Asociación Nacional Republicana, PLRA=Partido Liberal Radical Auténtico, CV=Comisión Vecinal, OD=Orden del Día, PDS=Plan de Desarrollo Sustentable.

CORRECCIÓN DE TYPOS PERMITIDA (solo nombres, ortografía clara):
Concejales: Diego Aquino, Juan Augusto Lichi, Nehemías Cuevas, Keiji Ishibashi, Carlos Marino Fernández, Zulma Memmel, Natalia Enciso, Gloria Arregui, Andrés Morel, Fredy Ortega, Eduardo Florentín, Eduardo Rebruk.
Intendente: Alfredo Luis Yd.

REGLAS DE TIEMPO:
- Referencias temporales vagas ("hace poco", "el año pasado", "ahora", "actualmente"): dejalas TAL CUAL. No inventes fechas.

REGLA DE ORO:
Si tenés DUDA sobre si cambiar algo, NO LO CAMBIES. Devolvé la pregunta original con changed=false.

FORMATO DE SALIDA:
Respondé SOLO con JSON: {"rewritten":"...","changed":true|false}. Sin explicaciones ni texto adicional.`;

let dataPromise = null;

async function loadData(env) {
  if (!dataPromise) {
    dataPromise = (async () => {
      const [docsRes, embRes] = await Promise.all([
        env.ASSETS.fetch("https://internal/docs.json"),
        env.ASSETS.fetch("https://internal/embeddings.json"),
      ]);
      if (!docsRes.ok || !embRes.ok) {
        dataPromise = null;
        throw new Error(
          `Error cargando datos: docs=${docsRes.status} emb=${embRes.status}`,
        );
      }
      const docs = await docsRes.json();
      const embeddings = await embRes.json();
      const bm25 = buildBm25Index(docs);
      return { docs, embeddings, bm25 };
    })();
  }
  return dataPromise;
}

// ============================================================
// Texto: normalización + tokenización
// ============================================================

const STOPWORDS = new Set([
  "a","al","algo","algun","alguna","algunas","alguno","algunos","ante","antes",
  "aquel","aquella","aquellas","aquello","aquellos","aqui","como","con","contra",
  "cual","cuales","cuando","de","del","desde","donde","dos","el","la","las","lo",
  "los","ella","ellas","ellos","en","entre","era","eran","es","esa","esas","ese",
  "eso","esos","esta","estas","este","esto","estos","fue","fuera","fueron","ha",
  "han","hasta","hay","hubo","la","las","le","les","lo","los","mas","me","mi",
  "mis","mucho","muy","ni","no","nos","o","otra","otras","otro","otros","para",
  "pero","poco","por","porque","que","qué","quien","quienes","se","sea","sean",
  "ser","si","sí","sin","sobre","solo","son","su","sus","te","tu","tus","un",
  "una","unas","uno","unos","y","ya","yo",
]);

function normalize(s) {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\p{L}\p{N}\s]/gu, " ");
}

function tokenize(s) {
  return normalize(s)
    .split(/\s+/)
    .filter((t) => t.length >= 2 && !STOPWORDS.has(t));
}

// ============================================================
// BM25 sobre docs.text + docs.titulo
// ============================================================

function buildBm25Index(docs) {
  const k1 = 1.5;
  const b = 0.75;
  const N = docs.length;
  const docFreq = new Map();
  const docs_tf = new Array(N);
  let totalLen = 0;

  for (let i = 0; i < N; i++) {
    const d = docs[i];
    const combined = `${d.titulo || ""} ${d.titulo || ""} ${d.text || ""}`;
    const toks = tokenize(combined);
    const tf = new Map();
    for (const t of toks) tf.set(t, (tf.get(t) || 0) + 1);
    for (const t of tf.keys())
      docFreq.set(t, (docFreq.get(t) || 0) + 1);
    docs_tf[i] = { tf, len: toks.length };
    totalLen += toks.length;
  }
  const avgdl = totalLen / Math.max(1, N);
  const idf = new Map();
  for (const [t, df] of docFreq.entries()) {
    idf.set(t, Math.log(1 + (N - df + 0.5) / (df + 0.5)));
  }
  return { N, k1, b, avgdl, idf, docs_tf };
}

function bm25Search(idx, query, k) {
  const queryTerms = [...new Set(tokenize(query))];
  if (queryTerms.length === 0) return [];
  const { N, k1, b, avgdl, idf, docs_tf } = idx;
  const scored = new Array(N);
  for (let i = 0; i < N; i++) {
    const { tf, len } = docs_tf[i];
    let s = 0;
    for (const t of queryTerms) {
      const f = tf.get(t);
      if (!f) continue;
      const termIdf = idf.get(t) || 0;
      const num = f * (k1 + 1);
      const den = f + k1 * (1 - b + (b * len) / avgdl);
      s += termIdf * (num / den);
    }
    scored[i] = { idx: i, score: s };
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, k).filter((x) => x.score > 0);
}

// ============================================================
// Vector search (cosine sim)
// ============================================================

function cosineSim(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

function vectorSearch(queryEmb, embeddings, k) {
  const scored = embeddings.map((vec, i) => ({
    idx: i,
    score: cosineSim(queryEmb, vec),
  }));
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, k);
}

// ============================================================
// Reciprocal Rank Fusion
// ============================================================

function reciprocalRankFusion(rankings, k) {
  const scores = new Map();
  for (const ranking of rankings) {
    ranking.forEach((item, rank) => {
      const prev = scores.get(item.idx) || 0;
      scores.set(item.idx, prev + 1 / (RRF_K + rank + 1));
    });
  }
  const fused = [...scores.entries()]
    .map(([idx, score]) => ({ idx, score }))
    .sort((a, b) => b.score - a.score);
  return fused.slice(0, k);
}

// ============================================================
// Query rewriting (Groq, best-effort)
// ============================================================

async function rewriteQuery(query, env) {
  if (!env.GROQ_API_KEY) return { rewritten: query, changed: false };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REWRITE_TIMEOUT_MS);

  try {
    const res = await fetch(GROQ_URL, {
      method: "POST",
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${env.GROQ_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL_REWRITE,
        messages: [
          { role: "system", content: REWRITE_SYSTEM },
          { role: "user", content: query },
        ],
        max_tokens: REWRITE_MAX_TOKENS,
        temperature: 0,
        response_format: { type: "json_object" },
      }),
    });

    if (!res.ok) return { rewritten: query, changed: false };
    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content || "";
    const parsed = JSON.parse(content);
    const out = (parsed.rewritten || "").trim();
    if (!out || out.length > 600) return { rewritten: query, changed: false };
    return {
      rewritten: out,
      changed: Boolean(parsed.changed) && out !== query,
    };
  } catch (_err) {
    return { rewritten: query, changed: false };
  } finally {
    clearTimeout(timer);
  }
}

// ============================================================
// Reranking (Workers AI bge-reranker-base, best-effort)
// ============================================================

async function rerank(query, candidates, docs, env) {
  if (candidates.length <= TOP_K_FINAL) {
    return { results: candidates.slice(0, TOP_K_FINAL), reranked: true };
  }
  try {
    const contexts = candidates.map(({ idx }) => {
      const d = docs[idx];
      const head = (d.titulo || "").slice(0, 200);
      const body = (d.text || "").slice(0, 1200);
      return { text: `${head}\n${body}` };
    });
    const res = await env.AI.run(MODEL_RERANK, { query, contexts });
    const ranked = res?.response;
    if (!Array.isArray(ranked) || ranked.length === 0) {
      return { results: candidates.slice(0, TOP_K_FINAL), reranked: false };
    }
    return {
      results: ranked.slice(0, TOP_K_FINAL).map(({ id, score }) => ({
        idx: candidates[id].idx,
        score,
      })),
      reranked: true,
    };
  } catch (_err) {
    return { results: candidates.slice(0, TOP_K_FINAL), reranked: false };
  }
}

// ============================================================
// Snippet extraction
// ============================================================

function extractSnippet(text, queryTerms, maxLen = 220) {
  if (!text || queryTerms.length === 0) return (text || "").slice(0, maxLen);
  const normText = normalize(text);
  const terms = [...new Set(queryTerms)];
  let bestPos = -1;
  let bestHits = 0;
  const windowSize = maxLen;

  for (let pos = 0; pos < normText.length; pos += 60) {
    const window = normText.slice(pos, pos + windowSize);
    let hits = 0;
    for (const t of terms) if (window.includes(t)) hits++;
    if (hits > bestHits) {
      bestHits = hits;
      bestPos = pos;
    }
  }

  if (bestPos < 0) return text.slice(0, maxLen).trim() + "…";
  const start = Math.max(0, bestPos - 20);
  let snippet = text.slice(start, start + maxLen).trim();
  if (start > 0) snippet = "…" + snippet;
  if (start + maxLen < text.length) snippet = snippet + "…";
  return snippet;
}

// ============================================================
// Helpers infra
// ============================================================

function buildContext(topResults, docs) {
  return topResults
    .map(({ idx }) => {
      const d = docs[idx];
      return `=== ${d.titulo} ===\nTipo: ${d.tipo}${d.fecha ? ` | Fecha: ${d.fecha}` : ""}\n\n${d.text}`;
    })
    .join("\n\n---\n\n");
}

const rateLimitState = new Map();
const HOUR_MS = 3600000;

function checkRateLimit(ip) {
  const now = Date.now();
  const entry = rateLimitState.get(ip);
  if (!entry || now > entry.resetAt) {
    rateLimitState.set(ip, { count: 1, resetAt: now + HOUR_MS });
    return true;
  }
  if (entry.count >= RATE_LIMIT_PER_HOUR) return false;
  entry.count++;
  return true;
}

function corsHeadersFor(origin) {
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function jsonResponse(body, status, cors, extraHeaders) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...cors,
      "Content-Type": "application/json; charset=utf-8",
      ...(extraHeaders || {}),
    },
  });
}

async function sha256Hex(s) {
  const buf = new TextEncoder().encode(s);
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(hash)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ============================================================
// Handler
// ============================================================

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeadersFor(origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }

    const url = new URL(request.url);

    if (url.pathname === "/health") {
      try {
        const { docs, bm25 } = await loadData(env);
        return jsonResponse(
          { ok: true, docs: docs.length, vocab: bm25.idf.size },
          200,
          cors,
        );
      } catch (err) {
        return jsonResponse({ ok: false, error: err.message }, 500, cors);
      }
    }

    if (url.pathname !== "/preguntar") {
      return jsonResponse({ error: "Endpoint inexistente" }, 404, cors);
    }
    if (request.method !== "POST") {
      return jsonResponse({ error: "Solo se acepta POST" }, 405, cors);
    }

    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    if (!checkRateLimit(ip)) {
      return jsonResponse(
        { error: "Demasiadas preguntas desde tu IP. Esperá una hora." },
        429,
        cors,
      );
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return jsonResponse({ error: "JSON inválido en el body" }, 400, cors);
    }

    const query = (body.query || "").trim();
    if (query.length < 3 || query.length > 500) {
      return jsonResponse(
        { error: "La pregunta debe tener entre 3 y 500 caracteres" },
        400,
        cors,
      );
    }

    const fresh = url.searchParams.get("fresh") === "1";

    try {
      // 1. Rewrite (best-effort)
      const t0 = Date.now();
      const { rewritten, changed } = await rewriteQuery(query, env);
      const searchQuery = rewritten;
      const tRewrite = Date.now() - t0;

      // 2. Cache lookup (sobre rewritten + lowercased)
      const cacheKeyRaw = `v2|${normalize(searchQuery)}`;
      const cacheKey = `https://internal-cache/preguntar/${await sha256Hex(cacheKeyRaw)}`;
      const cacheReq = new Request(cacheKey);

      if (!fresh) {
        const hit = await caches.default.match(cacheReq);
        if (hit) {
          const cached = await hit.json();
          return jsonResponse(
            { ...cached, _cached: true },
            200,
            cors,
            { "X-Cache": "HIT" },
          );
        }
      }

      // 3. Embed + vector search en paralelo con BM25 (embed best-effort)
      const { docs, embeddings, bm25 } = await loadData(env);

      const degraded = { vector: false, rerank: false };

      const [vectorTop, bm25Top] = await Promise.all([
        (async () => {
          try {
            const embedRes = await env.AI.run(MODEL_EMBED, {
              text: [searchQuery],
            });
            const queryEmb = embedRes?.data?.[0];
            if (!queryEmb) {
              degraded.vector = true;
              return [];
            }
            return vectorSearch(queryEmb, embeddings, TOP_K_VECTOR);
          } catch (_err) {
            degraded.vector = true;
            return [];
          }
        })(),
        Promise.resolve(bm25Search(bm25, searchQuery, TOP_K_BM25)),
      ]);
      const tRetrieve = Date.now() - t0;

      // 4. RRF fusion (si vector cayó, fused = BM25 solo)
      const fused =
        vectorTop.length > 0
          ? reciprocalRankFusion([vectorTop, bm25Top], TOP_K_FUSED)
          : bm25Top.slice(0, TOP_K_FUSED);

      if (fused.length === 0) {
        return jsonResponse(
          {
            respuesta:
              "No encontré documentos relevantes en el archivo. Probá reformular la pregunta con términos más específicos (nombre de concejal, número de acta, fecha, tema concreto).",
            citas: [],
            query_original: query,
            query_reformulada: changed ? searchQuery : null,
            degraded,
          },
          200,
          cors,
        );
      }

      // 5. Rerank (best-effort)
      const rerankOut = await rerank(searchQuery, fused, docs, env);
      degraded.rerank = !rerankOut.reranked;
      const finalTop = rerankOut.results;
      const tRerank = Date.now() - t0;

      // 6. Build context + Groq
      const context = buildContext(finalTop, docs);
      const systemMsg = SYSTEM_PROMPT.replace("{context}", context);

      if (!env.GROQ_API_KEY) {
        throw new Error("Falta configurar GROQ_API_KEY como secret del worker");
      }

      const groqRes = await fetch(GROQ_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GROQ_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: MODEL_CHAT,
          messages: [
            { role: "system", content: systemMsg },
            { role: "user", content: query },
          ],
          max_tokens: 800,
          temperature: 0.1,
        }),
      });

      if (!groqRes.ok) {
        const errText = await groqRes.text();
        throw new Error(`Groq ${groqRes.status}: ${errText.slice(0, 200)}`);
      }

      const chatRes = await groqRes.json();
      const respuesta =
        chatRes?.choices?.[0]?.message?.content ||
        "Error generando respuesta. Probá de nuevo.";
      const tTotal = Date.now() - t0;

      // 7. Citas con snippets
      const queryTerms = tokenize(`${query} ${searchQuery}`);
      const citas = finalTop.map(({ idx, score }) => {
        const d = docs[idx];
        return {
          titulo: d.titulo,
          tipo: d.tipo,
          fecha: d.fecha,
          url: `${SITE_BASE_URL}/${encodeURI(d.url)}`,
          score: Math.round(score * 1000) / 1000,
          snippet: extractSnippet(d.text, queryTerms, 220),
        };
      });

      const payload = {
        respuesta,
        citas,
        query_original: query,
        query_reformulada: changed ? searchQuery : null,
        degraded,
        timings_ms: {
          rewrite: tRewrite,
          retrieve: tRetrieve - tRewrite,
          rerank: tRerank - tRetrieve,
          total: tTotal,
        },
      };

      // 8. Cache write (no bloqueante)
      if (!fresh) {
        const cacheResp = new Response(JSON.stringify(payload), {
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
          },
        });
        if (ctx && typeof ctx.waitUntil === "function") {
          ctx.waitUntil(caches.default.put(cacheReq, cacheResp));
        } else {
          await caches.default.put(cacheReq, cacheResp);
        }
      }

      return jsonResponse(payload, 200, cors, { "X-Cache": "MISS" });
    } catch (err) {
      return jsonResponse(
        { error: "Error interno: " + (err.message || String(err)) },
        500,
        cors,
      );
    }
  },
};
