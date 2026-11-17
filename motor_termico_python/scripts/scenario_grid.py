"""Sensibilidad al viento/radiación con escenarios. Requiere lwbgt instalado.

Uso desde la raíz: python scripts/scenario_grid.py
La dispersión entre escenarios NO equivale a un intervalo de confianza.
"""
import copy
import json
import sys
from pathlib import Path

# Permite ejecutar este script directamente desde una copia sin instalar.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from heatguard import evaluate

BASE = Path(__file__).resolve().parents[1] / "examples" / "outdoor_scenario.json"


def main():
    base = json.loads(BASE.read_text(encoding="utf-8"))
    results = []
    for solar in (200, 650, 900):
        for wind in (0.3, 1.0, 3.0):
            obj = copy.deepcopy(base)
            for obs in obj["observations"]:
                if obs["parameter"] == "solar_w_m2":
                    obs["value"] = solar
                elif obs["parameter"] == "wind_speed_m_s":
                    obs["value"] = wind
            output = evaluate(obj)
            model = output["wbgt_outdoor_model"]
            if model["status"] != "computed":
                print("Modelo no disponible:", model)
                return
            results.append((solar, wind, model["value_c"]))
    print("Escenarios FICTICIOS, NO mediciones ni límites de seguridad:\n")
    for solar, wind, value in results:
        print(f"Solar={solar:4} W/m² | viento={wind:3.1f} m/s | WBGT modelo={value:5.2f} °C")
    print(f"\nRango ENTRE ESTOS ESCENARIOS: {min(x[2] for x in results):.2f} - {max(x[2] for x in results):.2f} °C")
    print("Esto NO representa un intervalo de confianza validado ni un WBGT ISO medido.")


if __name__ == "__main__":
    main()
