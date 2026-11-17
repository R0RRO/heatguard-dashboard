"""Ensayos v0.6 para elegir investigaciones y NO declarar exactitud de WBGT."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from .case_radiation import CaseAssumptions, surface_equilibrium_c, ambiguity_study, relative_brightness
from .relative_wind import relative_wind
from .sensitivity import load_case, analyze


@dataclass(frozen=True)
class SensorCandidate:
    name: str
    measures: str
    supply_or_interface: str
    approximate_size_mm: str | None
    current_typical_mA: float | None
    component_price_clp: float | None
    status: str
    uncertainty_or_limitation: str
    source: str | None


CANDIDATES = (
    SensorCandidate('VEML7700','iluminancia, lux','I2C 2.5–3.6 V','6.8 x 2.35 x 3',0.008,None,'documentado; candidato',
                    '8 µA a refresco ~600ms; no mide W/m² ni radiación LW', 'Vishay DS rev 1.8, 28/11/2024'),
    SensorCandidate('termistor en carcasa','temperatura superficial','ADC + divisor / NTC','según integración',None,None,'hipótesis de I+D',
                    'No identifica radiación si no se conocen viento, orientación, calor interno y absorptividad', None),
    SensorCandidate('FS3000','velocidad de aire en flujo local','I2C 3.3 V','8 x 9 x 4',10.0,None,'producto obsoleto; no seleccionar en producción',
                    'Flujo direccional, max 10 mA típicos; precisión 5% de escala completa', 'Renesas FS3000 Datasheet Rev1.01'),
    SensorCandidate('estación de obra','viento + radiación de zona','gateway / interfaz externa',None,None,None,'alternativa de arquitectura',
                    'Requiere ubicación representativa, calibración, energía y costo por obra',None),
    SensorCandidate('meteorología de zona','viento regional + GHI modelado','API externo',None,None,None,'disponible; no medición local',
                    'Viento a 10 m; radiación GHI horaria no equivale a orientación del clip', 'Open-Meteo docs'),
)


def run_experiments(case_path: str | None = None) -> dict:
    case = load_case(case_path)
    b = case['baseline']
    assumptions = CaseAssumptions()
    predicted_surface_c = surface_equilibrium_c(b['air_temperature_c'], b['solar_w_m2'], b['wind_speed_m_s'], assumptions)
    amb = ambiguity_study(predicted_surface_c, b['air_temperature_c'], 0.2, 4.0, points=21, assumptions=assumptions)
    return {
        'version': '0.6.0', 'purpose': 'research_only', 'reference_wbgt_data_used': False,
        'case_temperature_surface_prediction_c': round(predicted_surface_c, 3),
        'surface_analysis': amb,
        'wind_without_direction': relative_wind(2.0, 1.5),
        'wind_same_direction': relative_wind(2.0, 1.5, wind_bearing_deg=90, walking_bearing_deg=90),
        'wind_opposite_direction': relative_wind(2.0, 1.5, wind_bearing_deg=90, walking_bearing_deg=270),
        'lux_context_example': relative_brightness(18000, 95000),
        'sensor_candidates': [asdict(s) for s in CANDIDATES],
        'comparison': analyze(case, model='balance', samples=400, seed=42),
        'caveats': [
            'NO se comparó el modelo Liljegren: se necesita lwbgt instalado; no se substituye silenciosamente.',
            'Los resultados del balance y la temperatura superficial son hipótesis matemáticas, no WBGT de referencia.',
            'La relación lux/referencia lux es solo indicador visual: no recupera W/m².',
            'El viento del ejemplo con dirección es ilustrativo; el MPU no conoce el vector de viento.',
            'Precios en CLP y exactitud de termistor/estación se dejan sin inventar; solicitar cotizaciones y mediciones.',
        ]
    }


def save_results(result: dict, directory: str | Path) -> list[Path]:
    dest = Path(directory); dest.mkdir(exist_ok=True, parents=True)
    p = dest / 'research_report_v06.json'; p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    files=[p]
    p=dest / 'surface_radiation_ambiguity.csv'
    with p.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f, fieldnames=list(result['surface_analysis']['conditional_results'][0]))
        writer.writeheader(); writer.writerows(result['surface_analysis']['conditional_results'])
    files.append(p)
    p=dest / 'sensor_shortlist.csv'
    with p.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(result['sensor_candidates'][0]))
        writer.writeheader(); writer.writerows(result['sensor_candidates'])
    files.append(p)
    p=dest/'RESUMEN.md'
    surface=result['surface_analysis']
    p.write_text('# HeatGuard — Estudio de factibilidad y datos faltantes\n\n'
                 '**Solo investigación. No se ha medido WBGT normativo.**\n\n'
                 f'Caso hipotético: T superficial {result["case_temperature_surface_prediction_c"]:.2f} °C.\n\n'
                 f'Con esa T superficial, el mismo balance admite irradiancias condicionadas '
                 f'a diferentes vientos con amplitud de {surface["spread_of_conditional_solar_w_m2"]:.2f} W/m². '
                 '**Esto no es un intervalo de incertidumbre calibrado.**\n\n'
                 'Decisión: obtener primero GHI regional y un sensor de lux para clasificar sombra/sol; '
                 'investigar termistor de carcasa sin prometer estimación de radiación; '
                 'viento local mediante estación o sensor validado después.\n\n'
                 'FS3000 se incluye como referencia técnica, pero Renesas lo clasifica como obsoleto.\n',encoding='utf-8')
    files.append(p)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return files
    readings=result['surface_analysis']['conditional_results']
    fig,ax=plt.subplots(figsize=(7.2,4.7))
    ax.plot([row['wind_m_s_assumed'] for row in readings], [row['required_incident_solar_w_m2'] for row in readings],marker='o',markersize=3)
    ax.set_xlabel('Viento supuesto local (m/s)')
    ax.set_ylabel('Irradiancia que reproduce la misma T superficial (W/m²)')
    ax.set_title('Una temperatura superficial no identifica simultáneamente viento y radiación')
    ax.grid(alpha=0.25); fig.tight_layout()
    p=dest/'carcasa_no_identificabilidad.png'; fig.savefig(p,dpi=150); plt.close(fig); files.append(p)
    return files


def main() -> None:
    p=argparse.ArgumentParser(description='HeatGuard v0.6: ensayos físicos hipotéticos de sensores')
    p.add_argument('--case',default=None, help='JSON compatible con research_case_example.json')
    p.add_argument('--out',default='results/investigacion_v06')
    args=p.parse_args()
    result=run_experiments(args.case)
    files=save_results(result,args.out)
    print(f'T superficie predicha: {result["case_temperature_surface_prediction_c"]:.2f} °C (hipotético)')
    print('Amplitud de G condicionada al viento:',result['surface_analysis']['spread_of_conditional_solar_w_m2'],'W/m² (NO precisión)')
    print('Archivos:')
    for path in files:print(' ',path)

if __name__ == '__main__':
    main()
