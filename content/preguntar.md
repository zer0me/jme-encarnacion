---
title: Preguntale al archivo
description: Hacé preguntas en lenguaje natural al archivo de la Junta Municipal de Encarnación. Respuestas con citas a documentos oficiales.
---

<div class="preguntar-disclaimer">
  <strong>Cómo funciona.</strong> Esta herramienta usa inteligencia artificial para buscar respuestas en los <strong>696 documentos</strong> publicados en el archivo (actas, minutas, resoluciones, normativa, perfiles). La IA está configurada para <strong>solo citar lo que está en los documentos</strong> — si la información no aparece, te lo dice en lugar de inventar. <strong>Siempre verificá las respuestas en las fuentes citadas abajo de cada respuesta.</strong>
</div>

<form id="preguntar-form" class="preguntar-form" autocomplete="off">
  <label for="preguntar-input">Hacé tu pregunta:</label>
  <textarea id="preguntar-input" name="query" placeholder="Ej: ¿Quién es Diego Aquino y qué cargo ocupa? · ¿Qué dice el archivo sobre el Estacionamiento Tarifado? · ¿Qué empresa tiene el contrato de relleno sanitario?" maxlength="500" rows="3" required></textarea>
  <div class="preguntar-row">
    <button type="submit" id="preguntar-submit">Preguntar al archivo</button>
    <span id="preguntar-counter" class="preguntar-counter">0 / 500</span>
  </div>
</form>

<div id="preguntar-status" class="preguntar-status" hidden></div>

<div id="preguntar-respuesta" class="preguntar-respuesta" hidden>
  <h2>Respuesta</h2>
  <div id="preguntar-respuesta-text" class="preguntar-respuesta-text"></div>
  <h3>Fuentes consultadas</h3>
  <ol id="preguntar-citas" class="preguntar-citas"></ol>
</div>

<div class="preguntar-meta">
  Motor: <code>Llama 3.3 70B</code> · Recuperación: embeddings <code>bge-m3</code> multilingual · Backend: Cloudflare Workers AI · Modo: extractivo (no sintetiza fuera del archivo).
</div>

<style>
.preguntar-disclaimer {
  background: var(--lightgray);
  border-left: 4px solid var(--tertiary);
  padding: 1em 1.2em;
  margin: 1.5em 0;
  font-size: 0.95em;
  line-height: 1.55;
}
.preguntar-form {
  margin: 1.5em 0;
}
.preguntar-form label {
  display: block;
  font-weight: 600;
  margin-bottom: 0.5em;
  color: var(--secondary);
}
.preguntar-form textarea {
  width: 100%;
  padding: 0.8em;
  font: inherit;
  font-size: 1em;
  border: 2px solid var(--lightgray);
  border-radius: 4px;
  background: var(--light);
  color: var(--dark);
  resize: vertical;
  box-sizing: border-box;
  min-height: 84px;
}
.preguntar-form textarea:focus {
  outline: none;
  border-color: var(--secondary);
}
.preguntar-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.8em;
}
.preguntar-form button {
  padding: 0.7em 1.6em;
  background: var(--secondary);
  color: var(--light);
  border: none;
  border-radius: 4px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  font-size: 1em;
  transition: background 0.15s;
}
.preguntar-form button:hover:not(:disabled) {
  background: var(--darkgray);
}
.preguntar-form button:disabled {
  background: var(--gray);
  cursor: wait;
}
.preguntar-counter {
  font-size: 0.85em;
  color: var(--gray);
  font-variant-numeric: tabular-nums;
}
.preguntar-status {
  padding: 1em 1.2em;
  background: var(--lightgray);
  border-left: 4px solid var(--secondary);
  border-radius: 4px;
  margin: 1em 0;
  font-style: italic;
}
.preguntar-status.preguntar-error {
  border-left-color: #b03030;
  background: rgba(176, 48, 48, 0.08);
  font-style: normal;
}
.preguntar-respuesta {
  margin-top: 2em;
  padding-top: 1.5em;
  border-top: 2px solid var(--lightgray);
}
.preguntar-respuesta h2 {
  color: var(--secondary);
  margin-top: 0;
  font-size: 1.3em;
}
.preguntar-respuesta h3 {
  color: var(--secondary);
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  font-size: 1.05em;
}
.preguntar-respuesta-text {
  line-height: 1.7;
  white-space: pre-wrap;
}
.preguntar-citas {
  padding-left: 1.4em;
  margin-top: 0.3em;
}
.preguntar-citas li {
  margin-bottom: 0.5em;
  font-size: 0.95em;
  line-height: 1.5;
}
.preguntar-citas a {
  color: var(--secondary);
  text-decoration: none;
  border-bottom: 1px solid var(--tertiary);
  font-weight: 500;
}
.preguntar-citas a:hover {
  background: var(--highlight);
}
.preguntar-citas .preguntar-cita-meta {
  color: var(--gray);
  font-size: 0.88em;
  margin-left: 0.4em;
}
.preguntar-meta {
  margin-top: 3em;
  padding-top: 1em;
  border-top: 1px solid var(--lightgray);
  font-size: 0.82em;
  color: var(--gray);
  text-align: center;
  line-height: 1.6;
}
.preguntar-meta code {
  font-family: var(--codeFont, "JetBrains Mono", monospace);
  font-size: 0.92em;
  background: var(--lightgray);
  padding: 0.1em 0.4em;
  border-radius: 3px;
}
</style>

<script src="./preguntar.js" defer></script>
