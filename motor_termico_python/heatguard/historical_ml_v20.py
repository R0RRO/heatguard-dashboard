"""HeatGuard v0.20 — ML EXPLORATORIO para referencia meteorológica japonesa.

AVISO: datos ambientales históricos, NO datos del clip ni referencia ISO 7243 completa.
Modelo entrenado con ERA/reanálisis: PROHIBIDO extrapolar a lecturas locales HTU21D
sin una validación explícita de dominio. Nunca activa alertas laborales.

Se ejecuta: python -m heatguard.historical_ml_v20 --csv research_data/observaciones_japon_2025_agosto.csv --out results/ml_v20
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

FEATURES = (
    "ono_c", "liljegren_c", "temperature_c", "relative_humidity_pct",
    "solar_w_m2", "wind_10m_m_s", "pressure_hpa", "hour_sin", "hour_cos"
)
THRESHOLD = 28.0  # INVESTIGACION, no valor normativo
STATION_NAMES = ("JP_TOKYO", "JP_OSAKA", "JP_FUKUOKA", "JP_SAPPORO")
TRAIN_END = "2025-08-14"
TEST_START = "2025-08-15"


def check_table(df):
    import pandas as pd
    import numpy as np
    expected = set(FEATURES) | {"site_id", "timestamp_utc", "jst_day", "reference_c"}
    if not expected.issubset(df.columns):
        raise ValueError(f"Columnas faltantes: {sorted(expected - set(df.columns))}")
    if df.empty or df[[*FEATURES, "reference_c"]].isna().any().any():
        raise ValueError("Matriz vacía o datos faltantes")
    if not np.isfinite(df[[*FEATURES, "reference_c"]].to_numpy(dtype=float)).all():
        raise ValueError("Valores no finitos")
    if df.duplicated(["site_id", "timestamp_utc"]).any():
        raise ValueError("Observaciones duplicadas por estación y hora")
    if not set(df.site_id).issubset(set(STATION_NAMES)):
        raise ValueError("Estación no reconocida: la evaluación es exclusiva para los sitios japoneses declarados")
    if not ((df.reference_c>=-30)&(df.reference_c<=65)).all():
        raise ValueError("Valores WBGT fuera del rango de investigación")
    days=pd.to_datetime(df.jst_day,errors="raise")
    if days.min()<pd.Timestamp("2025-08-01") or days.max()>pd.Timestamp("2025-08-31"):
        raise ValueError("Se esperaba exclusivamente agosto de 2025")
    if "air_data_origin" not in df or not (df.air_data_origin=="open_meteo_reanalysis").all():
        raise ValueError("Dominio incorrecto: este estudio requiere aire regional de Open-Meteo")
    return True


def split_data(df, held_out_site=None):
    import pandas as pd
    days=pd.to_datetime(df.jst_day)
    train=days<=pd.Timestamp(TRAIN_END)
    test=days>=pd.Timestamp(TEST_START)
    if held_out_site is not None:
        train &= (df.site_id!=held_out_site)
        test &= (df.site_id==held_out_site)
    tr=df[train].copy(); te=df[test].copy()
    if tr.empty or te.empty: raise ValueError("Partición vacía")
    if set(tr.timestamp_utc).intersection(set(te.timestamp_utc)):
        raise ValueError("Fuga temporal: timestamps en ambos segmentos")
    if held_out_site and held_out_site in set(tr.site_id):
        raise ValueError("Fuga espacial: la estación reservada entró a entrenamiento")
    return tr,te


def candidates():
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    # Parámetros PREFIJADOS para no seleccionarlos sobre el conjunto evaluado.
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=100)),
        "gradient_boosting": HistGradientBoostingRegressor(
            max_iter=120, learning_rate=0.045, max_leaf_nodes=7,
            min_samples_leaf=35, l2_regularization=20, random_state=42),
        "random_forest": RandomForestRegressor(
            n_estimators=160, min_samples_leaf=18, max_features=0.85,
            random_state=42, n_jobs=1),
    }


def measure(reference, prediction, research_threshold=THRESHOLD):
    import numpy as np
    ref=np.asarray(reference,dtype=float)
    pred=np.asarray(prediction,dtype=float)
    if ref.shape!=pred.shape or ref.size==0: raise ValueError("Predicción y referencia deben ser del mismo tamaño")
    if not np.isfinite(ref).all() or not np.isfinite(pred).all(): raise ValueError("NaN en cálculo")
    err=pred-ref
    high=ref>=research_threshold
    low=~high
    return {
        "n":int(ref.size), "high_reference_n":int(high.sum()),
        "mae_c":round(float(np.abs(err).mean()),4),
        "rmse_c":round(float(np.sqrt(np.mean(err**2))),4),
        "bias_c":round(float(err.mean()),4),
        "false_low_n":int((high&(pred<research_threshold)).sum()),
        "false_high_n":int((low&(pred>=research_threshold)).sum()),
        "underestimate_gt1_when_high_n":int((high&(err < -1)).sum()),
        "underestimate_gt2_when_high_n":int((high&(err < -2)).sum()),
        "high_reference_mae_c":round(float(np.abs(err[high]).mean()),4) if high.any() else None,
    }


def one_evaluation(tr,te,fold):
    import pandas as pd
    X_tr=tr[list(FEATURES)].to_numpy(dtype=float)
    X_te=te[list(FEATURES)].to_numpy(dtype=float)
    residual_tr=tr.reference_c.to_numpy(dtype=float)-tr.ono_c.to_numpy(dtype=float)
    preds={"ono":te.ono_c.to_numpy(dtype=float),"liljegren":te.liljegren_c.to_numpy(dtype=float)}
    for name,model in candidates().items():
        model.fit(X_tr,residual_tr)
        preds[name]=te.ono_c.to_numpy(dtype=float)+model.predict(X_te)
    rows=[]
    frame=te[["site_id","timestamp_utc","jst_day","reference_c"]].copy()
    frame["fold"]=fold
    for name,p in preds.items():
        frame[name+"_c"]=p
        rows.append({"fold":fold,"model":name,**measure(te.reference_c.to_numpy(dtype=float),p)})
    return rows,frame


def research_predict(model_path, values, *, air_data_origin):
    # Herramienta de investigación deliberadamente separada de la API de alertas.
    if air_data_origin!="open_meteo_reanalysis":
        raise ValueError("MODELO BLOQUEADO: solo evaluado con entradas regionales Open-Meteo; no inferir sobre HTU21D ni JMA")
    import joblib
    import numpy as np
    path=Path(model_path)
    obj=joblib.load(path)  # SOLO artefactos confiables generados localmente
    if obj["metadata"].get("status")!="research_only_do_not_deploy":
        raise ValueError("Metadatos de investigación incompatibles")
    vals=np.asarray([[float(values[k]) for k in FEATURES]],dtype=float)
    if not np.isfinite(vals).all():raise ValueError("Entrada no finita")
    value=float(values["ono_c"])+float(obj["model"].predict(vals)[0])
    return {"wbgt_exploratory_c":round(value,3),"safety_alerts_enabled":False,
            "status":"research_only_not_validated_in_unseen_site",
            "reference_kind":"japan_composite_instrumental_psychrometric"}


def run(csv_path,out_dir):
    import pandas as pd
    import joblib
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(csv_path)
    check_table(df)
    configs=[("temporal_known_sites",None)]+[("unseen_"+s,s) for s in STATION_NAMES]
    metrics=[]; all_preds=[];splits=[]
    for name,held_out in configs:
        tr,te=split_data(df,held_out)
        measurements,frame=one_evaluation(tr,te,name)
        metrics.extend(measurements);all_preds.append(frame)
        splits.append({"fold":name,"training_rows":len(tr),"test_rows":len(te),
            "train_sites":sorted(tr.site_id.unique().tolist()),"test_sites":sorted(te.site_id.unique().tolist()),
            "train_max_day":str(tr.jst_day.max()),"test_min_day":str(te.jst_day.min())})
    # Guardamos solo modelo entrenado con 1-14 agosto; jamás alimenta el sistema de alertas.
    train,_=split_data(df,None)
    model=candidates()["gradient_boosting"]
    model.fit(train[list(FEATURES)].to_numpy(dtype=float),
              train.reference_c.to_numpy(dtype=float)-train.ono_c.to_numpy(dtype=float))
    metadata={"status":"research_only_do_not_deploy", "train_dates":"2025-08-01..2025-08-14",
              "features":list(FEATURES),"input_domain":"open_meteo_reanalysis",
              "reference":"Japan MOE: globo observado, bulbo húmedo psicrométrico calculado",
              "not_iso_7243_validation":True,"not_clip_calibration":True,
              "test_dates_previously_examined":True,
              "warnings":["No usar con sensor local HTU21D", "No activar alertas de seguridad", "No usar el error histórico como intervalo de predicción"]}
    joblib.dump({"model":model,"metadata":metadata},out/"hgb_exploratorio_NO_DESPLEGAR.joblib")
    pd.DataFrame(metrics).to_csv(out/"metricas_todos_los_folds.csv",index=False)
    pd.concat(all_preds,ignore_index=True).to_csv(out/"predicciones_todos_los_folds.csv",index=False)
    result={"status":"exploratory_history_not_safety_validated",
      "dataset_rows":int(len(df)),"unique_sites":int(df.site_id.nunique()),
      "research_threshold_only_c":THRESHOLD,
      "model_parameters_predefined":True,"feature_origin":"regional_open_meteo_not_clip",
      "reference_origin":"japanese_wbgt_partial_instrumental",
      "dates_already_examined_in_previous_research":True,
      "no_untouched_external_test":True,
      "split_integrity":splits, "metrics":metrics,
      "recommendation":"No habilitar corrección ML para faena nueva: falló al extrapolar a una estación reservada; obtener referencias nuevas y calibración física."}
    (out/"reporte_ml_v20.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    (out/"METODOLOGIA_Y_LIMITACIONES.md").write_text(
        "# Validación exploratoria de ML para HeatGuard\n\n"
        "Entradas: **meteorología regional Open-Meteo**, no lecturas HTU21D. Referencia: WBGT japonés basado en globo observado y bulbo húmedo psicrométrico calculado. "
        "No equivale a validación ISO 7243 ni de alertas preventivas.\n\n"
        "## Particiones\n"
        "- Temporal: entrenamiento 1–14 agosto (4 estaciones), evaluación 15–31 agosto (4 estaciones).\n"
        "- Espaciotemporal: entrenamiento 1–14 agosto en 3 estaciones, evaluación 15–31 agosto en la cuarta. Cada estación se reserva una vez.\n"
        "- Las fechas y estaciones ya se exploraron en versiones anteriores: no es prueba completamente ciega.\n\n"
        "## Objetivo\n"
        "Los modelos regresan **residuo (WBGT_japonés − Ono)**. Variables accesibles al cálculo antes de conocer la etiqueta. "
        "No se usa ID de estación para entrenar; día futuro no participa del entrenamiento.\n\n"
        "## Decisión de integración\n"
        "El modelo generado es **research_only_do_not_deploy**. La API v0.19 mantiene Ono sin ML. "
        "Una mejora del MAE global que aumente subestimaciones o falle en Fukuoka no autoriza despliegue.\n",
        encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser(description="ML exploratorio de referencias japonesas, nunca activar alertas")
    parser.add_argument("--csv",default="research_data/observaciones_japon_2025_agosto.csv")
    parser.add_argument("--out",default="results/ml_v20")
    a=parser.parse_args()
    result=run(a.csv,a.out)
    print(json.dumps({"status":result["status"], "dataset_rows":result["dataset_rows"],"output":str(a.out),"n_folds":len(result["split_integrity"])},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
