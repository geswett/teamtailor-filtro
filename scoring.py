"""
Motor de comparación candidato vs. perfil de cargo, basado en reglas y
palabras clave (sin IA). Es un primer filtro rápido, no un reemplazo del
juicio del reclutador: los candidatos "Alto" y "Medio" igual deben revisarse
a mano antes de avanzarlos de etapa.

Fuentes de texto usadas por candidato (en ese orden de prioridad):
- candidate.attributes["resume-summary"]  -> resumen de CV generado por
  Team Tailor (Co-pilot), si ya fue generado.
- candidate.attributes["pitch"]           -> carta de motivación / resumen
  que el candidato dejó al postular.
- respuestas (answers) del formulario de postulación.
"""

import re

YEARS_RE = re.compile(r"(\d{1,2})\s*años")
DIGITS_RE = re.compile(r"[^\d]")


def _answer_text(answer):
    if not answer:
        return "", ""
    attrs = answer.get("attributes", {})
    question = str(attrs.get("question") or attrs.get("body") or "")

    # El valor de la respuesta puede venir en distintos atributos según el
    # tipo de pregunta en Team Tailor: texto libre ("text"), rango numérico
    # ("range", ej. un slider de renta esperada), selección múltiple
    # ("choices") o sí/no ("boolean"). Probamos en ese orden.
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


def score_candidate(candidate, answers, requirements):
    text = _candidate_text(candidate, answers)
    text_lower = text.lower()

    formacion_list = requirements.get("formacion_excluyente") or []
    formacion_hits = [c for c in formacion_list if c.lower() in text_lower]
    formacion_ok = bool(formacion_hits) if formacion_list else None

    rrll_list = requirements.get("rrll_keywords") or []
    rrll_hits = [k for k in rrll_list if k.lower() in text_lower]

    industria_list = requirements.get("industria_keywords") or []
    industria_hits = [k for k in industria_list if k.lower() in text_lower]

    years_matches = YEARS_RE.findall(text_lower)
    years = max((int(y) for y in years_matches), default=None)

    renta = _extract_salary(answers)
    salario_max = requirements.get("salario_max")
    presupuesto_ok = True
    if renta and salario_max:
        presupuesto_ok = renta <= salario_max * 1.15  # 15% de margen de negociación

    score = 0
    if formacion_ok is True:
        score += 3
    elif formacion_ok is False:
        score -= 1
    score += min(len(rrll_hits), 3)
    score += min(len(industria_hits), 2)
    if years is not None and years >= 10:
        score += 1
    if renta and salario_max:
        score += 1 if presupuesto_ok else -2

    if score >= 7:
        tier = "Alto"
    elif score >= 4:
        tier = "Medio"
    else:
        tier = "Bajo"

    # Debug: lista de (pregunta, respuesta) tal como las ve el motor. Sirve
    # para diagnosticar por qué algo no matcheó (ej. la renta esperada) sin
    # depender de la vista previa del texto combinado, que puede quedar
    # tapada por el resumen de CV si este es largo.
    answers_debug = []
    for a in answers[:40]:
        q, t = _answer_text(a)
        if q or t:
            answers_debug.append({"question": q[:80], "answer": t[:80]})

    return {
        "tier": tier,
        "score": score,
        "formacion_ok": formacion_ok,
        "formacion_hits": formacion_hits,
        "rrll_hits": rrll_hits,
        "industria_hits": industria_hits,
        "years_detected": years,
        "renta_esperada": renta,
        "presupuesto_ok": presupuesto_ok,
        "text_used_preview": text[:500],
        "answers_debug": answers_debug,
    }


def build_note_text(result):
    return (
        f"[Filtro automático Puelche] Match {result['tier']} (puntaje {result['score']}). "
        f"Formación excluyente: "
        f"{'cumple' if result['formacion_ok'] else ('no detectada' if result['formacion_ok'] is False else 'sin lista definida')} "
        f"({', '.join(result['formacion_hits']) or 'sin coincidencias'}). "
        f"Señales RRLL/sindicatos: {', '.join(result['rrll_hits']) or 'ninguna'}. "
        f"Señales industria: {', '.join(result['industria_hits']) or 'ninguna'}. "
        f"Años detectados: {result['years_detected'] if result['years_detected'] is not None else 'no detectado'}. "
        f"Renta esperada: {result['renta_esperada'] if result['renta_esperada'] else 'no informada'} "
        f"({'dentro de rango' if result['presupuesto_ok'] else 'sobre el rango sugerido'})."
    )
