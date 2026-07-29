"""
Motor de comparación candidato vs. requisitos definidos manualmente por el
reclutador, basado en reglas explícitas (sin IA, sin perfil de cargo).

Seis criterios, cada uno editable en la interfaz antes de filtrar:

- Renta esperada (de la respuesta del formulario): rango definido por el
  reclutador, con un margen de tolerancia de 30% hacia arriba y hacia abajo.
  Fuera de ese margen -> RECHAZO automático.
- Edad (calculada desde la fecha de nacimiento): rango definido por el
  reclutador, con un margen de tolerancia de 10% hacia arriba y hacia abajo.
  Fuera de ese margen -> RECHAZO automático.
- Carrera: una o más carreras aceptadas (opcional). Si el candidato menciona
  alguna, cumple; si no, sigue en la lista pero con match más bajo (no se
  rechaza).
- Universidad: misma lógica que carrera (opcional).
- Ciudad de residencia: una o más ciudades aceptadas (opcional). Si el
  candidato menciona alguna, cumple; si no, sigue en la lista pero con match
  más bajo (no se rechaza).
- Palabras clave (hasta 3, opcional): TODAS deben aparecer en el CV o
  respuestas del candidato. Si falta alguna, el candidato sigue en la lista
  pero con match más bajo (no se rechaza).

Un candidato "Alto"/"Medio" igual debe revisarse a mano: esto es un primer
filtro rápido, no reemplaza el juicio del reclutador.

Fuentes de texto usadas por candidato (en ese orden de prioridad):
- candidate.attributes["resume-summary"]  -> resumen de CV generado por
  Team Tailor (Co-pilot), si ya fue generado.
- candidate.attributes["pitch"]           -> carta de motivación / resumen
  que el candidato dejó al postular.
- respuestas (answers) del formulario de postulación.
"""

import datetime
import re

DIGITS_RE = re.compile(r"[^\d]")


def _dedupe_specific(items):
    """Si un ítem es substring de otro ítem más largo de la misma lista,
    se descarta el más corto (nos quedamos con la variante más específica)."""
    unique_sorted = sorted(set(items), key=len, reverse=True)
    kept = []
    for item in unique_sorted:
        if not any(item != k and item in k for k in kept):
            kept.append(item)
    return sorted(kept, key=lambda i: items.index(i))


def _answer_text(answer):
    if not answer:
        return "", ""
    attrs = answer.get("attributes", {})
    question = str(attrs.get("question") or attrs.get("body") or "")

    # El valor de la respuesta puede venir en distintos atributos según el
    # tipo de pregunta en Team Tailor: texto libre ("text"), rango numérico
    # ("range"), selección múltiple ("choices") o sí/no ("boolean").
    if attrs.get("text"):
        text = str(attrs.get("text"))
    elif attrs.get("answer"):
        text = str(attrs.get("answer"))
    elif attrs.get("range") is not None:
        text = str(attrs.get("range"))
    elif attrs.get("choices"):
        text = ", ".join(str(c) for c in attrs.get("choices"))
    elif attrs.get("boolean") is not None:
        text = "Sí" if attrs.get("boolean") else "No"
    else:
        text = ""

    return question, text


def _candidate_text(candidate, answers):
    parts = []
    if candidate:
        attrs = candidate.get("attributes", {})
        for field in ("resume-summary", "pitch"):
            val = attrs.get(field)
            if val:
                parts.append(str(val))
    for a in answers:
        _, text = _answer_text(a)
        if text:
            parts.append(text)
    return "\n".join(parts)


SALARY_QUESTION_KEYWORDS = [
    "renta",
    "sueldo",
    "pretensión",
    "pretension",
    "expectativa salarial",
    "expectativas salariales",
    "aspiración salarial",
    "aspiracion salarial",
    "remuneración",
    "remuneracion",
    "salario",
    "líquido esperado",
    "liquido esperado",
]


def _extract_salary(answers):
    for a in answers:
        question, text = _answer_text(a)
        q_lower = question.lower()
        if any(kw in q_lower for kw in SALARY_QUESTION_KEYWORDS):
            digits = DIGITS_RE.sub("", text)
            if digits.isdigit() and len(digits) >= 6:
                return int(digits)
    return None


BIRTHDATE_QUESTION_KEYWORDS = [
    "fecha de nacimiento",
    "fecha nacimiento",
    "nacimiento",
    "date of birth",
    "birthday",
]

AGE_QUESTION_KEYWORDS = ["edad", "age"]

# Formatos de fecha comunes en la respuesta de "fecha de nacimiento"
# (dd/mm/aaaa, dd-mm-aaaa, aaaa-mm-dd, aaaa/mm/dd).
DATE_PATTERNS = [
    ("%d/%m/%Y", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
    ("%d-%m-%Y", re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")),
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")),
    ("%Y/%m/%d", re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")),
]


def _parse_date(text):
    text = (text or "").strip()
    for fmt, pattern in DATE_PATTERNS:
        if pattern.match(text):
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _age_from_birthdate(birthdate):
    today = datetime.date.today()
    return today.year - birthdate.year - (
        (today.month, today.day) < (birthdate.month, birthdate.day)
    )


def _extract_age(candidate, answers):
    # 1) Si hay una respuesta directa a "Edad" que sea un número, se usa tal
    # cual (evita depender de que exista una pregunta de fecha de nacimiento).
    for a in answers:
        question, text = _answer_text(a)
        q_lower = question.lower()
        if any(kw in q_lower for kw in AGE_QUESTION_KEYWORDS):
            digits = DIGITS_RE.sub("", text)
            if digits.isdigit() and 0 < int(digits) < 100:
                return int(digits)

    # 2) Si hay una pregunta de fecha de nacimiento, se calcula la edad.
    for a in answers:
        question, text = _answer_text(a)
        q_lower = question.lower()
        if any(kw in q_lower for kw in BIRTHDATE_QUESTION_KEYWORDS):
            birthdate = _parse_date(text)
            if birthdate:
                return _age_from_birthdate(birthdate)

    # 3) Respaldo: si el candidato trae un atributo nativo de fecha de
    # nacimiento (poco común, pero puede darse con integraciones externas).
    if candidate:
        attrs = candidate.get("attributes", {})
        for field in ("date-of-birth", "birthday", "birth-date"):
            val = attrs.get(field)
            if val:
                birthdate = _parse_date(str(val)[:10].replace("T", "-"))
                if birthdate:
                    return _age_from_birthdate(birthdate)
    return None


# Palabras cuya terminación varía por género y que suelen encabezar el
# nombre de una carrera. Si el reclutador escribe "ingeniería comercial" y
# el CV dice "Ingeniero Comercial", igual debe contar como coincidencia.
CAREER_GENDER_VARIANTS = {
    "ingeniería": ["ingenier[íi]a", "ingeniero", "ingeniera"],
    "ingeniero": ["ingenier[íi]a", "ingeniero", "ingeniera"],
    "ingeniera": ["ingenier[íi]a", "ingeniero", "ingeniera"],
    "licenciatura": ["licenciatura", "licenciado", "licenciada"],
    "licenciado": ["licenciatura", "licenciado", "licenciada"],
    "licenciada": ["licenciatura", "licenciado", "licenciada"],
    "técnico": ["técnico", "técnica"],
    "técnica": ["técnico", "técnica"],
    "contador": ["contador", "contadora"],
    "contadora": ["contador", "contadora"],
    "administrador": ["administrador", "administradora"],
    "administradora": ["administrador", "administradora"],
    "psicólogo": ["psicólogo", "psicóloga"],
    "psicóloga": ["psicólogo", "psicóloga"],
    "abogado": ["abogado", "abogada"],
    "abogada": ["abogado", "abogada"],
    "arquitecto": ["arquitecto", "arquitecta"],
    "arquitecta": ["arquitecto", "arquitecta"],
    "diseñador": ["diseñador", "diseñadora"],
    "diseñadora": ["diseñador", "diseñadora"],
}


def _flexible_phrase_regex(phrase):
    """Arma un patrón que ignora la variación de género en palabras como
    ingeniero/a, licenciado/a, técnico/a, etc., para que 'ingeniería
    comercial' matchee tanto 'Ingeniero Comercial' como 'Ingeniera
    Comercial' en el CV."""
    words = [w for w in phrase.strip().split() if w]
    if not words:
        return None
    parts = []
    for w in words:
        variants = CAREER_GENDER_VARIANTS.get(w.lower())
        parts.append("(?:" + "|".join(variants) + ")" if variants else re.escape(w))
    try:
        return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)
    except re.error:
        return None


def _keyword_match_status(candidate_list, text_lower, label_singular):
    """Para Carrera/Universidad: si la lista está vacía, el campo no aplica
    (None). Si el candidato menciona alguna, cumple (True). Si no, no cumple
    (False), pero eso NO implica rechazo, solo baja el puntaje."""
    if not candidate_list:
        return None, [], "sin definir"
    hits = []
    for item in candidate_list:
        if item.lower() in text_lower:
            hits.append(item)
            continue
        pattern = _flexible_phrase_regex(item)
        if pattern and pattern.search(text_lower):
            hits.append(item)
    hits = _dedupe_specific(hits)
    if hits:
        return True, hits, f"cumple ({', '.join(hits)})"
    return False, [], f"no cumple ({label_singular} no detectada en el CV)"


def score_candidate(candidate, answers, requirements):
    text = _candidate_text(candidate, answers)
    text_lower = text.lower()

    # --- Renta esperada (margen 30%, fuera de rango = RECHAZO) ---
    renta = _extract_salary(answers)
    renta_min = requirements.get("renta_min")
    renta_max = requirements.get("renta_max")
    renta_rechazo = False
    if renta_min is None and renta_max is None:
        renta_status = "sin rango definido"
    elif renta is None:
        renta_status = "no informada"
    else:
        lo = (renta_min * 0.7) if renta_min is not None else None
        hi = (renta_max * 1.3) if renta_max is not None else None
        dentro = (lo is None or renta >= lo) and (hi is None or renta <= hi)
        renta_fmt = f"{renta:,.0f}".replace(",", ".")
        if dentro:
            renta_status = f"cumple ({renta_fmt})"
        else:
            renta_status = f"fuera de rango ({renta_fmt})"
            renta_rechazo = True

    # --- Edad (margen 10%, fuera de rango = RECHAZO) ---
    edad = _extract_age(candidate, answers)
    edad_min = requirements.get("edad_min")
    edad_max = requirements.get("edad_max")
    edad_rechazo = False
    if edad_min is None and edad_max is None:
        edad_status = "sin rango definido"
    elif edad is None:
        edad_status = "no informada"
    else:
        lo = (edad_min * 0.9) if edad_min is not None else None
        hi = (edad_max * 1.1) if edad_max is not None else None
        dentro = (lo is None or edad >= lo) and (hi is None or edad <= hi)
        if dentro:
            edad_status = f"cumple ({edad} años)"
        else:
            edad_status = f"fuera de rango ({edad} años)"
            edad_rechazo = True

    # --- Carrera / Universidad (opcionales, bajan el match si no cumplen) ---
    carreras_list = requirements.get("carreras") or []
    carrera_ok, carrera_hits, carrera_status = _keyword_match_status(
        carreras_list, text_lower, "la carrera"
    )

    universidades_list = requirements.get("universidades") or []
    universidad_ok, universidad_hits, universidad_status = _keyword_match_status(
        universidades_list, text_lower, "la universidad"
    )

    # --- Ciudad(es) de residencia (opcional, baja el match si no cumple) ---
    ciudades_list = requirements.get("ciudades") or []
    ciudad_ok, ciudad_hits, ciudad_status = _keyword_match_status(
        ciudades_list, text_lower, "la ciudad"
    )

    # --- Palabras clave (hasta 3): si falta alguna, baja el match pero NO
    # se rechaza automáticamente (igual que carrera/universidad/ciudad). ---
    keywords = [k for k in (requirements.get("palabras_clave") or []) if k][:3]
    keywords_hits = [k for k in keywords if k.lower() in text_lower]
    if not keywords:
        keywords_ok = None
        keywords_status = "sin definir"
    elif len(keywords_hits) == len(keywords):
        keywords_ok = True
        keywords_status = f"cumple todas ({', '.join(keywords_hits)})"
    else:
        keywords_ok = False
        faltantes = [k for k in keywords if k not in keywords_hits]
        keywords_status = f"no cumple (faltan: {', '.join(faltantes)})"

    # --- Puntaje y tier ---
    score = 0
    if renta_status.startswith("cumple"):
        score += 2
    if edad_status.startswith("cumple"):
        score += 1
    if carrera_ok is True:
        score += 2
    elif carrera_ok is False:
        score -= 1
    if universidad_ok is True:
        score += 1
    elif universidad_ok is False:
        score -= 1
    if ciudad_ok is True:
        score += 1
    elif ciudad_ok is False:
        score -= 1
    if keywords_ok is True:
        score += 2
    elif keywords_ok is False:
        score -= 1

    if score >= 6:
        tier = "Alto"
    elif score >= 3:
        tier = "Medio"
    else:
        tier = "Bajo"

    # Solo renta o edad fuera de margen producen RECHAZO automático, sin
    # importar el resto del puntaje. Carrera, universidad, ciudad y palabras
    # clave que no coincidan solo bajan el match (el candidato sigue en la
    # lista, no se rechaza).
    rechazo = renta_rechazo or edad_rechazo
    if rechazo:
        tier = "Bajo"

    return {
        "tier": tier,
        "score": score,
        "rechazo": rechazo,
        "renta_esperada": renta,
        "renta_status": renta_status,
        "renta_rechazo": renta_rechazo,
        "edad_detectada": edad,
        "edad_status": edad_status,
        "edad_rechazo": edad_rechazo,
        "carrera_ok": carrera_ok,
        "carrera_hits": carrera_hits,
        "carrera_status": carrera_status,
        "universidad_ok": universidad_ok,
        "universidad_hits": universidad_hits,
        "universidad_status": universidad_status,
        "ciudad_ok": ciudad_ok,
        "ciudad_hits": ciudad_hits,
        "ciudad_status": ciudad_status,
        "keywords_hits": keywords_hits,
        "keywords_status": keywords_status,
        "keywords_ok": keywords_ok,
        "text_used_preview": text[:500],
    }


def build_note_text(result):
    prefijo = "RECHAZO. " if result.get("rechazo") else ""
    proceso = result.get("proceso_nombre")
    proceso_linea = f"Proceso: {proceso}\n" if proceso else ""
    return (
        f"{proceso_linea}"
        f"{prefijo}[Filtro automático Puelche] Match {result['tier']} (puntaje {result['score']}).\n"
        f"Renta esperada: {result['renta_status']}.\n"
        f"Edad: {result['edad_status']}.\n"
        f"Carrera: {result['carrera_status']}.\n"
        f"Universidad: {result['universidad_status']}.\n"
        f"Ciudad de residencia: {result['ciudad_status']}.\n"
        f"Palabras clave: {result['keywords_status']}."
    )
