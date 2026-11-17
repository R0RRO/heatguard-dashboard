"""Entrenamiento ML exploratorio: termohigrómetro JMA real + meteorología regional.

NO es calibración del HTU21D ni validación ocupacional. El WBGT japonés
comparte mediciones JMA; los datos de prueba ya fueron examinados previamente.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .historical_ml_v20 import candidates, measure

FEATURES_LOCAL = ("ono_jma_c", "liljegren_jma_c", "air_temperature_jma_c",
                  "relative_humidity_jma_pct", "solar_external_w_m2",
                  "wind_external_10m_m_s", "pressure_jma_hpa", "hour_sin", "hour_cos")


def validate(df):
    import pandas as pd
    import numpy as np
    required=set(FEATURES_LOCAL)|{"site_id", "timestamp_utc", "jst_day", "reference_c", "air_origin", "solar_wind_origin"}
    if not required.issubset(df): raise ValueError(f"Columnas faltantes: {sorted(required-set(df))}")
    if df.empty or df.duplicated(["site_id","timestamp_utc"]).any(): raise ValueError("Faltan datos o hay horas duplicadas")
    if set(df.site_id)!={"JP_FUKUOKA"}:raise ValueError("Dominio restringido a Fukuoka JMA")
    if not (df.air_origin=="jma_observatory_measured").all():raise ValueError("Aire debe provenir de JMA, nunca de clip")
    if not (df.solar_wind_origin=="open_meteo_reanalysis").all():raise ValueError("Viento y radiación regionales requeridos")
    if not np.isfinite(df[[*FEATURES_LOCAL,"reference_c"]].to_numpy(dtype=float)).all():raise ValueError("Datos no finitos")
    days=pd.to_datetime(df.jst_day)
    if days.min()!=pd.Timestamp("2025-08-01") or days.max()!=pd.Timestamp("2025-08-31"):
        raise ValueError("Período distinto de agosto 2025")
    return True


def run(csv_path, out_dir):
    import pandas as pd
    import numpy as np
    import joblib
    df=pd.read_csv(csv_path);validate(df)
    days=pd.to_datetime(df.jst_day)
    tr=df[days<=pd.Timestamp('2025-08-14')]
    te=df[days>=pd.Timestamp('2025-08-15')]
    if set(tr.timestamp_utc)&set(te.timestamp_utc):raise ValueError('Fuga temporal')
    xtr=tr[list(FEATURES_LOCAL)].to_numpy(dtype=float)
    xte=te[list(FEATURES_LOCAL)].to_numpy(dtype=float)
    y=tr.reference_c.to_numpy(dtype=float)-tr.ono_jma_c.to_numpy(dtype=float)
    predictions={"ono_jma":te.ono_jma_c.to_numpy(dtype=float),
                 "liljegren_jma":te.liljegren_jma_c.to_numpy(dtype=float)}
    models=candidates()
    for name,model in models.items():
        model.fit(xtr,y)
        predictions[name]=te.ono_jma_c.to_numpy(dtype=float)+model.predict(xte)
    metrics=[]
    values=te[['site_id','timestamp_utc','jst_day','reference_c']].copy()
    for name,pred in predictions.items():
        metrics.append({'model':name,**measure(te.reference_c.to_numpy(dtype=float),pred)})
        values[name+'_c']=pred
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(metrics).to_csv(out/'metricas_ml_local.csv',index=False)
    values.to_csv(out/'predicciones_ml_local.csv',index=False)
    meta={"status":"research_only_do_not_deploy","rows":len(df),
          "train_days":"2025-08-01..2025-08-14","test_days":"2025-08-15..2025-08-31",
          "input_domain":"JMA_observatory_air_plus_OpenMeteo_regional_wind_radiation",
          "reference_shared_inputs":True,"not_clip_ht21d_calibration":True,
          "previously_examined_dates":True,"no_iso_7243_validation":True,
          "cannot_infer_on_unseen_site":True,"cannot_trigger_occupational_alerts":True,
          "metrics":metrics}
    (out/'reporte_ml_local.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    joblib.dump({"model":models['random_forest'],"features":FEATURES_LOCAL,"metadata":meta},out/'rf_local_jma_NO_DESPLEGAR.joblib')
    return meta


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--csv',default='research_data/fukuoka_jma_local_2025_agosto.csv')
    p.add_argument('--out',default='results/ml_local_v20')
    a=p.parse_args()
    meta=run(a.csv,a.out)
    print(json.dumps({'status':meta['status'],'rows':meta['rows'],'output':a.out},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
