const jobSelect = document.getElementById("job-select");
const stageSelect = document.getElementById("stage-select");
const reqRentaMin = document.getElementById("req-renta-min");
const reqRentaMax = document.getElementById("req-renta-max");
const reqEdadMin = document.getElementById("req-edad-min");
const reqEdadMax = document.getElementById("req-edad-max");
const reqKeywords = document.getElementById("req-keywords");
const btnFiltrar = document.getElementById("btn-filtrar");
const writeBackCheckbox = document.getElementById("write-back");
const statusMsg = document.getElementById("status-msg");
const resultsSummary = document.getElementById("results-summary");
const resultsTable = document.getElementById("results-table");
const resultsTbody = resultsTable.querySelector("tbody");

// --- Multi-select con opciones por defecto + posibilidad de agregar otras ---
// Se usa para Carrera, Universidad y Ciudad: cada uno es un botón que abre un
// menú con checkboxes de las opciones predefinidas, más un campo para
// agregar una opción que no esté en la lista.
const MULTISELECT_DEFAULTS = {
  carreras: [
    "Ingeniería Comercial",
    "Ingeniería Civil Industrial",
    "Contador Auditor",
    "Abogado",
    "Administración de Empresas",
    "Ingeniería en Prevención de Riesgos",
    "Ingeniería Acuícola",
    "Veterinario",
    "Ingeniería en Computación",
    "Psicología",
    "Ingeniero Comercio Exterior",
  ],
  universidades: [
    "Universidad Católica",
    "Universidad de Chile",
    "Universidad Adolfo Ibáñez",
    "Universidad de los Andes",
    "Universidad Austral",
    "Universidad San Sebastián",
    "Universidad de los Lagos",
    "Universidad Andrés Bello",
    "Universidad del Desarrollo",
    "Universidad de Concepción",
    "Universidad Técnico Federico Santa María",
  ],
  ciudades: [
    "Puerto Montt",
    "Puerto Varas",
    "Osorno",
    "Valdivia",
    "Temuco",
    "Concepción",
    "Santiago",
    "Talca",
    "Viña del Mar",
    "Antofagasta",
    "Calama",
    "Iquique",
    "Punta Arenas",
    "Rancagua",
    "Villarrica",
    "Chiloé",
  ],
};

const msOptions = {};
const msSelected = {};

function renderMsOptions(key) {
  const wrapper = document.querySelector(`.ms[data-ms="${key}"]`);
  const optionsEl = wrapper.querySelector(".ms-options");
  optionsEl.innerHTML = "";
  msOptions[key].forEach((opt) => {
    const label = document.createElement("label");
    label.className = "ms-option";
    const checked = msSelected[key].has(opt) ? "checked" : "";
    label.innerHTML = `<input type="checkbox" value="${opt}" ${checked}> ${opt}`;
    optionsEl.appendChild(label);
  });
  updateMsButtonLabel(key);
}

function updateMsButtonLabel(key) {
  const wrapper = document.querySelector(`.ms[data-ms="${key}"]`);
  const btnLabel = wrapper.querySelector(".ms-btn-label");
  const values = Array.from(msSelected[key]);
  if (values.length === 0) btnLabel.textContent = "Sin selección";
  else if (values.length <= 2) btnLabel.textContent = values.join(", ");
  else btnLabel.textContent = `${values.length} seleccionadas`;
}

function closeAllMs(except) {
  document.querySelectorAll(".ms.open").forEach((el) => {
    if (el !== except) el.classList.remove("open");
  });
}

function initMultiSelect(key) {
  msOptions[key] = [...MULTISELECT_DEFAULTS[key]];
  msSelected[key] = new Set();
  const wrapper = document.querySelector(`.ms[data-ms="${key}"]`);

  wrapper.querySelector(".ms-btn").addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = wrapper.classList.contains("open");
    closeAllMs();
    if (!isOpen) wrapper.classList.add("open");
  });

  // Cualquier click DENTRO del menú (marcar un checkbox, hacer click en la
  // etiqueta, escribir en "agregar otra", etc.) no debe burbujear hasta el
  // listener global de document que cierra los menús abiertos — si no, el
  // menú se cerraba apenas se marcaba la primera opción.
  wrapper.querySelector(".ms-menu").addEventListener("click", (e) => {
    e.stopPropagation();
  });

  wrapper.querySelector(".ms-options").addEventListener("change", (e) => {
    if (e.target.type !== "checkbox") return;
    if (e.target.checked) msSelected[key].add(e.target.value);
    else msSelected[key].delete(e.target.value);
    updateMsButtonLabel(key);
  });

  const addInput = wrapper.querySelector(".ms-add-input");
  const addBtn = wrapper.querySelector(".ms-add-btn");
  const addCustom = () => {
    const val = addInput.value.trim();
    if (!val) return;
    if (!msOptions[key].some((o) => o.toLowerCase() === val.toLowerCase())) {
      msOptions[key].push(val);
    }
    msSelected[key].add(val);
    addInput.value = "";
    renderMsOptions(key);
  };
  addBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    addCustom();
  });
  addInput.addEventListener("click", (e) => e.stopPropagation());
  addInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addCustom();
    }
  });

  renderMsOptions(key);
}

function getMsValues(key) {
  return Array.from(msSelected[key]);
}

document.addEventListener("click", () => closeAllMs());

function setStatus(msg, isError) {
  statusMsg.textContent = msg || "";
  statusMsg.style.color = isError ? "#8F1A1A" : "#5C5A55";
}

function updateFiltrarEnabled() {
  btnFiltrar.disabled = !(jobSelect.value && stageSelect.value);
}

async function loadJobs() {
  setStatus("Cargando procesos desde Team Tailor…");
  try {
    const res = await fetch("/api/jobs");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Error desconocido");

    jobSelect.innerHTML = '<option value="">Selecciona un proceso</option>';
    data.jobs.forEach((job) => {
      const opt = document.createElement("option");
      opt.value = job.id;
      opt.textContent = job.title || `Proceso ${job.id}`;
      jobSelect.appendChild(opt);
    });
    setStatus("");
  } catch (err) {
    setStatus("No se pudieron cargar los procesos: " + err.message, true);
  }
}

async function loadStages(jobId) {
  stageSelect.innerHTML = '<option value="">Cargando etapas…</option>';
  stageSelect.disabled = true;
  try {
    const res = await fetch(`/api/jobs/${jobId}/stages`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Error desconocido");

    stageSelect.innerHTML = '<option value="">Selecciona una etapa</option>';
    data.stages.forEach((stage) => {
      const opt = document.createElement("option");
      opt.value = stage.id;
      opt.textContent = stage.name || `Etapa ${stage.id}`;
      stageSelect.appendChild(opt);
    });
    stageSelect.disabled = false;
  } catch (err) {
    setStatus("No se pudieron cargar las etapas: " + err.message, true);
  }
}

jobSelect.addEventListener("change", () => {
  if (jobSelect.value) {
    loadStages(jobSelect.value);
  } else {
    stageSelect.innerHTML = '<option value="">Selecciona un proceso primero</option>';
    stageSelect.disabled = true;
  }
  updateFiltrarEnabled();
});

stageSelect.addEventListener("change", updateFiltrarEnabled);

function splitList(value, max) {
  const items = value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return max ? items.slice(0, max) : items;
}

function currentRequirements() {
  return {
    renta_min: reqRentaMin.value ? Number(reqRentaMin.value) : null,
    renta_max: reqRentaMax.value ? Number(reqRentaMax.value) : null,
    edad_min: reqEdadMin.value ? Number(reqEdadMin.value) : null,
    edad_max: reqEdadMax.value ? Number(reqEdadMax.value) : null,
    carreras: getMsValues("carreras").map((s) => s.toLowerCase()),
    universidades: getMsValues("universidades").map((s) => s.toLowerCase()),
    ciudades: getMsValues("ciudades").map((s) => s.toLowerCase()),
    palabras_clave: splitList(reqKeywords.value, 3),
  };
}

function renderResults(results) {
  resultsTbody.innerHTML = "";
  results.forEach((r) => {
    const tr = document.createElement("tr");

    const tagCell = `<span class="tag ${r.tier}">${r.tier}</span>`;
    const nombre = r.candidate_name || "(sin nombre)";
    const nota = r.note_written
      ? "Nota escrita ✔"
      : (r.write_error ? "Error: " + r.write_error : "-");

    tr.innerHTML = `
      <td>${tagCell}</td>
      <td>${nombre}</td>
      <td>${r.score}</td>
      <td>${r.renta_status}</td>
      <td>${r.edad_status}</td>
      <td>${r.carrera_status}</td>
      <td>${r.universidad_status}</td>
      <td>${r.ciudad_status}</td>
      <td>${r.keywords_status}</td>
      <td>${nota}</td>
    `;
    resultsTbody.appendChild(tr);
  });
  resultsTable.classList.toggle("hidden", results.length === 0);
}

btnFiltrar.addEventListener("click", async () => {
  setStatus("Consultando candidatos y aplicando el filtro… esto puede tardar unos segundos.");
  btnFiltrar.disabled = true;
  resultsSummary.textContent = "";
  resultsTable.classList.add("hidden");

  try {
    const res = await fetch("/api/filtrar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: jobSelect.value,
        stage_id: stageSelect.value,
        requirements: currentRequirements(),
        write_back: writeBackCheckbox.checked,
      }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Error desconocido");

    const conteo = { Alto: 0, Medio: 0, Bajo: 0 };
    data.results.forEach((r) => conteo[r.tier] = (conteo[r.tier] || 0) + 1);
    resultsSummary.textContent =
      `${data.count} candidatos — Alto: ${conteo.Alto || 0} · Medio: ${conteo.Medio || 0} · Bajo: ${conteo.Bajo || 0}`;

    renderResults(data.results);
    setStatus("Listo.");
  } catch (err) {
    setStatus("Error al filtrar: " + err.message, true);
  } finally {
    updateFiltrarEnabled();
  }
});

initMultiSelect("carreras");
initMultiSelect("universidades");
initMultiSelect("ciudades");
loadJobs();
updateFiltrarEnabled();
