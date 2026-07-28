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
        if not
