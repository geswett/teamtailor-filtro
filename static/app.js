const jobSelect = document.getElementById("job-select");
const stageSelect = document.getElementById("stage-select");
const perfilFileInput = document.getElementById("perfil-file");
const btnUploadPerfil = document.getElementById("btn-upload-perfil");
const requirementsEditor = document.getElementById("requirements-editor");
const reqFormacion = document.getElementById("req-formacion");
const reqArea = document.getElementById("req-area");
const reqIndustria = document.getElementById("req-industria");
const reqSalarioMin = document.getElementById("req-salario-min");
const reqSalarioMax = document.getElementById("req-salario-max");
const btnFiltrar = document.getElementById("btn-filtrar");
const writeBackCheckbox = document.getElementById("write-back");
const statusMsg = document.getElementById("status-msg");
const resultsSummary = document.getElementById("results-summary");
const resultsTable = document.getElementById("results-table");
const resultsTbody = resultsTable.querySelector("tbody");

let perfilCargado = false;

function setStatus(msg, isError) {
  statusMsg.textContent = msg || "";
  statusMsg.style.color = isError ? "#c0392b" : "#767676";
}

function updateFiltrarEnabled() {
  btnFiltrar.disabled = !(jobSelect.value && stageSelect.value && perfilCargado);
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

btnUploadPerfil.addEventListener("click", async () => {
  const file = perfilFileInput.files[0];
  if (!file) {
    setStatus("Selecciona primero un archivo .docx o .pdf", true);
    return;
  }
  setStatus("Leyendo perfil de cargo…");
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/perfil", { method: "POST", body: formData });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Error desconocido");

    const req = data.requirements;
    reqFormacion.value = (req.formacion_excluyente || []).join(", ");
    reqArea.value = (req.area_keywords || []).join(", ");
    reqIndustria.value = (req.industria_keywords || []).join(", ");
    reqSalarioMin.value = req.salario_min || "";
    reqSalarioMax.value = req.salario_max || "";

    requirementsEditor.classList.remove("hidden");
    perfilCargado = true;
    updateFiltrarEnabled();
    setStatus("Perfil cargado. Revisa/ajusta los requisitos antes de filtrar.");
  } catch (err) {
    setStatus("No se pudo leer el perfil: " + err.message, true);
  }
});

function currentRequirements() {
  return {
    formacion_excluyente: reqFormacion.value
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
    area_keywords: reqArea.value
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
    industria_keywords: reqIndustria.value
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean),
    salario_min: reqSalarioMin.value ? Number(reqSalarioMin.value) : null,
    salario_max: reqSalarioMax.value ? Number(reqSalarioMax.value) : null,
  };
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : str;
  return div.innerHTML;
}

function renderResults(results) {
  resultsTbody.innerHTML = "";
  results.forEach((r) => {
    const tr = document.createElement("tr");

    const tagCell = `<span class="tag ${r.tier}">${r.tier}</span>`;
    const nombre = r.candidate_name || "(sin nombre)";
    const formacion = r.formacion_ok === null
      ? "sin lista definida"
      : (r.formacion_ok ? "cumple" : "no detectada");
    const nota = r.note_written
      ? "Nota escrita ✔"
      : (r.write_error ? "Error: " + r.write_error : "-");

    tr.innerHTML = `
      <td>${tagCell}</td>
      <td>${nombre}</td>
      <td>${r.score}</td>
      <td>${formacion}${r.formacion_hits.length ? " (" + r.formacion_hits.join(", ") + ")" : ""}</td>
      <td>${r.area_hits.join(", ") || "-"}</td>
      <td>${r.industria_hits.join(", ") || "-"}</td>
      <td>${r.years_detected ?? "-"}</td>
      <td>${r.renta_esperada ? r.renta_esperada.toLocaleString("es-CL") : "-"}</td>
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

loadJobs();
