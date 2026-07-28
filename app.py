"""
Interfaz web para filtrar candidatos de Team Tailor según un perfil de cargo.

Flujo:
1. Selecciona un proceso (vacante) y una etapa (ej. "Movimiento Inteligente").
2. Sube el perfil de cargo (.docx o .pdf); se extraen automáticamente
   formación excluyente, palabras clave de RRLL/industria y rango salarial
   (todo editable antes de filtrar).
3. Clic en "Filtrar": trae los candidatos de esa etapa, los compara contra el
   perfil y muestra un ranking (Alto/Medio/Bajo).
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

from perfil_parser import extract_perfil_text, parse_requirements
from scoring import build_note_text, score_candidate
from teamtailor_client import TeamTailorClient

load_dotenv()

app = Flask(__name__)

# Guardamos el último perfil cargado en memoria del proceso (suficiente para
# un equipo pequeño usando la app desde el mismo servidor). Si más de una
# persona la usa al mismo tiempo con perfiles distintos, conviene mandar
# 'requirements' completo desde el frontend en cada /api/filtrar (ya lo hace).
LAST_REQUIREMENTS = {}


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


@app.route("/api/perfil", methods=["POST"])
def api_perfil():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No se recibió archivo"}), 400
    file = request.files["file"]
    try:
        text = extract_perfil_text(file.filename, file.read())
        requirements = parse_requirements(text)
        global LAST_REQUIREMENTS
        LAST_REQUIREMENTS = requirements
        return jsonify({"ok": True, "requirements": requirements})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/filtrar", methods=["POST"])
def api_filtrar():
    body = request.get_json(force=True)
    job_id = body.get("job_id")
    stage_id = body.get("stage_id")
    requirements = body.get("requirements") or LAST_REQUIREMENTS
    write_back = bool(body.get("write_back"))

    if not job_id or not stage_id:
        return jsonify({"ok": False, "error": "Falta seleccionar proceso y etapa"}), 400
    if not requirements:
        return (
            jsonify({"ok": False, "error": "Falta cargar el perfil de cargo primero"}),
            400,
        )

    try:
        client = get_client()
        applications = client.list_job_applications(job_id, stage_id)
    except Exception as e:  # noqa: BLE001
        return (
            jsonify({"ok": False, "error": f"Error consultando Team Tailor: {e}"}),
            500,
        )

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
        result["write_error"] = None

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
