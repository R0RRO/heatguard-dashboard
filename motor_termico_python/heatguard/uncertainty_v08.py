"""HeatGuard v0.8: incertidumbre *condicional a supuestos* sobre entradas.

IMPORTANTE: estas bandas NO son intervalos estadísticos calibrados ni cuantifican
error frente a WBGT observado. Los factores de perturbación son HIPÓTESIS
del investigador; los modos 'sensor' son sensores IDEALES hipotéticos y NO
representan prestaciones verificadas de VEML7700 ni un anemómetro.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from statistics import mean

from .weather_history_v07 import load_weather_csv
from .research_history_v07 import wind_log_profile
from .thermal_science import experimental_balance_c
from .liljegren import calculate_optional
from .sensitivity import quantile

# Intervalos de multiplicadores ilustrativos, NO derivados de datos medidos.
UNCERTAINTY_SCHEMES = {
    "regional_only": {"solar_factor": (.25, 1.35), "wind_factor": (.35, 1.70)},
    "ideal_solar_measurement": {"solar_factor": (.90, 1.10), "wind_factor": (.35, 1.70)},
    "ideal_local_wind_measurement": {"solar_factor": (.25, 1.35), "wind_factor": (.80, 1.20)},
    "ideal_both_measurements": {"solar_factor": (.90, 1.10), "wind_factor": (.80, 1.20)},
}


def _triangle_from_uniform(u: float, lo: float, hi: float, mode: float = 1.0) -> float:
    """Inversa CDF triangular, solo para explorar el efecto de distribuciones supuestas."""
    if not 0 <= u <= 1 or not lo <= mode <= hi: raise ValueError("Distribución triangular inválida")
    p = (mode - lo) / (hi - lo)
    if u < p: return lo + math.sqrt(u * (hi - lo) * (mode - lo))
    return hi - math.sqrt((1 - u) * (hi - lo) * (hi - mode))


def _estimate(row: dict, model: str, solar: float, wind10: float, *, roughness_m: float, urban: int) -> float:
    if model == "balance":
        v2 = wind_log_profile(wind10, z0_m=roughness_m)
        if v2 < 0.1: raise ValueError("Viento local fuera del dominio del proxy (v<0.1 m/s)")
        out = experimental_balance_c(
            air_temperature_c=float(row["air_temperature_c"]),
            relative_humidity_pct=float(row["relative_humidity_pct"]),
            solar_w_m2=solar, wind_speed_m_s=v2,
            pressure_hpa=float(row["pressure_hpa"]),
        )
        return float(out["wbgt_like_experimental_c"])
    if model == "liljegren":
        vals = dict(air_temperature_c=float(row["air_temperature_c"]),
                    relative_humidity_pct=float(row["relative_humidity_pct"]),
                    solar_w_m2=solar, wind_speed_m_s=wind10,
                    pressure_hpa=float(row["pressure_hpa"]))
        context = {
            "environment": "outdoor",
            "location": dict(latitude_deg=float(row["latitude_deg"]),
                             longitude_deg=float(row["longitude_deg"]), utc_offset_hours=0),
            "weather_model": dict(wind_height_m=10, averaging_minutes=60,
                                  urban=urban, vertical_temperature_difference_c=0),
        }
        result = calculate_optional(vals, str(row["timestamp_utc"]), context)
        if result["status"] != "computed": raise ValueError(f"Liljegren: {result}")
        return float(result["value_c"])
    raise ValueError("Modelo debe ser 'balance' o 'liljegren'")


def analyze_uncertainty(rows: list[dict], *, model: str = "balance", n_samples: int = 100,
                        seed: int = 42, roughness_m: float = .1, urban: int = 1) -> dict:
    if not rows: raise ValueError("Sin datos meteorológicos")
    if model not in ("balance", "liljegren"): raise ValueError("Modelo no reconocido")
    if not 20 <= n_samples <= 10000: raise ValueError("Requiere 20..10000 simulaciones por registro")
    if model == "liljegren":
        try: import lwbgt  # noqa: F401
        except ImportError as exc: raise RuntimeError("Instala lwbgt para el modo liljegren, sin fallback") from exc
    rng = random.Random(seed)
    intervals = []
    rejected = []
    for i, row in enumerate(rows):
        if row["data_origin"] == "synthetic_fixture":
            data_label = "SYNTHETIC_INPUT_NOT_OBSERVED"
        else:
            data_label = "EXTERNAL_REANALYSIS_OR_SITE_DATA_NOT_WBGT_REFERENCE"
        solar0 = float(row["solar_w_m2"])
        wind0 = float(row["wind_speed_10m_m_s"])
        # Misma muestra aleatoria por modo: comparabilidad pareada.
        draws = [(rng.random(), rng.random()) for _ in range(n_samples)]
        for scenario, scheme in UNCERTAINTY_SCHEMES.items():
            estimates = []
            errors = 0
            for u_s, u_v in draws:
                solar_multiplier = _triangle_from_uniform(u_s, *scheme["solar_factor"])
                wind_multiplier = _triangle_from_uniform(u_v, *scheme["wind_factor"])
                # 0 irradiancia permanece 0; sin radiación nocturna ficticia.
                solar = solar0 * solar_multiplier
                wind = wind0 * wind_multiplier
                try:
                    estimates.append(_estimate(row, model, solar, wind, roughness_m=roughness_m, urban=urban))
                except (ValueError, ArithmeticError) as e:
                    errors += 1
            if not estimates:
                rejected.append({"timestamp_utc": row["timestamp_utc"], "mode": scenario,
                                 "reason": "all_perturbed_inputs_outside_model_domain"})
                continue
            lo = quantile(estimates, .05)
            hi = quantile(estimates, .95)
            intervals.append({
                "timestamp_utc": row["timestamp_utc"], "scenario": scenario,
                "input_origin": row["data_origin"], "input_label": data_label,
                "solar_w_m2": solar0, "wind_speed_10m_m_s": wind0,
                "p05_model_c": round(lo, 4),
                "median_model_c": round(quantile(estimates, .5), 4),
                "p95_model_c": round(hi, 4),
                "width_p05_p95_c": round(hi-lo, 4),
                "n_valid_draws": len(estimates), "n_rejected_draws": errors,
                "scientific_status": "MODEL_SENSITIVITY_NOT_VALIDATED_ACCURACY",
            })
    summary = []
    for name in UNCERTAINTY_SCHEMES:
        subset = [r for r in intervals if r["scenario"] == name and r["solar_w_m2"] > 20]
        if subset:
            summary.append({"scenario": name, "n_hours_with_solar": len(subset),
                            "mean_model_band_width_c": round(mean(r["width_p05_p95_c"] for r in subset), 4),
                            "p90_model_band_width_c": round(quantile([r["width_p05_p95_c"] for r in subset], .9), 4)})
    return {
        "version": "0.8.0", "model": model, "research_only": True,
        "statistical_confidence_interval": False,
        "accuracy_vs_instrument_evaluated": False,
        "model_output_type": "EXPERIMENTAL_PROXY_NOT_WBGT" if model == "balance" else "WBGT_LILJEGREN_ESTIMATE_NOT_MEASUREMENT",
        "n_input_hours": len(rows), "n_samples_per_hour": n_samples, "seed": seed,
        "input_perturbation_assumptions": UNCERTAINTY_SCHEMES,
        "sensor_modes_are_idealized": True,
        "note": "Bandas por supuestos ilustrativos. No se infiere desempeño real de VEML7700, anemómetro, ni exactitud del clip.",
        "summary_daylight": summary,
        "bands": intervals, "rejected": rejected,
        "limitations": [
            "Los intervalos reflejan únicamente rangos de viento/radiación SUPUESTOS; no son intervalos de confianza.",
            "No se incluyen incertidumbres de T/HR, radiación de onda larga, geometría, orientación ni sesgo del modelo.",
            "'Sensor ideal' significa una observación hipotética, no un componente comercial caracterizado.",
            "El balance simplificado no es un cálculo validado de WBGT normativo.",
            "Sin referencias instrumentales sincronizadas no es posible informar MAE real.",
            "La extrapolación de viento 10m→2m usa un perfil neutral abierto; no válida en estructuras de obra.",
        ],
    }


def save_uncertainty_report(report: dict, out: str | Path) -> None:
    root = Path(out); root.mkdir(parents=True, exist_ok=True)
    (root / "uncertainty_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["bands"]:
        with (root / "uncertainty_bands.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(report["bands"][0]))
            writer.writeheader(); writer.writerows(report["bands"])
    if report["summary_daylight"]:
        with (root / "mode_comparison.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(report["summary_daylight"][0]))
            writer.writeheader(); writer.writerows(report["summary_daylight"])
    lines = ["# HeatGuard — bandas de escenarios v0.8", "", "**NO es precisión observada ni intervalo estadístico de confianza.**", "",
             f"Modelo: `{report['model']}`, {report['n_input_hours']} horas, {report['n_samples_per_hour']} simulaciones/hora.", "",
             "| Escenario | Horas soleadas | Ancho medio p05-p95 (°C) |", "|---|---:|---:|"]
    for row in report["summary_daylight"]:
        lines.append(f"| {row['scenario']} | {row['n_hours_with_solar']} | {row['mean_model_band_width_c']:.3f} |")
    lines += ["", "Las amplitudes dependen de rangos hipotéticos de perturbación, NO de fichas técnicas de sensores.",
              "", "## Límites", *[f"- {x}" for x in report["limitations"]]]
    (root / "RESUMEN.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Propagación de supuestos de entrada: NO intervalo de confianza")
    p.add_argument("--weather", required=True)
    p.add_argument("--model", choices=["balance", "liljegren"], default="balance")
    p.add_argument("--samples", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--roughness-m", type=float, default=.1)
    p.add_argument("--urban", type=int, choices=[0, 1], default=1)
    p.add_argument("--out", default="results/uncertainty_v08")
    args = p.parse_args()
    result = analyze_uncertainty(load_weather_csv(args.weather), model=args.model, n_samples=args.samples,
                                 seed=args.seed, roughness_m=args.roughness_m, urban=args.urban)
    save_uncertainty_report(result, args.out)
    print(f"Generadas {len(result['bands'])} bandas de escenario en {args.out}")
    print("AVISO: incertidumbre condicionada a supuestos; NO exactitud calibrada, NO WBGT medido.")


if __name__ == "__main__":
    main()
