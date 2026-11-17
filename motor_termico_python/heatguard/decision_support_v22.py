"""Bandas ilustrativas y estado de revisión humana, NO alarmas de seguridad.

Solo admite políticas explícitas, con origen y media-ancho definidos por usuario;
una banda ±C no es un intervalo de confianza ni un percentil calibrado.
"""
from __future__ import annotations
from math import isfinite


def _scalar(x, name, low, high):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or not low<=x<=high:
        raise ValueError(f'context.research_review.{name} fuera de rango [{low},{high}]')
    return float(x)


def evaluate_band(estimate: dict, context: dict, *, simulated: bool=False) -> dict:
    cfg=context.get('research_review')
    out={'status':'not_configured','research_only':True,'safety_alert_enabled':False,
         'not_confidence_interval':True,'not_occupational_limit':True,
         'message':'Sin política de investigación explícita; no hay alarma.'}
    if cfg is None:
        return out
    if not isinstance(cfg,dict):
        raise ValueError('context.research_review debe ser objeto')
    if cfg.get('enabled') is not True:
        return out
    threshold=_scalar(cfg.get('threshold_c'),'threshold_c',-10,70)
    half=_scalar(cfg.get('illustrative_half_width_c'),'illustrative_half_width_c',0,15)
    duration=_scalar(cfg.get('duration_review_min',0.000001),'duration_review_min',0.000001,480)
    hysteresis=_scalar(cfg.get('hysteresis_c',0.5),'hysteresis_c',0,5)
    repeat=_scalar(cfg.get('repeat_suppression_min',30),'repeat_suppression_min',0,1440)
    coverage=_scalar(cfg.get('minimum_coverage_fraction',0.5),'minimum_coverage_fraction',0,1)
    origin=cfg.get('origin','research_scenario')
    if not isinstance(origin,str) or not origin.strip():
        raise ValueError('context.research_review.origin no válido')
    out.update(threshold_c=threshold, half_width_c=half, origin=origin,
               duration_review_min=duration, hysteresis_c=hysteresis,
               repeat_suppression_min=repeat, minimum_coverage_fraction=coverage,
               window_minutes=60, band_kind='user_assumed_not_statistical',
               simulated=simulated)
    if estimate.get('status')!='computed':
        out.update(status='missing_estimate',message='WBGT exterior no calculado; no interpretar ausencia de alerta como seguridad.')
        return out
    val=_scalar(estimate.get('value_c'),'estimate.value_c',-40,90)
    lower=round(val-half,3);upper=round(val+half,3)
    if lower>=threshold:
        status='entire_assumed_band_above_threshold'
        attention='priority_review'
    elif upper>=threshold:
        status='assumed_band_intersects_threshold'
        attention='review'
    else:
        status='assumed_band_below_threshold'
        attention='monitor_inputs_not_safety_clearance'
    out.update(status=status,attention=attention, estimate_c=val,
               band_lower_c=lower,band_upper_c=upper,
               message='Atención visual EXPERIMENTAL: valor y banda supuesta, no límite legal, ni criterio automático de trabajo seguro.')
    return out
