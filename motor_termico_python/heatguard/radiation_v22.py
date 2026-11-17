"""HeatGuard v0.22: fuentes radiativas opcionales, separadas por procedencia.

Una diferencia de temperatura negro/blanco NO equivale a irradiancia sin una
calibracion fisica que incluya viento, orientacion y geometria. Una camara sin
calibracion solo puede aportar etiquetas de contexto, no W/m².
"""
from __future__ import annotations
from math import isfinite
from .schema import iso_datetime, read_event


def _number(obj: dict, key: str, lo: float, hi: float) -> float:
    v = obj.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or not lo <= float(v) <= hi:
        raise ValueError(f'context.radiation.{key} debe ser numero entre {lo} y {hi}')
    return float(v)


def prepare_radiation(event: dict) -> tuple[dict, dict]:
    """Anexa SOLO observaciones explicitas; la etiqueta visual no se cuantifica.

    Modos: none, external_weather, instrumental, manual, differential,
    visual_label, solar_components.
    solar_components = GHI proxy=diffuse + fraction*direct, estrictamente
    escenario geometrico, NO medicion de irradiancia personal ni de IR industrial.
    """
    _, _, zone, context, _ = read_event(event)
    cfg = context.get('radiation') or {'mode': 'none'}
    if not isinstance(cfg, dict):
        raise ValueError('context.radiation debe ser objeto')
    mode = cfg.get('mode', 'none')
    if mode not in ('none', 'external_weather', 'instrumental', 'manual',
                    'differential', 'visual_label', 'solar_components'):
        raise ValueError('context.radiation.mode no reconocido')
    out = {**event, 'observations': [dict(x) for x in event.get('observations', [])]}
    info = {'mode': mode, 'status': 'not_supplied', 'solar_added': False,
            'calibrated_radiometer': False, 'no_direct_heat_risk_inference': True,
            'warnings': []}
    existing = {x['parameter'] for x in out['observations']}
    observed_at = cfg.get('observed_at', event['timestamp'])
    iso_datetime(str(observed_at))
    def append(parameter, value, unit, kind, source, metadata):
        if parameter in existing:
            info['warnings'].append(f'{parameter} ya presente: no se sobrescribe')
            return False
        out['observations'].append({'parameter':parameter,'value':value,'unit':unit,
            'kind':kind,'source':source,'zone_id':zone,'timestamp':str(observed_at), 'metadata':metadata})
        existing.add(parameter)
        return True
    if mode == 'manual':
        v = _number(cfg, 'solar_w_m2', 0, 2000)
        uncertainty = cfg.get('uncertainty_w_m2')
        if uncertainty is not None:
            uncertainty = _number(cfg, 'uncertainty_w_m2', 0, 1000)
        info['solar_added'] = append('solar_w_m2', v, 'W/m2','assumed',
            str(cfg.get('source_id') or 'MANUAL_SCENARIO_NOT_INSTRUMENT'),
            {'mode':'manual','not_measured':True,'uncertainty_w_m2':uncertainty})
        info['status'] = 'assumed_scenario'
        info.update(source_kind='assumed', observed_at=str(observed_at),
                    uncertainty_w_m2=uncertainty)
        info['warnings'].append('Solar manual: escenario declarado, NO radiación medida.')
    elif mode == 'instrumental':
        v = _number(cfg, 'solar_w_m2', 0, 2000)
        source = str(cfg.get('source_id', '')).strip()
        calibration = str(cfg.get('calibration_id', '')).strip()
        if not source or not calibration:
            raise ValueError('Radiación instrumental requiere source_id y calibration_id')
        uncertainty = cfg.get('uncertainty_w_m2')
        if uncertainty is not None:
            uncertainty = _number(cfg, 'uncertainty_w_m2', 0, 1000)
        info['solar_added'] = append('solar_w_m2', v, 'W/m2', 'measured', source,
            {'mode':'instrumental','calibration_id':calibration,
             'uncertainty_w_m2':uncertainty,'reference_instrument':True})
        info.update(status='instrumental_measurement', calibrated_radiometer=True,
                    source_kind='measured', source_id=source, observed_at=str(observed_at),
                    uncertainty_w_m2=uncertainty)
    elif mode == 'external_weather':
        candidates = [item for item in out['observations']
                      if item.get('parameter') == 'solar_w_m2' and item.get('kind') == 'external']
        if not candidates:
            raise ValueError('external_weather requiere observación solar_w_m2 kind=external')
        selected = candidates[-1]
        info.update(status='external_weather_context', source_kind='external',
                    source_id=selected.get('source'),
                    observed_at=selected.get('timestamp') or event['timestamp'])
        info['warnings'].append('Radiación meteorológica externa: puede no representar el puesto.')
    elif mode == 'solar_components':
        direct = _number(cfg, 'direct_horizontal_w_m2', 0, 2000)
        diffuse = _number(cfg, 'diffuse_horizontal_w_m2', 0, 2000)
        fraction = _number(cfg, 'direct_exposure_fraction', 0, 1)
        v = diffuse + fraction * direct
        if v > 2000:
            raise ValueError('Irradiancia de escenario fuera del rango permitido')
        info['solar_added'] = append('solar_w_m2', round(v,5),'W/m2','estimated',
            'SHORTWAVE_CONTEXT_SCENARIO',{'direct':direct,'diffuse':diffuse,'fraction':fraction,
            'not_local_calibrated':True})
        info['status'] = 'heuristic_context'
        info['warnings'].append('Factor visual/sombra: escenario corto-onda horizontal, no radiación personal completa.')
    elif mode == 'visual_label':
        label=cfg.get('scene_label')
        if label not in ('sun', 'partial_shade', 'shade', 'indoor', 'unknown'):
            raise ValueError('scene_label requiere sun/partial_shade/shade/indoor/unknown')
        info.update(status='categorical_only', scene_label=label, source_kind='estimated',
                    observed_at=str(observed_at))
        info['warnings'].append('Cámara/etiqueta visual NO permite estimar W/m² sin referencia y calibración.')
    elif mode == 'differential':
        black = _number(cfg,'black_surface_c',-40,110)
        white = _number(cfg,'white_surface_c',-40,110)
        kind = cfg.get('source_kind','assumed')
        if kind not in ('assumed','measured'):
            raise ValueError('source_kind differential requiere measured o assumed')
        source = cfg.get('source_id','RADIATIVE_FUTURE_SENSOR')
        if not isinstance(source,str) or not source.strip():
            raise ValueError('source_id debe ser cadena')
        uncertainty = cfg.get('uncertainty_c')
        if uncertainty is not None:
            uncertainty = _number(cfg, 'uncertainty_c', 0, 20)
        metadata = {'uncalibrated':True, 'uncertainty_c':uncertainty}
        append('radiative_black_surface_c',black,'degC',kind,source,metadata)
        append('radiative_white_surface_c',white,'degC',kind,source,metadata)
        append('radiative_delta_c',round(black-white,4),'degC',kind,source,metadata)
        info.update(status='differential_thermal_signal_only', delta_c=round(black-white,4),
                    source_kind=kind, source_id=source, observed_at=str(observed_at),
                    uncertainty_c=uncertainty)
        info['warnings'].append('Delta negro-blanco no convertible en W/m² ni WBGT sin calibración radiativa/convectiva.')
    return out, info
