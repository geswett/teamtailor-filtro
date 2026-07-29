"""
Interfaz web para filtrar candidatos de Team Tailor según 6 criterios
definidos a mano por el reclutador (renta, edad, carrera, universidad,
ciudad de residencia y palabras clave). Ya no se usa un perfil de cargo
subido como documento.

Flujo:
1. Selecciona un proceso (vacante) y una etapa (ej. "Movimiento Inteligente").
2. Completa los 6 criterios de la sección "Requisitos" (todos editables,
   varios son opcionales).
3. Clic en "Filtrar": trae los candidatos de esa etapa, los compara contra
   los requisitos y muestra un ranking (Alto/Medio/Bajo).
4. Opcional: marcar "Escribir en Team Tailor" para dejar una nota con el
   resultado en cada candidato.

Ejecutar:
    pip install -r requirements.txt
    cp .env.example .env   # y completar TEAMTAILOR_API_TOKEN
    python app.py
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from scoring import build_note_text, score_candidate
from teamtailor_client import TeamTailorClient

load_dotenv()

app = Flask(__name__)


def get_client():
    return TeamTailorClient()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/jobs")
def api_jobs():
    status = request.args.get("status")
    try:
        client = get_client()
        jobs = client.list_jobs(status=status)
        return jsonify({"ok": True, "jobs": jobs})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/jobs/<job_id>/stages")
def api_stages(job_id):
    try:
        client = get_client()
        stages = client.list_stages(job_id)
        return jsonify({"ok": True, "stages": stages})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/filtrar", methods=["POST"])
def api_filtrar():
    body = request.get_json(force=True)
    job_id = body.get("job_id")
    stage_id = body.get("stage_id")
    requirements = body.get("requirements") or {}
    write_back = bool(body.get("write_back"))

    if not job_id or not stage_id:
        return jsonify({"ok": False, "error": "Falta seleccionar proceso y etapa"}), 400

    try:
        client = get_client()
        applications = client.list_job_applications(job_id, stage_id)
    except Exception as e:  # noqa: BLE001
        return (
            jsonify({"ok": False, "error": f"Error consultando Team Tailor: {e}"}),
            500,
        )

    # Nombre del proceso, para dejarlo registrado en la nota que se escribe
    # en cada candidato (un mismo candidato puede estar en varios procesos a
    # la vez, con requisitos distintos).
    try:
        job_title = client.get_job_title(job_id)
    except Exception:  # noqa: BLE001
        job_title = None

    results = []
    for app_data in applications:
        candidate = app_data["candidate"]
        answers = app_data["answers"]
        result = score_candidate(candidate, answers, requirements)

        name = None
        if candidate:
            attrs = candidate.get("attributes", {})
            name = (
                f"{attrs.get('first-name', '')} {attrs.get('last-name', '')}".strip()
                or attrs.get("email")
            )

        result["candidate_id"] = candidate["id"] if candidate else None
        result["candidate_name"] = name
        result["job_application_id"] = app_data["job_application_id"]
        result["proceso_nombre"] = job_title
        result["write_error"] = None
        # Info de depuración: cuántas respuestas de formulario se lograron
        # traer para este candidato (ayuda a diagnosticar si el problema es
        # que no llegan respuestas, o que el texto no matchea palabras clave).
        result["answers_count"] = len(answers)

        if write_back and candidate:
            note_text = build_note_text(result)
            try:
                client.add_note(candidate["id"], note_text)
                result["note_written"] = True
            except Exception as e:  # noqa: BLE001
                result["note_written"] = False
                result["write_error"] = str(e)

        results.append(result)

    order = {"Alto": 0, "Medio": 1, "Bajo": 2}
    results.sort(key=lambda r: (order.get(r["tier"], 3), -r["score"]))

    return jsonify({"ok": True, "count": len(results), "results": results})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
