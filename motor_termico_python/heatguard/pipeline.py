"""Punto único de entrada: sensores + datos externos + supuestos -> indicadores."""
from __future__ import annotations

from typing import Any

from .environmental_v18 import environmental_estimate
from .radiation_v22 import prepare_radiation
from .decision_support_v22 import evaluate_band
from .fusion import select_inputs
from .liljegren import calculate_optional
from .risk import evaluate_occupational_risk
from .schema import iso_datetime, read_event
from .thermal import heat_index_nws_c, shade_proxy_c, wet_bulb_stull_c


def _metric(value: float, method: str, interpretation: str) -> dict:
    return {"value_c": round(value, 2), "method": method, "interpretation": interpretation}


def _observation_record(obs, event_time: str) -> dict:
    record = obs.as_dict()
    observed_at = obs.timestamp or event_time
    age = (iso_datetime(event_time) - iso_datetime(observed_at)).total_seconds()
    record.update({
        "effective_timestamp": observed_at,
        "age_seconds": round(age, 3),
        "condition": {
            "measured": "declared_measurement",
            "external": "external_source",
            "estimated": "model_estimate",
            "neighbor": "other_device_inference",
            "assumed": "explicit_assumption",
        }[obs.kind],
    })
    return record


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    payload, radiation_detail = prepare_radiation(payload)
    device_id, timestamp, zone_id, context, readings = read_event(payload)
    fusion = select_inputs(readings, timestamp, zone_id)
    chosen = fusion.chosen
    values = {key: obs.value for key, obs in chosen.items()}
    warnings = list(fusion.warnings)
    metrics: dict[str, Any] = {}

    if "air_temperature_c" in values and "relative_humidity_pct" in values:
        temp, rh = values["air_temperature_c"], values["relative_humidity_pct"]
        metrics["heat_index_c"] = _metric(
            heat_index_nws_c(temp, rh), "NWS Heat Index (Rothfusz + ajustes)",
            "Índice auxiliar a la sombra; NO es WBGT ni incluye radiación directa.",
        )
        if temp < 26.7:
            warnings.append("Heat Index debajo de ~27 °C: su interpretación ocupacional es limitada.")
        tw = wet_bulb_stull_c(temp, rh)
        if tw is None:
            warnings.append("Stull no calculado fuera de su rango de aplicación definido.")
        else:
            metrics["psychrometric_wet_bulb_c"] = _metric(
                tw, "Stull (2011)",
                "Bulbo húmedo psicrométrico aproximado; NO es bulbo húmedo natural.",
            )
            metrics["shade_experimental_proxy_c"] = _metric(
                shade_proxy_c(temp, tw), "0.7*Tw(Stull)+0.3*Taire (hipótesis de sombra)",
                "PROXY EXPERIMENTAL; NO representa WBGT medido ni WBGT ISO.",
            )

    # Segundo método, solo habilitado expresamente en modo investigación.
    experimental = {'status': 'disabled', 'normative_measurement': False}
    experiment_config = context.get('science', {})
    if not isinstance(experiment_config, dict):
        raise ValueError('context.science debe ser un objeto JSON.')
    if experiment_config.get('enable_simplified_balance') is True:
        required = ('air_temperature_c', 'relative_humidity_pct',
                    'solar_w_m2', 'wind_speed_m_s', 'pressure_hpa')
        missing = [k for k in required if k not in values]
        if missing:
            experimental = {'status': 'missing_inputs', 'missing': missing,
                            'normative_measurement': False}
        elif context.get('environment') != 'outdoor':
            experimental = {'status': 'not_applicable',
                            'message': 'El modelo experimental está habilitado solo en exteriores.'}
        elif experiment_config.get('wind_is_local') is not True:
            experimental = {'status': 'wind_reference_uncertain',
                            'message': 'Para este balance simplificado se exige explícitamente viento local a altura de trabajo.'}
        else:
            from .thermal_science import experimental_balance_c
            try:
                experimental = experimental_balance_c(**{k: values[k] for k in required})
            except (ValueError, ArithmeticError) as exc:
                experimental = {'status': 'model_error', 'details': str(exc)}
            experimental['input_sources'] = {k: {'kind': chosen[k].kind, 'source': chosen[k].source}
                                             for k in required}
            if any(chosen[k].kind == 'assumed' for k in required):
                warnings.append('Balance simplificado con hipótesis explícitas: es solo escenario experimental.')
    wbgt = calculate_optional(values, timestamp, context)
    if wbgt["status"] == "computed":
        used_kinds = {chosen[k].kind for k in (
            "air_temperature_c", "relative_humidity_pct", "solar_w_m2", "wind_speed_m_s", "pressure_hpa"
        )}
        wbgt["input_quality"] = (
            "scenario_with_assumptions" if "assumed" in used_kinds
            else "contains_estimates_or_neighbors" if used_kinds & {"estimated", "neighbor"}
            else "meteorological_inputs_available"
        )
        wbgt["normative_measurement"] = False
        wbgt["model_input_sources"] = {
            k: {"kind": chosen[k].kind, "source": chosen[k].source}
            for k in ("air_temperature_c", "relative_humidity_pct",
                      "solar_w_m2", "wind_speed_m_s", "pressure_hpa")
        }
        if any(chosen[k].source == "OPEN_METEO_HOURLY_MODEL" for k in wbgt["model_input_sources"]):
            wbgt["regional_weather_model_used"] = True
            warnings.append(
                "WBGT emplea pronóstico meteorológico regional, no viento ni radiación "
                "medidos junto al trabajador. No es una medición ISO 7243."
            )
        if "assumed" in used_kinds:
            warnings.append("WBGT Liljegren usa hipótesis. Resultado ilustrativo, NO habilitar alertas de seguridad.")
        else:
            warnings.append("WBGT calculado con modelo físico, aún sin validación propia contra instrumento de referencia.")
    elif wbgt["status"] == "missing_inputs":
        warnings.append("Faltan datos para calcular WBGT mediante Liljegren; no se rellenan silenciosamente.")
    elif wbgt["status"] == "dependency_unavailable":
        warnings.append("Modelo Liljegren disponible al instalar la dependencia opcional 'wbgt'.")
    elif wbgt["status"] == "not_applicable":
        warnings.append("Modelo Liljegren exterior no ejecutado: declarar el ambiente o usar un modelo adecuado para interior.")
    elif wbgt["status"] == "model_error":
        warnings.append("Error del modelo Liljegren: revisar unidades, metadatos y entradas.")

    transport = payload.get("transport_metadata") or {}
    if not isinstance(transport, dict):
        raise ValueError("transport_metadata debe ser un objeto JSON.")
    environmental_v18 = environmental_estimate(values, chosen, timestamp, context,
        simulated=bool(transport.get("simulated", False)))

    return {
        "device_id": device_id, "timestamp": timestamp, "zone_id": zone_id,
        "inputs_selected": {key: _observation_record(obs, timestamp) for key, obs in chosen.items()},
        "inputs_rejected": fusion.rejected,
        "input_contradictions": fusion.contradictions,
        "metrics": metrics,
        "wbgt_outdoor_model": wbgt,
        "environmental_estimator_v18": environmental_v18,
        "radiative_context_v22": radiation_detail,
        "decision_support_v22": evaluate_band(environmental_v18, context, simulated=bool(transport.get("simulated",False))),
        "experimental_balance": experimental,
        "occupational_risk": evaluate_occupational_risk(),
        "limitations": {
            "normative_wbgt_measurement": False,
            "medical_diagnosis": False,
            "warnings": warnings,
        },
    }
