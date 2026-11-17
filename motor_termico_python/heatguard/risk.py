"""Lugar para evaluación ocupacional; no emitir alertas de seguridad sin validar."""


def evaluate_occupational_risk() -> dict:
    return {
        "status": "not_configured",
        "score_0_100": None,
        "safety_alert_enabled": False,
        "explanation": (
            "Pendiente: criterios de exposición aplicables, tarea/carga metabólica, "
            "ropa/EPP, aclimatación, historial y validación del WBGT estimado. "
            "NO interpretar ausencia de alerta como condición segura."
        ),
    }
