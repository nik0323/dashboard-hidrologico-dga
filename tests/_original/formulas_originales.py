"""Cálculos que en el original están escritos en línea dentro de las funciones de UI.

Cada función reproduce TEXTUALMENTE las líneas indicadas de `dashboard_dga_original.py`,
solo envueltas en una función para poder testearlas sin Streamlit. No modificar: es la
referencia contra la que se valida el refactor.
"""

import numpy as np
import pandas as pd

from dashboard_dga_original import COL_DIST, LAT_REF, LON_REF, T_OBJETIVO, haversine_vectorizado


def tc_cuenca(area_km2, longitud_km, modo, pendiente=None, desnivel_m=None):
    """Líneas 631-654 (modulo_cuenca)."""
    if modo == "Pendiente Media (m/m)":
        desnivel_m = pendiente * longitud_km * 1000
    else:
        pendiente = desnivel_m / (longitud_km * 1000)

    tc_kirpich = 0.0663 * longitud_km ** 0.77 / pendiente ** 0.385
    tc_california = (0.87 * longitud_km ** 3 / desnivel_m) ** 0.385
    tc_giandotti = (4 * np.sqrt(area_km2) + 1.5 * longitud_km) / (0.8 * np.sqrt(desnivel_m))

    tcs = np.array([tc_kirpich, tc_california, tc_giandotti])
    return {
        "pendiente": pendiente,
        "desnivel_m": desnivel_m,
        "tc_kirpich": tc_kirpich,
        "tc_california": tc_california,
        "tc_giandotti": tc_giandotti,
        "alerta_dispersion": bool(tcs.max() / tcs.min() > 3),
        "alerta_pendiente": bool(pendiente > 0.5),
    }


def lag_horas(tc_adoptado):
    """Línea 658."""
    return 0.6 * tc_adoptado


def cn_retencion(df_cn):
    """Líneas 685-687."""
    cn_ponderado = float((df_cn["CN_Teórico"] * df_cn["%_Área"] / 100).sum())
    s_ret = 25400 / cn_ponderado - 254
    ia = 0.2 * s_ret
    return {"cn": cn_ponderado, "s_ret": s_ret, "ia": ia}


def ficha_hec(area_km2, ia, cn_ponderado, t_lag):
    """Líneas 699-702."""
    return pd.DataFrame({
        "Parámetro HEC-HMS": ["Area (KM2)", "Initial Abstraction (MM)", "Curve Number", "Impervious (%)", "Lag Time (MIN)"],
        "Valor a Ingresar": [round(area_km2, 2), round(ia, 2), round(cn_ponderado, 1), 0.0, round(t_lag * 60, 1)],
    })


def curva_duracion(df_est):
    """Líneas 731-747 (modulo_caudales, pestaña FDC)."""
    q = df_est["Valor_Registrado"].dropna().sort_values(ascending=False).reset_index(drop=True)
    excedencia = 100.0 * (q.index + 1) / (len(q) + 1)
    df_fdc = pd.DataFrame({"Probabilidad de Excedencia (%)": excedencia, "Caudal (m3/s)": q})
    n_ceros = int((q <= 0).sum())
    q50 = float(np.percentile(q, 50))
    q85 = float(np.percentile(q, 15))
    return {"df_fdc": df_fdc, "n_ceros": n_ceros, "q50": q50, "q85": q85}


def maximos_anuales(df_est):
    """Líneas 470 (PMA) y 754 (QMA): idéntica expresión."""
    return df_est.groupby("AÑO")["Valor_Registrado"].max().reset_index()


def estadisticos_pma(pma_anual):
    """Líneas 494-496."""
    media = pma_anual["Valor_Registrado"].mean()
    desv = pma_anual["Valor_Registrado"].std()
    cv = desv / media * 100 if media > 0 else 0
    return {"media": media, "desv": desv, "cv": cv}


def anios_pma_imputada(df_est):
    """Líneas 455-459."""
    n_imp = int(df_est["IMPUTADO"].sum())
    idx_max = df_est.groupby("AÑO")["Valor_Registrado"].idxmax()
    filas_pma = df_est.loc[idx_max]
    anios = sorted(filas_pma.loc[filas_pma["IMPUTADO"], "AÑO"].astype(int).tolist())
    return {"n_imp": n_imp, "fraccion": n_imp / max(len(df_est), 1), "anios": anios}


def serie_sin_agromet(df_est):
    """Líneas 450-451."""
    df_est = df_est[["FECHA_DT", "AÑO", "MES", "MES_NOMBRE", "Valor_Registrado"]].copy()
    df_est["IMPUTADO"] = False
    return df_est


def precip_mensual(df_est):
    """Línea 478."""
    return df_est.groupby(["AÑO", "MES", "MES_NOMBRE"])["Valor_Registrado"].sum().reset_index()


def precip_anual(df_est):
    """Línea 486."""
    return df_est.groupby("AÑO")["Valor_Registrado"].sum().reset_index()


def tabla_cuantiles(ajuste):
    """Líneas 518-522."""
    return pd.DataFrame({
        "Periodo de Retorno T (Años)": T_OBJETIVO,
        "Probabilidad Excedencia (%)": np.round(100 / T_OBJETIVO, 1),
        **{f"{d} (mm)": np.round(list(ajuste["cuantiles"][d].values()), 2) for d in ajuste["cuantiles"]},
    })


def intensidad_idf(p, duraciones, coef_b):
    """Línea 572: i(d) = P24·(d/24)^b / d  [mm/h]."""
    return p * (duraciones / 24.0) ** coef_b / duraciones


def tabla_hec_hms(tiempos, hieto):
    """Líneas 591-592."""
    return pd.DataFrame({"Tiempo Acumulado (minutos)": tiempos,
                         "Precipitación Incremental (mm)": np.round(hieto, 3)})


def filtrar_por_radio_puro(df, radio_km):
    """Líneas 365-378 (filtrar_por_radio sin los widgets)."""
    col_estacion = next((c for c in df.columns if "ESTACI" in c and "COD" not in c), df.columns[0])
    sin_coord = df.loc[df["LAT_DEC"].isna() | df["LON_DEC"].isna(), col_estacion].unique()
    df = df.dropna(subset=["LAT_DEC", "LON_DEC"]).copy()
    df[COL_DIST] = haversine_vectorizado(LAT_REF, LON_REF, df["LAT_DEC"], df["LON_DEC"])
    df_radio = df[df[COL_DIST] <= radio_km]
    return {"df_radio": df_radio, "col_estacion": col_estacion, "sin_coord": list(sin_coord)}


def info_estaciones(df_radio, col_estacion):
    """Líneas 389-394."""
    agregaciones = {"LAT_DEC": "first", "LON_DEC": "first", COL_DIST: "first"}
    if "ALTITUD" in df_radio.columns:
        agregaciones["ALTITUD"] = "first"
    return df_radio.groupby(col_estacion).agg(agregaciones).reset_index().sort_values(COL_DIST)


def serie_estacion(df_radio, col_estacion, estacion):
    """Línea 408."""
    return df_radio[df_radio[col_estacion] == estacion].sort_values("FECHA_DT").copy()


def niveles_pozo(df_est):
    """Líneas 798-799 y 803."""
    nivel_max = df_est["Valor_Registrado"].max()
    nivel_min = df_est["Valor_Registrado"].min()
    return {"nivel_min": nivel_min, "nivel_max": nivel_max, "amplitud": nivel_max - nivel_min}


def filtrar_parametro(df_est, parametro):
    """Líneas 824-832 (modulo_calidad)."""
    col_param = next((c for c in df_est.columns if "PARAMETRO" in c and "COD" not in c), None)
    opciones = sorted(df_est[col_param].dropna().unique().tolist())
    df_param = df_est[df_est[col_param] == parametro]
    unidad = df_param["UNIDAD"].iloc[0] if "UNIDAD" in df_param.columns and not df_param.empty else ""
    return {"col_param": col_param, "opciones": opciones, "df_param": df_param, "unidad": unidad}
