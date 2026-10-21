"""Casos sintéticos deterministas para la regresión numérica.

Cada caso es una función `caso(api)` que recibe un espacio de nombres con la API del
original (`dashboard_dga_original` + `formulas_originales`) y devuelve un resultado
comparable con `comparar`. Las salidas del original se congelan en `golden/` con
`python tests/generar_golden.py`; ningún caso depende de los archivos DGA reales.
"""

import importlib
import os
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
import pandas as pd

DIR_TESTS = os.path.dirname(os.path.abspath(__file__))
DIR_ORIGINAL = os.path.join(DIR_TESTS, "_original")
RUTA_GOLDEN = os.path.join(DIR_TESTS, "golden", "salidas_original.pkl")
ATOL = 1e-9

CASOS = {}


def caso(fn):
    CASOS[fn.__name__] = fn
    return fn


def api_original():
    """Importa el original congelado (sin ejecutar main) y las fórmulas extraídas de su UI."""
    if DIR_ORIGINAL not in sys.path:
        sys.path.insert(0, DIR_ORIGINAL)
    original = importlib.import_module("dashboard_dga_original")
    formulas = importlib.import_module("formulas_originales")
    publicos = lambda m: {k: v for k, v in vars(m).items() if not k.startswith("__")}
    return SimpleNamespace(**{**publicos(original), **publicos(formulas)})


# ==========================================
# COMPARACIÓN (tolerancia absoluta 1e-9)
# ==========================================
def comparar(obtenido, esperado, ruta="raiz"):
    if isinstance(esperado, pd.DataFrame):
        assert isinstance(obtenido, pd.DataFrame), f"{ruta}: se esperaba DataFrame"
        pd.testing.assert_frame_equal(obtenido, esperado, check_exact=False, rtol=0, atol=ATOL, obj=ruta)
    elif isinstance(esperado, pd.Series):
        assert isinstance(obtenido, pd.Series), f"{ruta}: se esperaba Series"
        pd.testing.assert_series_equal(obtenido, esperado, check_exact=False, rtol=0, atol=ATOL, obj=ruta)
    elif isinstance(esperado, pd.Index):
        pd.testing.assert_index_equal(obtenido, esperado, exact=True, obj=ruta)
    elif isinstance(esperado, np.ndarray):
        obtenido = np.asarray(obtenido)
        assert obtenido.shape == esperado.shape, f"{ruta}: forma {obtenido.shape} != {esperado.shape}"
        if np.issubdtype(esperado.dtype, np.number):
            np.testing.assert_allclose(obtenido, esperado, rtol=0, atol=ATOL, equal_nan=True, err_msg=ruta)
        else:
            np.testing.assert_array_equal(obtenido, esperado, err_msg=ruta)
    elif isinstance(esperado, dict):
        assert isinstance(obtenido, dict), f"{ruta}: se esperaba dict"
        assert list(obtenido.keys()) == list(esperado.keys()), f"{ruta}: claves {list(obtenido)} != {list(esperado)}"
        for k in esperado:
            comparar(obtenido[k], esperado[k], f"{ruta}[{k!r}]")
    elif isinstance(esperado, (list, tuple)):
        assert isinstance(obtenido, (list, tuple)) and len(obtenido) == len(esperado), f"{ruta}: largo distinto"
        for i, (o, e) in enumerate(zip(obtenido, esperado)):
            comparar(o, e, f"{ruta}[{i}]")
    elif isinstance(esperado, (bool, np.bool_, str, bytes)) or esperado is None:
        assert obtenido == esperado, f"{ruta}: {obtenido!r} != {esperado!r}"
    elif isinstance(esperado, (int, float, np.integer, np.floating)):
        if np.isnan(esperado):
            assert np.isnan(obtenido), f"{ruta}: se esperaba NaN, se obtuvo {obtenido!r}"
        else:
            assert abs(obtenido - esperado) <= ATOL, f"{ruta}: {obtenido!r} != {esperado!r}"
    else:
        raise TypeError(f"{ruta}: tipo no soportado {type(esperado)}")


# ==========================================
# DATOS SINTÉTICOS
# ==========================================
CABECERA_DGA = "CODIGO ESTACION,NOMBRE ESTACION,COD_REGION,REGION,COMUNA,LAT,LONG,UTM_ESTE,UTM_NORTE,ALTITUD,{fecha},{var},{extra}Unidad"

# Coordenadas DMS concatenadas como en los archivos DGA (con espacios de relleno)
ESTACIONES = [
    ("06019001", "ESTACION CERCANA", "0343810  ", "0710126  ", 210),   # ~0 km de Lo Moscoso
    ("06008005", "ESTACION MEDIA", "0343000  ", "0705000  ", 480),     # ~26 km
    ("06000003", "ESTACION LEJANA", "0342145  ", "0701819  ", 1296),   # ~70 km
    ("06099999", "ESTACION SIN COORD", "0349999  ", "0710126  ", 100), # segundos = 99 -> NaN
]


def _csv_dga(var, unidad, fechas_por_est, generador, fecha_col="FECHA", extra=""):
    filas = [CABECERA_DGA.format(fecha=fecha_col, var=var, extra=extra)]
    for (cod, nombre, lat, lon, alt), fechas in zip(ESTACIONES, fechas_por_est):
        for f in fechas:
            valor = generador(f)
            filas.append(f"{cod},{nombre},6,DEL LIB.BDO.O'HIGGINS,PLACILLA,{lat},{lon},0,0,{alt},"
                         f"{f.strftime('%d/%m/%Y')},{valor},{'' if not extra else ','}{unidad}")
    return filas


def csv_precipitaciones(encoding="utf-8"):
    rng = np.random.default_rng(10)
    fechas = [
        pd.date_range("2010-07-01", "2013-03-31", freq="D"),
        pd.date_range("2011-01-01", "2012-12-31", freq="D"),
        pd.date_range("2012-01-01", "2012-12-31", freq="D"),
        pd.date_range("2012-06-01", "2012-06-30", freq="D"),
    ]
    # 15 % de días faltantes en la estación cercana (vacíos internos)
    fechas[0] = fechas[0][rng.random(len(fechas[0])) > 0.15]

    def gen(f):
        u = rng.random()
        if u < 0.65:
            return "0"
        if u < 0.66:
            return ""             # valor vacío -> se descarta
        if u < 0.67:
            return '"12,5"'       # coma decimal
        return f"{rng.gamma(0.8, 18.0):.1f}"

    filas = _csv_dga("Precipitación_diaria", "mm", fechas, gen)
    filas.append("06019001,ESTACION CERCANA,6,X,PLACILLA,0343810  ,0710126  ,0,0,210,32/13/2011,5.0,mm")  # fecha inválida
    filas.append("06019001,ESTACION CERCANA,6,X,PLACILLA,0343810  ,0710126  ,0,0,210,15/08/2011,abc,mm")  # valor inválido
    return ("\n".join(filas) + "\n").encode(encoding)


def csv_caudales():
    rng = np.random.default_rng(20)
    fechas = [pd.date_range("2009-04-01", "2012-03-31", freq="D")] * 3 + [pd.date_range("2010-01-01", "2010-01-10")]

    def gen(f):
        base = 2.0 + 6.0 * max(0.0, np.sin(2 * np.pi * (f.dayofyear - 150) / 365))
        if rng.random() < 0.02:
            return "0"
        return f"{base * rng.lognormal(0, 0.4):.3f}"

    return ("\n".join(_csv_dga("Caudal_diario", "m3/s", fechas, gen)) + "\n").encode("utf-8")


def csv_pozos():
    rng = np.random.default_rng(30)
    fechas = [pd.date_range("2005-01-15", "2015-12-15", freq="MS")] * 4

    def gen(f):
        return f"{25 + 3 * np.sin(f.month / 12 * 2 * np.pi) + 0.2 * (f.year - 2005) + rng.normal(0, 0.3):.2f}"

    return ("\n".join(_csv_dga("Nivel", "m", fechas, gen, fecha_col="Fecha", extra="Observacion,")) + "\n").encode("utf-8")


def csv_calidad():
    cab = ("ESTACIÓN,COD. ESTACIÓN,REGIÓN,PROVINCIA,COMUNA,PARAMETRO,COD. PARAMETRO,CUENCA,SUB CUENCA,"
           "SUB SUB CUENCA,FECHA MEDICION,HORA MEDICION,VALOR,CALIDAD,UNIDAD,LATITUD,LONGITUD,ALTITUD,AguProfundidad")
    rng = np.random.default_rng(40)
    estaciones = [("RIO TINGUIRIRICA EN LOS OLMOS", "06034001-0", "343800.0", "710130.0"),
                  ("RIO CLARO EN EL VALLE", "06027001-K", "343000.0", "705000.0")]
    params = [("Ph", "6020", "unid. ph", 7.4, 0.3), ("Conductividad Especifica", "5020", "mhos/cm ", 650, 80),
              ("Sulfato", "7350", "mg/l    ", 120, 25)]
    filas = [cab]
    for nombre, cod, lat, lon in estaciones:
        for f in pd.date_range("1990-03-01", "2000-12-01", freq="QS"):
            for p, codp, uni, mu, sd in params:
                filas.append(f"{nombre},{cod},VI Region,Colchagua,Placilla,{p},{codp},Rio Rapel,X,Y,"
                             f"{f.strftime('%d-%m-%Y')}  ,00:00,{mu + rng.normal(0, sd):.2f}, ,{uni},{lat},{lon},250.0,0.0")
    filas.append(f"{estaciones[0][0]},{estaciones[0][1]},VI Region,Colchagua,Placilla,Sulfato,7350,Rio Rapel,X,Y,"
                 "01-01-2001  ,00:00,<0.01, ,mg/l    ,343800.0,710130.0,250.0,0.0")  # censurado
    filas.append(f"{estaciones[0][0]},{estaciones[0][1]},VI Region,Colchagua,Placilla,Sulfato,7350,Rio Rapel,X,Y,"
                 '02-01-2001  ,00:00,"95,5", ,mg/l    ,343800.0,710130.0,250.0,0.0')  # coma decimal
    return ("\n".join(filas) + "\n").encode("utf-8")


def escribir_agromet(directorio):
    """Tres archivos AGROMET horarios que solapan y extienden el fin de la serie DGA (31/03/2013)."""
    rng = np.random.default_rng(50)
    cab = '"Fecha Hora","Temp. promedio aire","Precipitación horaria","Humed. rel. promedio"'

    def filas(inicio, fin):
        out = [cab]
        for t in pd.date_range(inicio, fin, freq="h"):
            p = 0.0 if rng.random() < 0.8 else round(float(rng.gamma(0.6, 3.0)), 1)
            out.append(f'"{t.strftime("%d/%m/%Y %H:%M")}",15.0,{p},80.0')
        return out

    f1 = filas("2013-03-20 00:00", "2013-03-31 23:00")
    f1.insert(30, '"20/03/2013 05:30",15.0,180.0,80.0')   # > 150 mm/h -> QA/QC
    f1.insert(40, '"20/03/2013 06:30",15.0,,80.0')        # precipitación vacía
    f1.insert(50, '"fecha mala",15.0,3.0,80.0')           # fecha inválida
    f2 = filas("2013-03-29 00:00", "2013-04-12 23:00")    # solapa 29-31/03
    with open(os.path.join(directorio, "agromet_Placilla A-2013.csv"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(f1) + "\n")
    with open(os.path.join(directorio, "agromet_Placilla B-2013.csv"), "w", encoding="latin-1") as fh:
        fh.write("\n".join(f2) + "\n")
    with open(os.path.join(directorio, "agromet_Placilla C-sinlluvia.csv"), "w", encoding="utf-8") as fh:
        fh.write('"Fecha Hora","Temp. promedio aire"\n"01/04/2013 00:00",12.0\n')


def _agromet(api):
    with tempfile.TemporaryDirectory() as d:
        escribir_agromet(d)
        df, avisos = api.cargar_agromet(d)
    return df, sorted(avisos)


def _serie(api, contenido, columna, radio, estacion):
    df = api.cargar_datos(contenido, columna)
    fr = api.filtrar_por_radio_puro(df, radio)
    return api.serie_estacion(fr["df_radio"], fr["col_estacion"], estacion)


def _serie_precip(api):
    return _serie(api, csv_precipitaciones(), "PRECIPIT", 30, "ESTACION CERCANA")


def _serie_imputada(api):
    df_agro, _ = _agromet(api)
    return api.imputar_con_agromet(_serie_precip(api), df_agro)


# ==========================================
# CASOS: funciones puras del original
# ==========================================
DMS_ENTRADAS = [343810, "0342145  ", "0701819  ", 222713.0, 685407.0, -34.636, 71.5, -34.0, 0,
                None, "abc", np.nan, 346099, 1806000, 9999999, "  343810"]


@caso
def dms_a_decimal(api):
    return np.array([api.dms_a_decimal(v) for v in DMS_ENTRADAS], dtype=float)


@caso
def haversine(api):
    rng = np.random.default_rng(1)
    lat, lon = rng.uniform(-36, -33, 50), rng.uniform(-72, -70, 50)
    return {
        "series": api.haversine_vectorizado(-34.636, -71.024, pd.Series(lat), pd.Series(lon)),
        "arrays": api.haversine_vectorizado(-34.636, -71.024, lat, lon),
        "escalar": float(api.haversine_vectorizado(-33.45, -70.66, -34.636, -71.024)),
    }


@caso
def hietograma(api):
    out = {}
    for p24 in (50.0, 87.3):
        for dt in (5, 10, 15, 30):
            for b in (0.1, 0.25, 0.33, 0.5):
                t, h = api.hietograma_bloques_alternos(p24, dt, 24, b)
                out[f"p{p24}_dt{dt}_b{b}"] = (t, h, float(h.sum()))
    out["6h_dt10"] = api.hietograma_bloques_alternos(40.0, 10, 6, 0.33)
    out["defecto"] = api.hietograma_bloques_alternos(60.0, 15)
    return out


def _resumen_ajuste(aj):
    return None if aj is None else {k: aj[k] for k in ("n", "n_ceros", "x_sorted", "t_empirico",
                                                       "cuantiles", "curvas", "ks", "mejor")}


SERIES_PMA = {
    "gumbel_30": lambda r: r.gumbel(40, 15, 30),
    "lognormal_50": lambda r: r.lognormal(3.5, 0.5, 50),
    "asimetria_negativa_20": lambda r: r.uniform(80, 100, 20),
    "con_ceros_y_nan": lambda r: np.concatenate([r.gumbel(25, 8, 10), [0.0, 0.0, np.nan]]),
    "n3_minimo": lambda r: np.array([10.0, 20.0, 35.0]),
    "n2_insuficiente": lambda r: np.array([10.0, 20.0]),
    "solo_ceros": lambda r: np.zeros(5),
}


@caso
def ajustar_distribuciones(api):
    out = {}
    for nombre, gen in SERIES_PMA.items():
        x = gen(np.random.default_rng(2))
        out[nombre] = _resumen_ajuste(api.ajustar_distribuciones(x))
    out["entrada_series"] = _resumen_ajuste(api.ajustar_distribuciones(pd.Series(SERIES_PMA["gumbel_30"](np.random.default_rng(2)))))
    return out


@caso
def leer_csv_codificaciones(api):
    return {
        "utf8": api._leer_csv(csv_precipitaciones("utf-8"), sep=","),
        "latin1": api._leer_csv(csv_precipitaciones("latin-1"), sep=","),
    }


@caso
def cargar_datos(api):
    out = {
        "precip_utf8": api.cargar_datos(csv_precipitaciones("utf-8"), "PRECIPIT"),
        "precip_latin1": api.cargar_datos(csv_precipitaciones("latin-1"), "PRECIPIT"),
        "caudales": api.cargar_datos(csv_caudales(), "CAUDAL"),
        "pozos": api.cargar_datos(csv_pozos(), "NIVEL"),
        "calidad": api.cargar_datos(csv_calidad(), "VALOR"),
    }
    for nombre, (contenido, col) in {
        "sin_fecha": (b"A,B\n1,2\n", "VALOR"),
        "sin_columna": (csv_caudales(), "PRECIPIT"),
        "sin_valor": (b"FECHA,X\n01/01/2000,1\n", "VALOR"),
    }.items():
        try:
            api.cargar_datos(contenido, col)
            out[nombre] = "sin error"
        except ValueError as e:
            out[nombre] = str(e)
    return out


@caso
def cargar_agromet(api):
    df, avisos = _agromet(api)
    with tempfile.TemporaryDirectory() as d:
        vacio = api.cargar_agromet(d)
    return {"df": df, "avisos": avisos, "vacio": vacio}


@caso
def imputar_con_agromet(api):
    df_agro, _ = _agromet(api)
    df_est = _serie_precip(api)
    sintetico_dga = pd.DataFrame({
        "FECHA_DT": pd.to_datetime(["2020-01-01 08:00", "2020-01-01 20:00", "2020-01-03 00:00", "2020-01-06 08:00"]),
        "Valor_Registrado": [2.0, 4.0, 0.0, 10.0],
    })
    sintetico_agro = pd.DataFrame({"FECHA_DT": pd.date_range("2019-12-30", "2020-01-08"),
                                   "Precip_mm": np.arange(10, dtype=float)})
    return {
        "pipeline": api.imputar_con_agromet(df_est, df_agro),
        "sintetico": api.imputar_con_agromet(sintetico_dga, sintetico_agro),
    }


@caso
def agregar_columnas_fecha(api):
    df = pd.DataFrame({"FECHA_DT": pd.date_range("2011-12-25", "2012-01-05"), "x": range(12)})
    return api.agregar_columnas_fecha(df)


@caso
def a_csv(api):
    df = pd.DataFrame({"T": [2, 100], "Gumbel (mm)": [45.123456, 120.5], "Estación": ["Ñ", "a;b"]})
    return api.a_csv(df)


@caso
def validar_tabla_cn(api):
    base = pd.DataFrame({"Cobertura/Suelo": list("abcde"), "GHS (SCS)": list("BCBDC"),
                         "CN_Teórico": [60, 73, 67, 91, 89], "%_Área": [10.0, 45.0, 30.0, 10.0, 5.0]})
    vacia = base.copy()
    vacia.loc[2, "CN_Teórico"] = np.nan
    fuera = base.copy()
    fuera.loc[0, "CN_Teórico"] = 25
    negativa = base.copy()
    negativa["%_Área"] = [-5.0, 60.0, 30.0, 10.0, 5.0]
    suma = base.copy()
    suma.loc[0, "%_Área"] = 10.2
    fila_nueva = base.reindex(range(len(base) + 1))  # fila agregada vacía en st.data_editor
    return {k: api.validar_tabla_cn(v) for k, v in
            dict(base=base, vacia=vacia, fuera=fuera, negativa=negativa, suma=suma, fila_nueva=fila_nueva).items()}


# ==========================================
# CASOS: cálculos en línea de la UI (formulas_originales)
# ==========================================
@caso
def cuenca_tc(api):
    entradas = {
        "defecto_pendiente": (15.5, 8.2, "Pendiente Media (m/m)", 0.045, None),
        "defecto_desnivel": (15.5, 8.2, "Desnivel Topográfico (m)", None, 369.0),
        "grande": (120.0, 25.0, "Pendiente Media (m/m)", 0.01, None),
        "pequena_empinada": (0.5, 1.2, "Desnivel Topográfico (m)", None, 700.0),
    }
    out = {}
    for k, args in entradas.items():
        r = api.tc_cuenca(*args)
        r["lag"] = api.lag_horas(r["tc_kirpich"])
        out[k] = r
    return out


@caso
def cuenca_cn_ficha(api):
    tablas = {
        "defecto": pd.DataFrame({"CN_Teórico": [60, 73, 67, 91, 89], "%_Área": [10.0, 45.0, 30.0, 10.0, 5.0]}),
        "homogenea": pd.DataFrame({"CN_Teórico": [100], "%_Área": [100.0]}),
        "decimales": pd.DataFrame({"CN_Teórico": [55.5, 78.0, 84.0], "%_Área": [33.3, 33.3, 33.4]}),
    }
    out = {}
    for k, t in tablas.items():
        r = api.cn_retencion(t)
        r["ficha"] = api.ficha_hec(15.5, r["ia"], r["cn"], api.lag_horas(1.37))
        out[k] = r
    return out


@caso
def caudales(api):
    df_est = _serie(api, csv_caudales(), "CAUDAL", 40, "ESTACION MEDIA")
    pequena = pd.DataFrame({"Valor_Registrado": [3.0, 0.0, 1.5, np.nan, 7.2]})
    return {
        "fdc": api.curva_duracion(df_est),
        "fdc_pequena": api.curva_duracion(pequena),
        "qma": api.maximos_anuales(df_est),
    }


@caso
def precipitaciones_sin_agromet(api):
    df_est = api.serie_sin_agromet(_serie_precip(api))
    pma = api.maximos_anuales(df_est)
    aj = api.ajustar_distribuciones(pma["Valor_Registrado"])
    return {
        "serie": df_est,
        "mensual": api.precip_mensual(df_est),
        "anual": api.precip_anual(df_est),
        "pma": pma,
        "estadisticos": api.estadisticos_pma(pma),
        "ajuste": _resumen_ajuste(aj),
    }


@caso
def precipitaciones_con_agromet(api):
    df_est = _serie_imputada(api)
    pma = api.maximos_anuales(df_est)
    aj = api.ajustar_distribuciones(pma["Valor_Registrado"])
    return {
        "imputacion": api.anios_pma_imputada(df_est),
        "pma": pma,
        "estadisticos": api.estadisticos_pma(pma),
        "ajuste": _resumen_ajuste(aj),
        "estadisticos_media_cero": api.estadisticos_pma(pd.DataFrame({"Valor_Registrado": [0.0, 0.0]})),
    }


@caso
def tormenta_diseno(api):
    aj = api.ajustar_distribuciones(SERIES_PMA["gumbel_30"](np.random.default_rng(2)))
    duraciones = np.linspace(0.25, 24, 100)
    out = {"cuantiles": api.tabla_cuantiles(aj)}
    for dist in aj["cuantiles"]:
        for t in (50, 100, 500):
            p = aj["cuantiles"][dist][t]
            out[f"idf_{dist}_{t}"] = api.intensidad_idf(p, duraciones, 0.33)
        tiempos, hieto = api.hietograma_bloques_alternos(aj["cuantiles"][dist][100], 15, 24, 0.33)
        out[f"hec_{dist}"] = api.tabla_hec_hms(tiempos, hieto)
    return out


@caso
def red_estaciones(api):
    df = api.cargar_datos(csv_precipitaciones(), "PRECIPIT")
    out = {}
    for radio in (10, 30, 100):
        fr = api.filtrar_por_radio_puro(df, radio)
        out[f"radio_{radio}"] = {
            "n_filas": len(fr["df_radio"]),
            "distancias": fr["df_radio"]["Distancia_km"],
            "col_estacion": fr["col_estacion"],
            "sin_coord": fr["sin_coord"],
            "info": api.info_estaciones(fr["df_radio"], fr["col_estacion"]),
        }
    return out


@caso
def pozos(api):
    df_est = _serie(api, csv_pozos(), "NIVEL", 50, "ESTACION MEDIA")
    return {"serie": df_est, "niveles": api.niveles_pozo(df_est)}


@caso
def calidad(api):
    df_est = _serie(api, csv_calidad(), "VALOR", 60, "RIO TINGUIRIRICA EN LOS OLMOS")
    return {p: api.filtrar_parametro(df_est, p) for p in ("Sulfato", "Ph", "Inexistente")}
