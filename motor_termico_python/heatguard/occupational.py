"""Estado ocupacional de INVESTIGACIÓN, NO dispositivo de seguridad validado.

El índice temporal combina Heat Index, actividad declarada y exposición.
No se deben configurar umbrales de seguridad a partir de este puntaje.
"""
from __future__ import annotations

from .occupational_context import evaluate_occupational_context


def research_assessment(result: dict, exposure: dict, context: dict) -> dict:
    metrics = result.get('metrics', {})
    hi = metrics.get('heat_index_c', {}).get('value_c')
    activity = context.get('activity_class', 'unknown')
    accepted = {'resting': 0.05, 'light': 0.25, 'moderate': 0.60,
                'heavy': 0.90, 'very_heavy': 1.0}
    score = None
    if hi is not None and activity in accepted:
        heat_factor = min(1.0, max(0.0, (hi - 27.0) / 18.0))
        time_factor = min(1.0, max(0.0, exposure['minutes_above_threshold'] / 120.0))
        # SOLO presentación exploratoria, NO pesos basados en riesgos clínicos.
        score = round(100 * (0.5 * heat_factor + 0.3 * time_factor + 0.2 * accepted[activity]), 1)
    independent = evaluate_occupational_context(
        context, result.get('environmental_estimator_v18', {})
    )
    return {
        'state': 'research_only', 'score_0_100': score,
        'activity_class': activity, 'task_source': context.get('activity_source', 'not_declared'),
        'clothing': context.get('clothing', 'unknown'),
        'acclimatization': context.get('acclimatization', 'unknown'),
        'score_formula': '0.5*HeatIndexNormalized+0.3*ExperimentalExposure+0.2*DeclaredActivity',
        'score_validated': False, 'automatic_safety_alerts': False,
        'notes': 'No es riesgo fisiológico ni probabilidad de golpe de calor. Solo visualización de I+D.',
        'context_model': independent,
    }
