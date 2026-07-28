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
import requests


class TeamTailorClient:
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

    def _get(self, path, params=None):
        r = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(
                f"Team Tailor API error {r.status_code} en GET {path}: {r.text[:500]}"
            )
        return r.json()

    def _get_url(self, url):
        r = requests.get(url, headers=self._headers(), timeout=30)
        if not r.ok:
            raise RuntimeError(
                f"Team Tailor API error {r.status_code} en GET {url}: {r.text[:500]}"
            )
        return r.json()

    def _post(self, path, payload):
        r = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers(with_body=True),
            json=payload,
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(
                f"Team Tailor API error {r.status_code} en POST {path}: {r.text[:500]}"
            )
        return r.json() if r.text else {}

    def _patch(self, path, payload):
        r = requests.patch(
            f"{self.base_url}{path}",
            headers=self._headers(with_body=True),
            json=payload,
            timeout=30,
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
    def list_job_applications(self, job_id, stage_id):
        applications = []
        params = {
            "filter[job]": job_id,
            "filter[stage]": stage_id,
            "include": "candidate,answers",
            "page[size]": 30,
        }
        data = self._get("/job-applications", params=params)
        applications.extend(self._merge_included(data))

        next_link = data.get("links", {}).get("next")
        while next_link:
            data = self._get_url(next_link)
            applications.extend(self._merge_included(data))
            next_link = data.get("links", {}).get("next")

        return applications

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
        attrs = current.get("data", {}).get("attributes", {})
        existing = attrs.get("tag-list") or attrs.get("tags") or []
        if isinstance(existing, str):
            existing_set = {t.strip() for t in existing.split(",") if t.strip()}
        else:
            existing_set = set(existing or [])
        existing_set.add(tag)

        payload = {
            "data": {
                "type": "candidates",
                "id": candidate_id,
                "attributes": {"tag-list": sorted(existing_set)},
            }
        }
        return self._patch(f"/candidates/{candidate_id}", payload)
