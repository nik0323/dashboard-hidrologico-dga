"""Expone el paquete `hidro` con la misma API que usan los casos de `casos.py`.

Así cada caso se ejecuta contra el código nuevo y se compara con las salidas congeladas
del original (golden). Las funciones aún no migradas se toman del original.
"""

from dataclasses import asdict
from types import SimpleNamespace

from casos import api_original
from hidro.config import RUTA_SETTINGS_DEFECTO, cargar_settings
from hidro.core import calidad, caudales, cuenca, estaciones, frecuencia, geo, series, tormentas
from hidro.io import exportar, imputacion, lectura, normalizacion
from hidro.io.normalizacion import columna_estacion as _columna_estacion
from hidro.io.normalizacion import columna_parametro as _columna_parametro

# Parámetros desde settings.toml (test_config verifica que igualan al original)
_S = cargar_settings(RUTA_SETTINGS_DEFECTO)
LAT_REF, LON_REF = _S.punto_control.lat, _S.punto_control.lon
T_OBJETIVO = _S.t_objetivo
N_MIN_AJUSTE = _S.n_min_ajuste
PATRON_AGROMET = _S.patron_agromet
QA_MAX_PRECIP_HORARIA = _S.qa_max_precip_horaria_mm


class _Ajuste(dict):
    """Vista dict de ResultadoAjuste (formato del original) que conserva el objeto en `.obj`."""

    def __init__(self, r):
        super().__init__(n=r.n, n_ceros=r.n_ceros, x_sorted=r.x_sorted, t_empirico=r.t_empirico,
                         cuantiles=r.cuantiles, curvas=r.curvas, ks=r.ks, mejor=r.mejor)
        self.obj = r


def _ajustar_distribuciones(x):
    r = frecuencia.ajustar_distribuciones(x, T_OBJETIVO, N_MIN_AJUSTE, n_bootstrap=_S.n_bootstrap,
                                          semilla=_S.semilla_bootstrap, alfa=_S.alfa_ks)
    return None if r is None else _Ajuste(r)


def _tc_cuenca(area_km2, longitud_km, modo, pendiente=None, desnivel_m=None):
    if modo == "Pendiente Media (m/m)":
        geom = cuenca.geometria_desde_pendiente(longitud_km, pendiente)
    else:
        geom = cuenca.geometria_desde_desnivel(longitud_km, desnivel_m)
    # El original usaba el desnivel del cauce como H de Giandotti (hallazgo #3); los casos del golden
    # validan la fórmula con esa misma entrada.
    tcs = cuenca.tiempos_concentracion(area_km2, longitud_km, geom, geom.desnivel_m)
    return {
        "pendiente": geom.pendiente,
        "desnivel_m": geom.desnivel_m,
        "tc_kirpich": tcs.kirpich,
        "tc_california": tcs.california,
        "tc_giandotti": tcs.giandotti,
        "alerta_dispersion": tcs.dispersion_excesiva(),
        "alerta_pendiente": bool(geom.pendiente > cuenca.PENDIENTE_ALERTA),
    }


def _cn_retencion(df_cn):
    cn = cuenca.cn_ponderado(df_cn)
    ret = cuenca.retencion_scs(cn)
    return {"cn": cn, "s_ret": ret.s_ret, "ia": ret.ia}


def _curva_duracion(df_est):
    r = caudales.curva_duracion(df_est["Valor_Registrado"])
    return {"df_fdc": r.tabla, "n_ceros": r.n_ceros, "q50": r.q50, "q85": r.q85}


def _filtrar_por_radio(df, radio_km):
    col = _columna_estacion(df.columns)
    r = estaciones.filtrar_por_radio(df, LAT_REF, LON_REF, radio_km, col)
    return {"df_radio": r.df_radio, "col_estacion": col, "sin_coord": r.sin_coordenadas}


def _filtrar_parametro(df_est, parametro):
    col = _columna_parametro(df_est.columns)
    df_param, unidad = calidad.filtrar_parametro(df_est, col, parametro)
    return {"col_param": col, "opciones": calidad.parametros_disponibles(df_est, col),
            "df_param": df_param, "unidad": unidad}


MIGRADAS = {
    # io/
    "_leer_csv": lectura.leer_csv,
    "cargar_datos": lectura.cargar_serie_dga,
    "cargar_agromet": lambda d: lectura.cargar_agromet(d, PATRON_AGROMET, QA_MAX_PRECIP_HORARIA,
                                                       _S.agromet_desfase_horas, _S.agromet_horas_min_dia),
    "imputar_con_agromet": lambda dga, agro: imputacion.imputar_con_agromet(
        dga, agro, cobertura_min_anual=_S.cobertura_min_anual),
    "serie_sin_agromet": imputacion.serie_sin_imputar,
    "anios_pma_imputada": lambda df: dict(zip(("n_imp", "fraccion", "anios"),
                                              asdict(imputacion.resumen_imputacion(df)).values())),
    "agregar_columnas_fecha": normalizacion.agregar_columnas_fecha,
    "a_csv": exportar.a_csv,
    # core/
    "dms_a_decimal": geo.dms_a_decimal,
    "haversine_vectorizado": geo.haversine_vectorizado,
    "hietograma_bloques_alternos": tormentas.hietograma_bloques_alternos,
    "ajustar_distribuciones": _ajustar_distribuciones,
    "tabla_cuantiles": lambda aj: frecuencia.tabla_cuantiles(aj.obj),
    "intensidad_idf": tormentas.intensidad_idf,
    "tabla_hec_hms": tormentas.tabla_hec_hms,
    "validar_tabla_cn": cuenca.validar_tabla_cn,
    "tc_cuenca": _tc_cuenca,
    "lag_horas": cuenca.lag_scs,
    "cn_retencion": _cn_retencion,
    "ficha_hec": cuenca.ficha_hec_hms,
    "curva_duracion": _curva_duracion,
    "maximos_anuales": lambda df: series.maximos_anuales(df, _S.cobertura_min_maximos),
    "estadisticos_pma": lambda pma: asdict(series.estadisticos(pma)),
    "precip_mensual": series.totales_mensuales,
    "precip_anual": series.totales_anuales,
    "niveles_pozo": lambda df: asdict(series.rango_niveles(df)),
    "filtrar_por_radio_puro": _filtrar_por_radio,
    "info_estaciones": estaciones.resumen_estaciones,
    "serie_estacion": estaciones.serie_estacion,
    "filtrar_parametro": _filtrar_parametro,
}


def api_hidro():
    """Solo funciones de `hidro`: si un caso pide algo no migrado, falla con AttributeError."""
    api_original()  # carga dashboard_dga_original en sys.path para formulas_originales
    return SimpleNamespace(**MIGRADAS)
