# Filtro de candidatos Team Tailor (Puelche HC)

Interfaz web simple para filtrar candidatos de un proceso (vacante) de Team
Tailor contra un perfil de cargo, sin tener que revisar uno por uno.

## Qué hace

1. Lista los procesos (vacantes) abiertos desde la API de Team Tailor y las
   etapas de cada uno (ej. "Bandeja de entrada", "Movimiento Inteligente").
2. Permite subir el perfil de cargo (Word o PDF) y extrae automáticamente:
   - Formación excluyente (carreras mencionadas en el documento)
   - Palabras clave de relaciones laborales / sindicatos
   - Palabras clave de industria
   - Rango de renta sugerido
   Todo esto queda editable en pantalla antes de correr el filtro.
3. Al hacer clic en "Filtrar", trae los candidatos de la etapa elegida, calcula
   un puntaje contra el perfil, y los ordena en Alto / Medio / Bajo.
4. Opcionalmente, puede dejar una nota con el resultado en cada ficha de
   candidato dentro de Team Tailor (checkbox "Escribir en Team Tailor").

## Importante: el motor de comparación es por reglas, no por IA

Este filtro compara texto por palabras clave (formación, sindicatos,
industria, años de experiencia, renta esperada). Es rápido y gratis, pero no
"entiende" matices como lo haría una persona: no detecta contradicciones entre
respuestas, ni juzga si la experiencia realmente aplica al cargo. Sirve como
un primer corte para priorizar revisión manual, no como decisión final.

Si más adelante quieren mejorar la calidad del veredicto (ej. detectar
matices como "el candidato dice sí pero su propia respuesta lo contradice"),
se puede reemplazar `scoring.py` por una llamada a un modelo de lenguaje
(Claude, GPT, etc.) usando el mismo texto que ya se recopila por candidato.
Eso requiere una API key de ese proveedor y tiene un costo pequeño por
candidato analizado.

## Aviso sobre pruebas

Este código se escribió siguiendo la documentación pública de Team Tailor
(https://docs.teamtailor.com/), pero **no pudo probarse contra una cuenta real**
porque el entorno donde se escribió no tenía salida de red hacia
`api.teamtailor.com`. Antes de usarlo con candidatos reales:

1. Pruébenlo primero con una vacante de prueba o poco crítica.
2. Revisen la pestaña "Resultados" con el checkbox "Escribir en Team Tailor"
   **desmarcado** las primeras veces (modo solo-lectura), para confirmar que
   los datos que trae tienen sentido antes de dejarlo escribir notas.
3. Si `add_tag()` en `teamtailor_client.py` falla, es porque el nombre del
   atributo de etiquetas puede variar según la cuenta; usen `add_note()`
   (comentarios) que es el método documentado y más estable — ya es el que
   usa la app por defecto.

## Instalación local

Requiere Python 3.10+.

```bash
git clone <tu-repo> teamtailor-filtro
cd teamtailor-filtro
python -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edita .env y completa TEAMTAILOR_API_TOKEN (Team Tailor > Configuración >
# Integraciones > API keys, con permisos de Admin lectura/escritura)

python app.py
```

Abre `http://localhost:5000` en el navegador.

## Subir a GitHub

```bash
git init
git add .
git commit -m "Filtro de candidatos Team Tailor"
git branch -M main
git remote add origin <url-de-tu-repo-en-github>
git push -u origin main
```

**El archivo `.env` con tu API key real nunca se sube** (está en
`.gitignore`). Cada persona/servidor que corra la app debe crear su propio
`.env` a partir de `.env.example`.

## Desplegar para que todo el equipo lo use

La forma más simple es correrlo en un servidor o computador de la empresa que
tenga salida a internet y esté siempre encendido, por ejemplo:

- Un servidor interno / VPS pequeño (ej. una instancia barata en cualquier
  proveedor cloud), corriendo `python app.py` (o mejor, con `gunicorn` en
  producción: `pip install gunicorn` y `gunicorn -w 2 -b 0.0.0.0:5000 app:app`).
- Servicios que despliegan directo desde GitHub (Render, Railway, Fly.io,
  PythonAnywhere, etc.): conectan el repo, configuran las variables de
  entorno del `.env.example` en su panel, y listo.

En cualquier caso, todo el equipo entra a la misma URL/IP del servidor donde
quede corriendo la app.

## Estructura del proyecto

```
teamtailor-filtro/
├── app.py                # Backend Flask (rutas /api/jobs, /api/perfil, /api/filtrar)
├── teamtailor_client.py  # Llamadas a la API de Team Tailor
├── perfil_parser.py      # Extrae texto y requisitos desde el perfil de cargo (.docx/.pdf)
├── scoring.py            # Motor de comparación candidato-vs-perfil (reglas/palabras clave)
├── requirements.txt
├── .env.example
├── templates/index.html  # Interfaz
└── static/
    ├── style.css
    └── app.js
```
