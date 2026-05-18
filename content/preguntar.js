(function () {
  const API_URL = "https://jme-preguntar.ale-nubri.workers.dev/preguntar";

  function init() {
    const form = document.getElementById("preguntar-form");
    if (!form || form.dataset.preguntarInitialized === "1") return;
    form.dataset.preguntarInitialized = "1";

    const input = document.getElementById("preguntar-input");
    const submit = document.getElementById("preguntar-submit");
    const counter = document.getElementById("preguntar-counter");
    const status = document.getElementById("preguntar-status");
    const respDiv = document.getElementById("preguntar-respuesta");
    const respText = document.getElementById("preguntar-respuesta-text");
    const citasList = document.getElementById("preguntar-citas");
    const reformulada = document.getElementById("preguntar-reformulada");

    function showStatus(msg, isError) {
      status.textContent = msg;
      status.hidden = false;
      status.classList.toggle("preguntar-error", !!isError);
    }
    function hideStatus() {
      status.hidden = true;
      status.classList.remove("preguntar-error");
    }
    function updateCounter() {
      counter.textContent = input.value.length + " / 500";
    }
    function hideReformulada() {
      if (reformulada) {
        reformulada.hidden = true;
        reformulada.textContent = "";
      }
    }

    input.addEventListener("input", updateCounter);
    updateCounter();

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      const query = input.value.trim();
      if (query.length < 3) {
        showStatus("La pregunta debe tener al menos 3 caracteres.", true);
        return;
      }

      submit.disabled = true;
      submit.textContent = "Buscando…";
      respDiv.hidden = true;
      hideReformulada();
      showStatus(
        "Buscando entre 696 documentos y procesando con IA. Puede tardar 5-15 segundos.",
        false,
      );

      try {
        const r = await fetch(API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: query }),
        });
        const data = await r.json();

        if (!r.ok) {
          showStatus("Error: " + (data.error || r.statusText), true);
          return;
        }

        hideStatus();
        respText.textContent = data.respuesta || "(respuesta vacía)";

        if (reformulada && data.query_reformulada) {
          reformulada.textContent =
            "Interpretamos tu pregunta como: «" + data.query_reformulada + "»";
          reformulada.hidden = false;
        } else {
          hideReformulada();
        }

        citasList.innerHTML = "";
        (data.citas || []).forEach(function (c) {
          const li = document.createElement("li");
          const a = document.createElement("a");
          a.href = c.url;
          a.textContent = c.titulo + (c.fecha ? " (" + c.fecha + ")" : "");
          a.target = "_self";
          li.appendChild(a);
          const meta = document.createElement("span");
          meta.className = "preguntar-cita-meta";
          meta.textContent =
            " · " + c.tipo + " · relevancia " + Math.round(c.score * 100) + "%";
          li.appendChild(meta);
          if (c.snippet) {
            const sn = document.createElement("div");
            sn.className = "preguntar-cita-snippet";
            sn.textContent = c.snippet;
            li.appendChild(sn);
          }
          citasList.appendChild(li);
        });
        respDiv.hidden = false;
        respDiv.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (err) {
        showStatus("Error de red: " + (err.message || err), true);
      } finally {
        submit.disabled = false;
        submit.textContent = "Preguntar al archivo";
      }
    });
  }

  init();
  document.addEventListener("nav", init);
})();
