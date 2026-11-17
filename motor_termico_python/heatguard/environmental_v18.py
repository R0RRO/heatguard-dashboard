"""Estimador ambiental integrado HeatGuard v0.18.

Modelo meteorológico NO equivale a WBGT ISO 7243 medido. La función no
rellena variables faltantes, no promedia Ono/Liljegren ni activa alertas.
"""
from __future__ import annotations

from typing import Any

from .liljegren import calculate_optional
from .ono_v09 import wbgt_ono

ONO_REQUIRED = ("air_temperature_c", "relative_humidity_pct", "solar_w_m2", "wind_speed_m_s")
LILJE_REQUIRED = (*ONO_REQUIRED, "pressure_hpa")


def _quality(chosen: dict[str, Any], required: tuple[str, ...], simulated: bool) -> dict:
    source_kinds = {chosen[k].kind for k in required}
    if simulated or "assumed" in source_kinds:
        level = "scenario_only"
        note = "Incluye entradas hipotéticas: resultados solo de demostración."
    elif {"estimated", "neighbor"} & source_kinds:
        level = "unverified_inference"
        note = "Incluye datos inferidos o provenientes de otros dispositivos."
    elif any(chosen[k].kind == "external" for k in required):
        level = "mixed_local_and_external" if any(chosen[k].kind == "measured" for k in required) else "external_only"
        note = "Meteorología externa no necesariamente representativa del puesto; instrumento no validado."
    else:
        level = "all_declared_measured"
        note = "Declarado como medido, pero calibración, ubicación y representatividad no verificadas."
    if simulated and any(chosen[k].kind == "measured" for k in required):
        note += " ADVERTENCIA: telemetría simulada fue etiquetada indebidamente como medida."
    return {"category": level, "interpretation": note,
            "not_confidence_interval": True,
            "no_occupational_safety_certification": True}


def environmental_estimate(values: dict[str, float], chosen: dict[str, Any],
                           timestamp: str, context: dict[str, Any],
                           *, simulated: bool = False) -> dict[str, Any]:
    """Calcula Ono y Liljegren cuando procede; no inventa datos faltantes."""
    environment = context.get("environment")
    result: dict[str, Any] = {
        "status": "missing_inputs", "model": "Ono 2014 outdoor meteorological approximation",
        "not_iso_7243_measurement": True, "alerts_enabled": False,
        "site_sensor_validation": "not_performed",
        "provenance": {}, "warnings": [],
        "liljegren": {"status": "not_evaluated"},
    }
    if environment != "outdoor":
        result.update(status="not_applicable", reason="Requiere context.environment=outdoor; interiores y radiación industrial requieren evaluación local específica.")
        return result
    missing = [k for k in ONO_REQUIRED if k not in values]
    if missing:
        result["missing"] = missing
        result["reason"] = "Sin meteorología completa no se estima WBGT. No se sustituyen valores por defecto."
        return result
    result["provenance"] = {
        k: {"kind": chosen[k].kind, "source": chosen[k].source,
            "timestamp": chosen[k].timestamp, "metadata": chosen[k].metadata}
        for k in ONO_REQUIRED
    }
    result["input_quality"] = _quality(chosen, ONO_REQUIRED, simulated)
    try:
        ono = wbgt_ono(*(values[k] for k in ONO_REQUIRED))
    except (ValueError, ArithmeticError, OverflowError) as e:
        result.update(status="model_error", reason=str(e))
        return result
    result.update(status="computed", value_c=round(ono, 3),
                  interpretation="WBGT estimado con modelo meteorológico Ono; no medido en el puesto.")
    # Interpretación: el promedio regional de radiación horizontal no determina
    # exposición de la persona bajo sombra, techo, equipos calientes, etc.
    for k in ("solar_w_m2", "wind_speed_m_s"):
        if chosen[k].kind == "external":
            result["warnings"].append(f"{k}: valor regional, no medición de la exposición del trabajador.")
    if chosen["air_temperature_c"].kind == "measured":
        result["warnings"].append("Sensor en carcasa/ropa: se debe verificar sesgo térmico por sol, cuerpo y auto-calentamiento.")
    if simulated:
        result["warnings"].append("Telemetría virtual; no hay lecturas del clip físico.")

    # Sensibilidad, NO incertidumbre calibrada; variable solar de celda global
    # puede diferir de exposición bajo sombra. Se omiten los escenarios si no
    # son aplicables y nunca se usan para afirmar seguridad.
    if chosen["solar_w_m2"].kind in ("external", "assumed", "estimated"):
        shade = wbgt_ono(values["air_temperature_c"], values["relative_humidity_pct"],
                         0.0, values["wind_speed_m_s"])
        result["sun_shade_sensitivity"] = {
            "wbgt_if_zero_shortwave_c": round(shade, 3),
            "difference_to_reported_c": round(shade-ono, 3),
            "status": "hypothetical_sensitivity_not_confidence_interval",
            "note": "Poner irradiancia=0 no reproduce automáticamente la radiación térmica de una sombra real.",
        }

    lilje = calculate_optional(values, timestamp, context)
    # Mantener visible que Liljegren usa la misma procedencia cuando esté completo.
    result["liljegren"] = lilje
    if lilje.get("status") == "computed":
        result["liljegren"]["model_input_provenance"] = {
            k: {"kind": chosen[k].kind, "source": chosen[k].source}
            for k in LILJE_REQUIRED
        }
        result["model_spread_c"] = round(lilje["value_c"] - ono, 3)
        result["model_spread_note"] = "Diferencia entre modelos, NO cota de error ni intervalo de confianza."
    return result
