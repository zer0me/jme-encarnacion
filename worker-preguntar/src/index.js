const ALLOWED_ORIGINS = [
  "https://zer0me.github.io",
  "http://localhost:8080",
  "http://localhost:3000",
];
const TOP_K = 8;
const RATE_LIMIT_PER_HOUR = 10;
const MODEL_CHAT = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const MODEL_EMBED = "@cf/baai/bge-m3";
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
      return { docs, embeddings };
    })();
  }
  return dataPromise;
}

function cosineSim(a, b) {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

function topKIndices(queryEmbedding, embeddings, k) {
  const scored = embeddings.map((vec, i) => ({
    idx: i,
    score: cosineSim(queryEmbedding, vec),
  }));
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, k);
}

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

function jsonResponse(body, status, cors) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors, "Content-Type": "application/json; charset=utf-8" },
  });
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeadersFor(origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }

    const url = new URL(request.url);

    if (url.pathname === "/health") {
      try {
        const { docs } = await loadData(env);
        return jsonResponse({ ok: true, docs: docs.length }, 200, cors);
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

    try {
      const { docs, embeddings } = await loadData(env);

      const embedRes = await env.AI.run(MODEL_EMBED, { text: [query] });
      const queryEmb = embedRes.data[0];

      const top = topKIndices(queryEmb, embeddings, TOP_K);
      const context = buildContext(top, docs);
      const systemMsg = SYSTEM_PROMPT.replace("{context}", context);

      const chatRes = await env.AI.run(MODEL_CHAT, {
        messages: [
          { role: "system", content: systemMsg },
          { role: "user", content: query },
        ],
        max_tokens: 800,
        temperature: 0.1,
      });

      const respuesta =
        (chatRes && chatRes.response) ||
        "Error generando respuesta. Probá de nuevo.";

      const citas = top.map(({ idx, score }) => {
        const d = docs[idx];
        return {
          titulo: d.titulo,
          tipo: d.tipo,
          fecha: d.fecha,
          url: `${SITE_BASE_URL}/${encodeURI(d.url)}`,
          score: Math.round(score * 1000) / 1000,
        };
      });

      return jsonResponse({ respuesta, citas }, 200, cors);
    } catch (err) {
      return jsonResponse(
        { error: "Error interno: " + (err.message || String(err)) },
        500,
        cors,
      );
    }
  },
};
