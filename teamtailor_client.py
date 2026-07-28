"""
Cliente simple para la API pública de Team Tailor (JSON:API).

Documentación oficial: https://docs.teamtailor.com/
- Auth: header Authorization: Token token=<API_KEY>
- Header obligatorio: X-Api-Version: <fecha_version>
- Base URL EU: https://api.teamtailor.com
- Base URL NA: https://api.na.teamtailor.com

NOTA IMPORTANTE: este cliente fue escrito siguiendo la documentación pública de
Team Tailor, pero no pudo probarse contra una cuenta real (el entorno donde se
escribió no tenía salida de red hacia api.teamtailor.com). Antes de usarlo en
producción, pruébenlo primero contra una vacante de prueba y revisen los
nombres de atributos (algunos pueden variar levemente según la versión de API
o configuración de la cuenta, especialmente en add_tag()).
"""

import os
import time

import requests


class TeamTailorClient:
    # Team Tailor limita a 50 requests cada 10 segundos. Con muchos
    # candidatos hacemos varias llamadas por candidato (respuestas + nota),
    # así que reintentamos con espera cuando llega un 429 y espaciamos un
    # poco cada llamada para no volver a pasarnos del límite.
    RATE_LIMIT_MAX_RETRIES = 5
    MIN_DELAY_BETWEEN_REQUESTS = 0.2  # segundos

    def __init__(self, token=None, stack=None, api_version=None):
        self.token = token or os.environ.get("TEAMTAILOR_API_TOKEN")
        stack = (stack or os.environ.get("TEAMTAILOR_STACK", "eu")).lower()
        self.base_url = (
            "https://api.na.teamtailor.com/v1"
            if stack == "na"
            else "https://api.teamtailor.com/v1"
        )
        self.api_version = api_version or os.environ.get(
            "TEAMTAILOR_API_VERSION", "20240904"
        )

        if not self.token:
            raise RuntimeError(
                "Falta TEAMTAILOR_API_TOKEN. Configúralo en el archivo .env "
                "(ver .env.example)."
            )

    def _headers(self, with_body=False):
        headers = {
            "Authorization": f"Token token={self.token}",
            "X-Api-Version": self.api_version,
            "Accept": "application/vnd.api+json",
        }
        if with_body:
            headers["Content-Type"] = "application/vnd.api+json"
        return headers

    def _request(self, method, url, **kwargs):
        """Hace la llamada HTTP con reintento automático si Team Tailor
        responde 429 (rate limit), y una pequeña pausa entre llamadas para
        no volver a pasarnos del límite (50 requests / 10 segundos)."""
        last_response = None
        for attempt in range(self.RATE_LIMIT_MAX_RETRIES + 1):
            time.sleep(self.MIN_DELAY_BETWEEN_REQUESTS)
            r = requests.request(method, url, timeout=30, **kwargs)
            last_response = r
            if r.status_code != 429:
                return r
            wait_s = 2.0
            reset_header = r.headers.get("X-Rate-Limit-Reset")
            if reset_header:
                try:
                    wait_s = max(float(reset_header), 1.0)
                except ValueError:
                    pass
            time.sleep(wait_s)
        return last_response

    def _get(self, path, params=None):
        r = self._request(
            "GET",
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params,
        )
        if not r.ok:
            raise RuntimeError(
                f"Team Tailor API error {r.status_code} en GET {path}: {r.text[:500]}"
            )
        return r.json()

    def _get_url(self, url):
        r = self._request("GET", url, headers=self._headers())
        if not r.ok:
            raise RuntimeError(
                f"Team Tailor API error {r.status_code} en GET {url}: {r.text[:500]}"
            )
        return r.json()

    def _post(self, path, payload):
        r = self._request(
            "POST",
            f"{self.base_url}{path}",
            headers=self._headers(with_body=True),
            json=payload,
        )
        if not r.ok:
            raise RuntimeError(
                f"Team Tailor API error {r.status_code} en POST {path}: {r.text[:500]}"
            )
        return r.json() if r.text else {}

    def _patch(self, path, payload):
        r = self._request(
            "PATCH",
            f"{self.base_url}{path}",
            headers=self._headers(with_body=True),
            json=payload,
        )
        if not r.ok:
            raise RuntimeError(
                f"Team Tailor API error {r.status_code} en PATCH {path}: {r.text[:500]}"
            )
        return r.json() if r.text else {}

    # ------------------------------------------------------------------
    # Procesos (jobs) y etapas (stages)
    # ------------------------------------------------------------------
    def list_jobs(self, status=None):
        """Lista simplificada de vacantes ('procesos').

        No filtramos por status vía la API: en esta cuenta de Team Tailor el
        filtro filter[status]=open no es un valor aceptado (varía según
        configuración de la cuenta). Traemos todos los jobs y, si se pide un
        status, filtramos localmente sobre el atributo ya devuelto.
        """
        jobs = []
        params = {"page[size]": 30}
        data = self._get("/jobs", params=params)
        jobs.extend(data.get("data", []))

        next_link = data.get("links", {}).get("next")
        while next_link:
            data = self._get_url(next_link)
            jobs.extend(data.get("data", []))
            next_link = data.get("links", {}).get("next")

        result = [
            {
                "id": j["id"],
                "title": j.get("attributes", {}).get("title"),
                "status": j.get("attributes", {}).get("status"),
            }
            for j in jobs
        ]
        if status:
            result = [j for j in result if j.get("status") == status]
        return result

    def list_stages(self, job_id):
        data = self._get("/stages", params={"filter[job]": job_id, "page[size]": 30})
        stages = data.get("data", [])
        return [
            {
                "id": s["id"],
                "name": s.get("attributes", {}).get("name"),
                "active_count": s.get("attributes", {}).get(
                    "active-job-applications-count"
                ),
            }
            for s in stages
        ]

    # ------------------------------------------------------------------
    # Candidaturas (job-applications) de una etapa
    # ------------------------------------------------------------------
    def list_job_applications(self, job_id, stage_id, only_active=True):
        """Trae las candidaturas de una etapa, con el candidato incluido.

        Por defecto excluye candidaturas rechazadas (atributo `rejected-at`
        no nulo): esto se filtra localmente porque `filter[status]` de
        job-applications no está documentado/soportado de forma confiable en
        todas las cuentas, a diferencia del atributo `rejected-at` que sí
        viene siempre en la respuesta.

        Nota: 'answers' NO es una relación válida de job-applications en la
        API de Team Tailor (solo lo son candidate, job, stage, reject-reason).
        Las respuestas del formulario de postulación viven en el candidato
        (relación 'answers' de /candidates/{id}), así que se piden aparte,
        una consulta por candidato, vía get_candidate_answers().
        """
        applications = []
        params = {
            "filter[job]": job_id,
            "filter[stage]": stage_id,
            "include": "candidate",
            "page[size]": 30,
        }
        data = self._get("/job-applications", params=params)
        applications.extend(self._merge_included(data))

        next_link = data.get("links", {}).get("next")
        while next_link:
            data = self._get_url(next_link)
            applications.extend(self._merge_included(data))
            next_link = data.get("links", {}).get("next")

        if only_active:
            applications = [a for a in applications if not a.get("rejected_at")]

        for app_data in applications:
            candidate = app_data.get("candidate")
            if candidate:
                try:
                    app_data["answers"] = self.get_candidate_answers(candidate["id"])
                except Exception:
                    app_data["answers"] = []
            else:
                app_data["answers"] = []

        return applications

    def get_candidate_answers(self, candidate_id):
        """Trae las respuestas del formulario de postulación de un candidato,
        con el texto de la pregunta ya incrustado en attributes['question']
        (para que scoring.py pueda leerlo directo)."""
        data = self._get(
            f"/candidates/{candidate_id}", params={"include": "answers,questions"}
        )
        included = data.get("included", [])
        included_map = {(i["type"], i["id"]): i for i in included}
        candidate_data = data.get("data", {})
        answer_refs = (
            candidate_data.get("relationships", {}).get("answers", {}).get("data", [])
            or []
        )

        results = []
        for ref in answer_refs:
            answer = included_map.get((ref["type"], ref["id"]))
            if not answer:
                continue
            q_ref = (answer.get("relationships", {}).get("question", {}) or {}).get(
                "data"
            )
            question = (
                included_map.get((q_ref["type"], q_ref["id"])) if q_ref else None
            )
            q_attrs = question.get("attributes", {}) if question else {}
            question_text = (
                q_attrs.get("body") or q_attrs.get("title") or q_attrs.get("text") or ""
            )

            answer_copy = dict(answer)
            attrs_copy = dict(answer.get("attributes", {}))
            attrs_copy["question"] = question_text
            answer_copy["attributes"] = attrs_copy
            results.append(answer_copy)

        return results

    @staticmethod
    def _merge_included(data):
        included = {(i["type"], i["id"]): i for i in data.get("included", [])}
        results = []
        for app in data.get("data", []):
            candidate_ref = (
                app.get("relationships", {}).get("candidate", {}).get("data")
            )
            candidate = (
                included.get((candidate_ref["type"], candidate_ref["id"]))
                if candidate_ref
                else None
            )
            answer_refs = (
                app.get("relationships", {}).get("answers", {}).get("data", []) or []
            )
            answers = [included.get((a["type"], a["id"])) for a in answer_refs]
            answers = [a for a in answers if a]
            results.append(
                {
                    "job_application_id": app["id"],
                    "candidate": candidate,
                    "answers": answers,
                    "rejected_at": app.get("attributes", {}).get("rejected-at"),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Escritura de vuelta hacia Team Tailor
    # ------------------------------------------------------------------
    def add_note(self, candidate_id, body):
        """Agrega un comentario/nota visible en la ficha del candidato."""
        payload = {
            "data": {
                "type": "notes",
                "attributes": {"text": body},
                "relationships": {
                    "candidate": {"data": {"type": "candidates", "id": candidate_id}}
                },
            }
        }
        return self._post("/notes", payload)

    def add_tag(self, candidate_id, tag):
        """Intenta agregar una etiqueta al candidato.

        Team Tailor maneja etiquetas de candidato como una lista de strings.
        Esto puede requerir ajuste según la versión/cuenta real (revisar
        respuesta de GET /candidates/{id} para confirmar el nombre exacto del
        atributo antes de usar esto en producción).
        """
        current = self._get(f"/candidates/{candidate_id}")
