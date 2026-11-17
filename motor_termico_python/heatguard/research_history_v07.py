"""Sensibilidad de WBGT modelado a perturbaciones de viento/radiación.

La referencia para cada diferencia es el MISMO MODELO con entradas meteorológicas
completas (NO un instrumento WBGT). Los escenarios NO son datos observados.
Para validación independiente ver reference_v07.py.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import math
from pathlib import Path
from statistics import mean

from .weather_history_v07 import load_weather_csv
from .thermal_science import experimental_balance_c
from .liljegren import calculate_optional
from .sensitivity import quantile

SCENARIOS = (
    "baseline_full_external",
    "solar_30pct_perturbation",
    "solar_0pct_perturbation",
    "wind_50pct_perturbation",
    "wind_150pct_perturbation",
    "wind_fixed_2m_s_at_10m",
    "solar_30pct_and_wind_50pct",
)


def wind_log_profile(v10: float, *, z0_m: float, desired_height_m: float = 2.0) -> float:
    """Perfil logarítmico neutral exploratorio sobre superficie abierta.

    No válido automáticamente cerca de edificios, en interior o bajo obstáculos;
    z0 y v10 requieren verificación. Devuelve viento extrapolado, NO medido.
    """
    v, z0, z = float(v10), float(z0_m), float(desired_height_m)
    if not (math.isfinite(v) and v >= 0 and math.isfinite(z0) and 0 < z0 < z and z <= 10):
        raise ValueError("v10 debe ser positivo; rugosidad < altura destino <= 10 m")
    return v * math.log(z / z0) / math.log(10.0 / z0)


def _solar_and_wind(row: dict, scenario: str) -> tuple[float, float]:
    solar = float(row["solar_w_m2"])
    wind = float(row["wind_speed_10m_m_s"])
    if scenario in ("solar_30pct_perturbation", "solar_30pct_and_wind_50pct"):
        solar *= 0.30
    elif scenario == "solar_0pct_perturbation":
        solar = 0.0
    if scenario in ("wind_50pct_perturbation", "solar_30pct_and_wind_50pct"):
        wind *= 0.50
    elif scenario == "wind_150pct_perturbation":
        wind *= 1.50
    elif scenario == "wind_fixed_2m_s_at_10m":
        wind = 2.0
    return solar, wind


def _estimate(row: dict, model: str, solar: float, wind10: float,
              roughness_m: float, urban: int) -> float:
    if model == "balance":
        wind2 = wind_log_profile(wind10, z0_m=roughness_m)
        # En el modelo exploratorio original el dominio es v >= 0,1 m/s.
        # Los valores menores se rechazan, no se sustituyen por 0,1.
        if wind2 < 0.1:
            raise ValueError("Viento extrapolado <0.1 m/s: fuera del modelo balance")
        res = experimental_balance_c(
            air_temperature_c=float(row["air_temperature_c"]),
            relative_humidity_pct=float(row["relative_humidity_pct"]),
            solar_w_m2=solar,
            wind_speed_m_s=wind2,
            pressure_hpa=float(row["pressure_hpa"]),
        )
        return float(res["wbgt_like_experimental_c"])
    if model == "liljegren":
        vals = {
            "air_temperature_c": float(row["air_temperature_c"]),
            "relative_humidity_pct": float(row["relative_humidity_pct"]),
            "solar_w_m2": solar,
            "wind_speed_m_s": wind10,
            "pressure_hpa": float(row["pressure_hpa"]),
        }
        context = {
            "environment": "outdoor",
            "location": {
                "latitude_deg": float(row["latitude_deg"]),
                "longitude_deg": float(row["longitude_deg"]),
                "utc_offset_hours": 0,  # timestamps UTC
            },
            "weather_model": {
                "wind_height_m": 10,
                "averaging_minutes": 60,
                "urban": urban,
                "vertical_temperature_difference_c": 0,  # supuesto, no observado
            },
        }
        out = calculate_optional(vals, str(row["timestamp_utc"]), context)
        if out["status"] != "computed":
            raise RuntimeError(f"Liljegren no disponible: {out}")
        return float(out["value_c"])
    raise ValueError("Modelo no reconocido")


def analyze_history(rows: list[dict], *, model: str = "balance", roughness_m: float = .1,
                    urban: int = 1) -> dict:
    if model not in ("balance", "liljegren"):
        raise ValueError("model debe ser balance o liljegren")
    if urban not in (0, 1):
        raise ValueError("urban debe ser 0 o 1")
    if not rows:
        raise ValueError("Sin datos meteorológicos")
    if model == "liljegren":
        try:
            import lwbgt  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("Falta lwbgt: pip install -e '.[wbgt]' (NO usamos proxy sustituto)") from exc
    predictions = []
    rejected = []
    for row in rows:
        ts = str(row["timestamp_utc"])
        try:
            vals = {}
            for scenario in SCENARIOS:
                s, w = _solar_and_wind(row, scenario)
                vals[scenario] = _estimate(row, model, s, w, roughness_m, urban)
            predictions.append({"timestamp_utc": ts, "data_origin": row["data_origin"],
                                "solar_w_m2": float(row["solar_w_m2"]),
                                "wind_speed_10m_m_s": float(row["wind_speed_10m_m_s"]),
                                "air_temperature_c": float(row["air_temperature_c"]),
                                "latitude_deg": float(row["latitude_deg"]),
                                "longitude_deg": float(row["longitude_deg"]),
                                **vals})
        except (ValueError, ArithmeticError, OverflowError) as exc:
            rejected.append({"timestamp_utc": ts, "reason": str(exc)})
    if not predictions:
        raise ValueError("No hay filas válidas del modelo; revisar dominio, viento y datos")
    summary = []
    for scenario in SCENARIOS:
        deltas = [row[scenario] - row["baseline_full_external"] for row in predictions]
        absdiff = [abs(d) for d in deltas]
        summary.append({
            "scenario": scenario, "n": len(deltas),
            "mean_difference_c": round(mean(deltas), 4),
            "mean_abs_difference_c": round(mean(absdiff), 4),
            "p90_abs_difference_c": round(quantile(absdiff, .9), 4),
            "max_abs_difference_c": round(max(absdiff), 4),
        })
    # Separar día/noche evita que las horas sin radiación diluyan el efecto solar.
    phase_metrics = []
    for name, subset in (("day_solar_gt20_w_m2", [r for r in predictions if r["solar_w_m2"] > 20]),
                         ("night_solar_le20_w_m2", [r for r in predictions if r["solar_w_m2"] <= 20])):
        if not subset:
            continue
        for scenario in SCENARIOS:
            dif = [abs(r[scenario] - r["baseline_full_external"]) for r in subset]
            phase_metrics.append({"phase": name, "scenario": scenario, "n": len(subset),
                                  "mean_abs_difference_c": round(mean(dif), 4),
                                  "p90_abs_difference_c": round(quantile(dif, .9), 4)})
    origins = sorted(set(row["data_origin"] for row in predictions))
    return {
        "version": "0.7.0", "research_only": True,
        "model": model,
        "model_description": ("proxy experimental v0.5 (NO WBGT)" if model == "balance"
                              else "WBGT EXTERIOR Liljegren/lwbgt (NO medición instrumental)"),
        "reference_measured": False,
        "comparison_target": "same_model_full_external_inputs; NOT WBGT instrument",
        "data_origins": origins,
        "n_input": len(rows), "n_accepted": len(predictions),
        "rejected": rejected, "roughness_m_if_balance": roughness_m if model == "balance" else None,
        "liljegren_metadata_if_applicable": {
            "wind_height_m": 10, "averaging_minutes": 60, "urban": urban,
            "vertical_temperature_difference_c": "0 assumed, not observed"
        } if model == "liljegren" else None,
        "scenarios": summary, "phase_metrics": phase_metrics, "predictions": predictions,
        "limitations": [
            "Las diferencias son sensibilidad del MISMO MODELO ante cambios artificiales de entrada, no error frente a instrumento.",
            "GHI meteorológica representa radiación global horizontal; escalarla NO modela completamente la sombra de estructuras.",
            "Viento a 10m y radiación de reanálisis NO representan necesariamente casco/chaleco/interior.",
            "El proxy balance requiere viento 2m extrapolado con perfil logarítmico neutro y rugosidad SUPUESTA.",
            "Sin mediciones WBGT independientes no hay MAE de exactitud física ni selección definitiva de sensor.",
        ]
    }


def write_report(report: dict, out: str | Path, *, plot: bool = True) -> list[Path]:
    base = Path(out); base.mkdir(parents=True, exist_ok=True)
    pjson = base / "history_research_report.json"
    pjson.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with (base / "scenario_sensitivity.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(report["scenarios"][0]))
        w.writeheader(); w.writerows(report["scenarios"])
    with (base / "day_night_sensitivity.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(report["phase_metrics"][0]))
        w.writeheader(); w.writerows(report["phase_metrics"])
    with (base / "paired_model_scenarios.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(report["predictions"][0]))
        w.writeheader(); w.writerows(report["predictions"])
    lines = [
        "# HeatGuard v0.7 — sensibilidad ante fuentes y datos faltantes", "",
        f"Modelo: `{report['model']}`; aceptadas {report['n_accepted']}/{report['n_input']} horas.", "",
        "**AVISO: estas NO son métricas de precisión WBGT frente a un instrumento.**", "",
        "| Escenario hipotético | Diferencia media (°C) | Diferencia absoluta media (°C) | p90 absoluta (°C) |",
        "|---|---:|---:|---:|",
    ]
    for r in report["scenarios"]:
        lines.append(f"| {r['scenario']} | {r['mean_difference_c']:.3f} | {r['mean_abs_difference_c']:.3f} | {r['p90_abs_difference_c']:.3f} |")
    lines += ["", "## Estratificación día / noche",
              "Día definido solo para este análisis como GHI >20 W/m²; noche/no-sol como <=20 W/m².",
              "| Franja | Escenario | Cambio absoluto medio (°C) | p90 (°C) |",
              "|---|---|---:|---:|"]
    for r in report["phase_metrics"]:
        lines.append(f"| {r['phase']} | {r['scenario']} | {r['mean_abs_difference_c']:.3f} | {r['p90_abs_difference_c']:.3f} |")
    lines += ["", "## Limitaciones", *[f"- {s}" for s in report["limitations"]]]
    (base / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    created = [pjson, base / "scenario_sensitivity.csv", base / "day_night_sensitivity.csv", base / "paired_model_scenarios.csv", base / "REPORT.md"]
    if plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return created
        labels = [x["scenario"].replace("_", " ") for x in report["scenarios"][1:]]
        delta = [x["mean_abs_difference_c"] for x in report["scenarios"][1:]]
        fig, ax = plt.subplots(figsize=(10.5, 5.1))
        ax.barh(labels, delta)
        ax.invert_yaxis(); ax.set_xlabel("Cambio absoluto medio de salida respecto del modelo con datos completos (°C)")
        ax.set_title("Sensibilidad ante supuestos de viento y radiación — NO error WBGT")
        fig.tight_layout()
        png = base / "sensitivity_weather.png"; fig.savefig(png, dpi=150); plt.close(fig)
        created.append(png)
    return created


def main() -> None:
    p = argparse.ArgumentParser(description="Experimentos con históricos: diferencias entre escenarios, NO exactitud WBGT")
    p.add_argument("--weather", required=True)
    p.add_argument("--model", choices=("balance", "liljegren"), default="balance")
    p.add_argument("--roughness-m", type=float, default=.1)
    p.add_argument("--urban", type=int, choices=(0, 1), default=1)
    p.add_argument("--out", default="results/history_v07")
    args = p.parse_args()
    report = analyze_history(load_weather_csv(args.weather), model=args.model,
                             roughness_m=args.roughness_m, urban=args.urban)
    files = write_report(report, args.out)
    print(f"{len(report['predictions'])} horas modeladas ({report['model']}); NO WBGT observado")
    for file in files:
        print(file)


if __name__ == "__main__":
    main()
