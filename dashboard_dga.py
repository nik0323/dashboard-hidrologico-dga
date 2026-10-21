"""
Plataforma de Análisis Hidrológico e Hidrogeológico DGA
=======================================================

Ejecutar con:
    streamlit run dashboard_dga.py

Carpeta de datos (en orden de prioridad):
    1. Lo que escribas en la barra lateral ("Carpeta de datos").
    2. La variable de entorno DGA_DATA_DIR.
    3. La carpeta por defecto definida en DIR_DATOS_DEFAULT.
Si un archivo no se encuentra en la carpeta, el módulo ofrece subirlo desde el navegador.
"""

import glob
import io
import logging
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import gumbel_r, kstest, lognorm, pearson3, skew

# ==========================================
# CONFIGURACIÓN GENERAL
# ==========================================
st.set_page_config(page_title="Plataforma de Análisis Hidrológico e Hidrogeológico DGA", layout="wide")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dashboard_dga")

DIR_DATOS_DEFAULT = os.environ.get(
    "DGA_DATA_DIR", r"C:\Users\nicos\OneDrive\Escritorio\PRECIPITACIONES"
)

ARCHIVOS = {
    "precipitaciones": "prep_diarias_historico_6.txt",
    "caudales": "caudal_diario_historico.txt",
    "pozos": "niveles_estaticos_pozos_historico.txt",
    "calidad": "calidad_agua_historico.txt",
}
PATRON_AGROMET = "*agromet_Placilla*.csv"

# Punto de control (Lo Moscoso, Placilla)
LAT_REF = -34.636
LON_REF = -71.024
NOMBRE_REF = "Lo Moscoso"
COL_DIST = "Distancia_km"

ORDEN_MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
T_OBJETIVO = np.array([2, 5, 10, 25, 50, 100, 200, 500])
N_MIN_AJUSTE = 3          # mínimo absoluto de años para ajustar distribuciones
N_RECOMENDADO = 15        # mínimo recomendado para extrapolar
QA_MAX_PRECIP_HORARIA = 150.0  # mm/h, umbral QA/QC AGROMET


# ==========================================
# FUNCIONES MATEMÁTICAS Y DE CONVERSIÓN
# ==========================================
def dms_a_decimal(dms_val):
    """Convierte coordenadas DGA (DMS concatenado, ej. 343810) a grados decimales (hemisferio sur/oeste).

    Si el valor ya parece estar en grados decimales (|v| <= 180 con parte fraccionaria), se respeta.
    Devuelve NaN si el valor no es interpretable o tiene minutos/segundos fuera de rango.
    """
    try:
        v = float(dms_val)
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(v):
        return np.nan

    # Coordenada ya en grados decimales
    if abs(v) <= 180 and v != int(v):
        return -abs(v)

    val_str = str(abs(int(v))).zfill(6)
    s = float(val_str[-2:])
    m = float(val_str[-4:-2])
    d = float(val_str[:-4])
    if m >= 60 or s >= 60 or d > 180:
        return np.nan
    return -(d + m / 60.0 + s / 3600.0)


def haversine_vectorizado(lat_ref, lon_ref, lat_series, lon_series):
    """Distancia geodésica (Haversine) en km, vectorizada con NumPy."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat_ref, lon_ref, lat_series, lon_series])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def hietograma_bloques_alternos(p24, dt_minutos, duracion_total_horas=24, b=0.33):
    """Hietograma de diseño por Bloques Alternos con desagregación potencial P(d) = P24·(d/24)^b."""
    dt_horas = dt_minutos / 60.0
    n_bloques = int(round(duracion_total_horas / dt_horas))
    t_array = np.arange(1, n_bloques + 1) * dt_horas

    p_d = p24 * (t_array / duracion_total_horas) ** b
    delta_p = np.diff(p_d, prepend=0.0)
    delta_p_sorted = np.sort(delta_p)[::-1]

    hietograma = np.zeros(n_bloques)
    centro = (n_bloques - 1) // 2
    hietograma[centro] = delta_p_sorted[0]
    izq, der = centro - 1, centro + 1

    for i in range(1, n_bloques):
        derecha = (i % 2 != 0 and der < n_bloques) or izq < 0
        if derecha:
            hietograma[der] = delta_p_sorted[i]
            der += 1
        else:
            hietograma[izq] = delta_p_sorted[i]
            izq -= 1

    tiempo_array = np.arange(1, n_bloques + 1) * dt_minutos
    return tiempo_array, hietograma


def ajustar_distribuciones(serie_maximos):
    """Ajusta Gumbel, Log-Pearson III y Log-Normal a una serie de máximos anuales.

    Devuelve un dict con cuantiles de diseño, curvas para graficar y prueba de bondad de
    ajuste Kolmogorov-Smirnov. Devuelve None si no hay datos suficientes.
    """
    x = np.asarray(serie_maximos, dtype=float)
    x = x[np.isfinite(x)]
    n_ceros = int((x <= 0).sum())
    x = x[x > 0]  # los modelos logarítmicos no admiten ceros
    n = len(x)
    if n < N_MIN_AJUSTE:
        return None

    # Posición de graficación de Weibull
    x_sorted = np.sort(x)[::-1]
    t_empirico = (n + 1) / np.arange(1, n + 1)
    p_emp = 1 - 1 / t_empirico
    p_obj = 1 - 1 / T_OBJETIVO

    # Gumbel (método de momentos)
    media, desv = np.mean(x), np.std(x, ddof=1)
    alpha_g = desv * np.sqrt(6) / np.pi
    u_g = media - 0.5772 * alpha_g

    # Log-Pearson III (momentos de log10)
    log_x = np.log10(x)
    mean_log, std_log = np.mean(log_x), np.std(log_x, ddof=1)
    skew_log = float(skew(log_x, bias=False)) if n > 2 else 0.0

    # Log-Normal (máxima verosimilitud, loc = 0)
    shape_ln, loc_ln, scale_ln = lognorm.fit(x, floc=0)

    modelos = {
        "Gumbel": {
            "ppf": lambda p: gumbel_r.ppf(p, loc=u_g, scale=alpha_g),
            "ks": kstest(x, "gumbel_r", args=(u_g, alpha_g)),
        },
        "Log-Pearson III": {
            "ppf": lambda p: 10 ** pearson3.ppf(p, skew_log, loc=mean_log, scale=std_log),
            "ks": kstest(log_x, "pearson3", args=(skew_log, mean_log, std_log)),
        },
        "Log-Normal": {
            "ppf": lambda p: lognorm.ppf(p, shape_ln, loc=loc_ln, scale=scale_ln),
            "ks": kstest(x, "lognorm", args=(shape_ln, loc_ln, scale_ln)),
        },
    }

    d_critico = 1.36 / np.sqrt(n)  # aproximación α = 0.05
    cuantiles, curvas, filas_ks = {}, {}, []
    for nombre, mod in modelos.items():
        valores = mod["ppf"](p_obj)
        cuantiles[nombre] = {int(t): float(v) for t, v in zip(T_OBJETIVO, valores)}
        curvas[nombre] = mod["ppf"](p_emp)
        d_stat, p_val = mod["ks"].statistic, mod["ks"].pvalue
        filas_ks.append({
            "Distribución": nombre,
            "Estadístico D": round(float(d_stat), 4),
            "D crítico (α=0.05)": round(float(d_critico), 4),
            "p-valor": round(float(p_val), 4),
            "Resultado": "Aceptada" if d_stat < d_critico else "Rechazada",
        })

    df_ks = pd.DataFrame(filas_ks).sort_values("Estadístico D").reset_index(drop=True)
    return {
        "n": n,
        "n_ceros": n_ceros,
        "x_sorted": x_sorted,
        "t_empirico": t_empirico,
        "cuantiles": cuantiles,
        "curvas": curvas,
        "ks": df_ks,
        "mejor": df_ks.loc[0, "Distribución"],
    }


# ==========================================
# CARGA Y TRANSFORMACIÓN DE DATOS (ETL)
# ==========================================
def _leer_csv(fuente, **kwargs):
    """Lee un CSV desde una ruta o desde bytes, probando UTF-8 y luego Latin-1."""
    for encoding in ("utf-8", "latin-1"):
        try:
            origen = io.BytesIO(fuente) if isinstance(fuente, (bytes, bytearray)) else fuente
            return pd.read_csv(origen, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            logger.info("Codificación %s falló, probando la siguiente.", encoding)
    raise ValueError("No fue posible decodificar el archivo con UTF-8 ni Latin-1.")


@st.cache_data(show_spinner=False)
def cargar_datos(fuente, columna_valor):
    """Lee una serie DGA y homologa cabeceras. `fuente` puede ser una ruta o los bytes de un archivo subido."""
    df = _leer_csv(fuente, sep=",")
    df.columns = df.columns.str.strip().str.upper()
    df = df.rename(columns={"FECHA MEDICION": "FECHA", "LATITUD": "LAT", "LONGITUD": "LONG"})

    if "FECHA" not in df.columns:
        raise ValueError(f"El archivo no tiene columna de fecha. Columnas: {list(df.columns)}")

    df["FECHA_DT"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors="coerce")
    df["AÑO"] = df["FECHA_DT"].dt.year
    df["MES"] = df["FECHA_DT"].dt.month
    df["MES_NOMBRE"] = df["FECHA_DT"].dt.strftime("%b")

    if columna_valor == "VALOR":
        col_var = "VALOR" if "VALOR" in df.columns else None
    else:
        col_var = next((c for c in df.columns if columna_valor.upper() in c), None)
    if col_var is None:
        raise ValueError(f"No se encontró una columna que contenga '{columna_valor}'. Columnas: {list(df.columns)}")

    df = df.rename(columns={col_var: "Valor_Registrado"})
    if df["Valor_Registrado"].dtype == "object":
        df["Valor_Registrado"] = df["Valor_Registrado"].astype(str).str.replace(",", ".", regex=False)
    df["Valor_Registrado"] = pd.to_numeric(df["Valor_Registrado"], errors="coerce")

    if "LAT" in df.columns and "LONG" in df.columns:
        df["LAT_DEC"] = df["LAT"].apply(dms_a_decimal)
        df["LON_DEC"] = df["LONG"].apply(dms_a_decimal)

    n_antes = len(df)
    df = df.dropna(subset=["FECHA_DT", "Valor_Registrado"])
    if len(df) < n_antes:
        logger.info("Se descartaron %d filas con fecha o valor inválido.", n_antes - len(df))
    return df


@st.cache_data(show_spinner=False)
def cargar_agromet(directorio_base):
    """Lee estaciones AGROMET auxiliares, aplica QA/QC y agrega a precipitación diaria.

    Devuelve (DataFrame diario, lista de advertencias).
    """
    archivos = glob.glob(os.path.join(directorio_base, PATRON_AGROMET))
    advertencias = []
    lista = []
    for archivo in archivos:
        nombre = os.path.basename(archivo)
        try:
            df = _leer_csv(archivo)
        except (OSError, ValueError, pd.errors.ParserError) as e:
            advertencias.append(f"{nombre}: no se pudo leer ({e}).")
            logger.warning("AGROMET %s ilegible: %s", nombre, e)
            continue

        col_fecha = df.columns[0]
        col_precip = next((c for c in df.columns if "PRECIPIT" in c.upper()), None)
        if col_precip is None:
            advertencias.append(f"{nombre}: sin columna de precipitación, se omite.")
            continue

        df["FECHA_DT"] = pd.to_datetime(df[col_fecha], format="%d/%m/%Y %H:%M", errors="coerce")
        df["Precip_mm"] = pd.to_numeric(df[col_precip], errors="coerce").fillna(0)

        n_qa = int((df["Precip_mm"] > QA_MAX_PRECIP_HORARIA).sum())
        if n_qa:
            advertencias.append(f"{nombre}: {n_qa} registros > {QA_MAX_PRECIP_HORARIA:.0f} mm/h anulados por QA/QC.")
        df.loc[df["Precip_mm"] > QA_MAX_PRECIP_HORARIA, "Precip_mm"] = 0.0

        df = df.dropna(subset=["FECHA_DT"])
        diario = df.groupby(df["FECHA_DT"].dt.normalize())["Precip_mm"].sum().reset_index()
        lista.append(diario)

    if not lista:
        return pd.DataFrame(columns=["FECHA_DT", "Precip_mm"]), advertencias

    total = pd.concat(lista, ignore_index=True).sort_values("FECHA_DT")
    total = total.drop_duplicates(subset=["FECHA_DT"])
    return total, advertencias


def imputar_con_agromet(df_estacion, df_agro):
    """Rellena días sin dato de la estación DGA con AGROMET, alineando por fecha.

    Devuelve un DataFrame diario con columna booleana IMPUTADO.
    """
    serie = df_estacion.groupby(df_estacion["FECHA_DT"].dt.normalize())["Valor_Registrado"].mean()
    agro = df_agro.set_index("FECHA_DT")["Precip_mm"]

    indice = serie.index.union(agro.index)
    serie = serie.reindex(indice)
    faltantes = serie.isna()
    serie = serie.fillna(agro.reindex(indice))

    out = pd.DataFrame({
        "FECHA_DT": indice,
        "Valor_Registrado": serie.values,
        "IMPUTADO": (faltantes & serie.notna()).values,
    }).dropna(subset=["Valor_Registrado"])
    return agregar_columnas_fecha(out)


def agregar_columnas_fecha(df):
    df = df.copy()
    df["AÑO"] = df["FECHA_DT"].dt.year
    df["MES"] = df["FECHA_DT"].dt.month
    df["MES_NOMBRE"] = df["FECHA_DT"].dt.strftime("%b")
    return df


def a_csv(df):
    """CSV listo para Excel en configuración regional chilena (; y coma decimal)."""
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


# ==========================================
# COMPONENTES DE INTERFAZ REUTILIZABLES
# ==========================================
def obtener_fuente(clave, dir_datos):
    """Devuelve la ruta del archivo si existe en la carpeta; si no, ofrece subirlo. Detiene la app si no hay datos."""
    nombre = ARCHIVOS[clave]
    ruta = os.path.join(dir_datos, nombre)
    if os.path.isfile(ruta):
        return ruta

    st.warning(f"No se encontró **{nombre}** en `{dir_datos}`. Puedes subir el archivo aquí:")
    subido = st.file_uploader(f"Subir {nombre}", type=["txt", "csv"], key=f"upload_{clave}")
    if subido is None:
        st.stop()
    return subido.getvalue()


def cargar_o_detener(fuente, columna_valor, mensaje):
    with st.spinner(mensaje):
        try:
            return cargar_datos(fuente, columna_valor)
        except (OSError, ValueError, pd.errors.ParserError) as e:
            logger.exception("Error al cargar datos")
            st.error(f"No se pudieron cargar los datos: {e}")
            st.stop()


def filtrar_por_radio(df, radio_default, radio_max=100, paso=5):
    """Calcula distancia al punto de control, filtra por radio (slider lateral) y devuelve (df_radio, col_estacion)."""
    if "LAT_DEC" not in df.columns:
        st.error("El archivo no contiene coordenadas (LATITUD / LONGITUD).")
        st.stop()

    col_estacion = next((c for c in df.columns if "ESTACI" in c and "COD" not in c), df.columns[0])

    sin_coord = df.loc[df["LAT_DEC"].isna() | df["LON_DEC"].isna(), col_estacion].unique()
    if len(sin_coord):
        st.sidebar.caption(f"⚠️ {len(sin_coord)} estación(es) con coordenadas inválidas fueron excluidas.")
        logger.warning("Estaciones sin coordenadas válidas: %s", list(sin_coord))

    df = df.dropna(subset=["LAT_DEC", "LON_DEC"]).copy()
    df[COL_DIST] = haversine_vectorizado(LAT_REF, LON_REF, df["LAT_DEC"], df["LON_DEC"])

    st.sidebar.header("Filtros Espaciales")
    radio_km = st.sidebar.slider("Radio de Búsqueda (km):", min_value=10, max_value=radio_max,
                                 value=radio_default, step=paso)
    df_radio = df[df[COL_DIST] <= radio_km]
    if df_radio.empty:
        st.warning(f"No hay estaciones a menos de {radio_km} km de {NOMBRE_REF}. Aumenta el radio de búsqueda.")
        st.stop()
    return df_radio, col_estacion


def mostrar_red_estaciones(df_radio, col_estacion, titulo_seccion, titulo_mapa, escala, etiqueta_selector):
    """Dibuja el mapa de estaciones y el selector. Devuelve (nombre_estacion, df_estacion ordenado)."""
    st.header(titulo_seccion)

    agregaciones = {"LAT_DEC": "first", "LON_DEC": "first", COL_DIST: "first"}
    hover = [COL_DIST]
    if "ALTITUD" in df_radio.columns:
        agregaciones["ALTITUD"] = "first"
        hover.append("ALTITUD")
    info = df_radio.groupby(col_estacion).agg(agregaciones).reset_index().sort_values(COL_DIST)

    fig = px.scatter_mapbox(
        info, lat="LAT_DEC", lon="LON_DEC", hover_name=col_estacion, hover_data=hover,
        color=COL_DIST, color_continuous_scale=escala, zoom=9, height=400, title=titulo_mapa,
        labels={COL_DIST: f"Distancia a {NOMBRE_REF} (km)"},
    )
    fig.update_traces(marker=dict(size=12))
    fig.add_scattermapbox(lat=[LAT_REF], lon=[LON_REF], mode="markers",
                          marker=dict(size=14, color="red"), name=f"Punto de Control ({NOMBRE_REF})")
    fig.update_layout(mapbox_style="open-street-map", margin={"r": 0, "t": 40, "l": 0, "b": 0})
    st.plotly_chart(fig, use_container_width=True)

    estacion = st.selectbox(etiqueta_selector, info[col_estacion].tolist())
    df_est = df_radio[df_radio[col_estacion] == estacion].sort_values("FECHA_DT").copy()
    return estacion, df_est


def encabezado(titulo, fuente, fundamento):
    st.title(titulo)
    st.caption(fuente)
    st.markdown(f"**Fundamento Técnico:** {fundamento}")


def justificacion(texto):
    st.markdown(f"**Justificación Técnica:** {texto}")


# ==========================================
# MÓDULO 1: PRECIPITACIONES
# ==========================================
def modulo_precipitaciones(dir_datos):
    encabezado(
        "Análisis Espacial de Precipitaciones DGA",
        "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas (mapas2.mop.gob.cl).",
        f"Evaluación de parámetros pluviométricos para el diseño hidrológico de obras civiles y mitigación de amenazas aluvionales en el sector {NOMBRE_REF}.",
    )

    fuente = obtener_fuente("precipitaciones", dir_datos)
    df = cargar_o_detener(fuente, "PRECIPIT", "Procesando series de tiempo pluviométricas...")
    df_radio, col_est = filtrar_por_radio(df, radio_default=30)
    estacion, df_est = mostrar_red_estaciones(
        df_radio, col_est, "1. Red de Monitoreo Pluviométrico",
        "Distribución de Estaciones Pluviométricas (Gradiente de proximidad)",
        px.colors.sequential.Teal, "Seleccione la estación para extracción de datos:",
    )

    # --- Imputación AGROMET (opcional y trazable) ---
    df_agro, avisos_agro = cargar_agromet(dir_datos) if os.path.isdir(dir_datos) else (pd.DataFrame(), [])
    usar_agromet = False
    if not df_agro.empty:
        usar_agromet = st.sidebar.checkbox("Rellenar vacíos con AGROMET", value=True,
                                           help="Completa los días sin registro DGA con la estación auxiliar AGROMET.")
    if usar_agromet:
        df_est = imputar_con_agromet(df_est, df_agro)
    else:
        df_est = df_est[["FECHA_DT", "AÑO", "MES", "MES_NOMBRE", "Valor_Registrado"]].copy()
        df_est["IMPUTADO"] = False

    st.header(f"2. Análisis Hidrometeorológico: {estacion}")

    n_imp = int(df_est["IMPUTADO"].sum())
    if usar_agromet:
        idx_max = df_est.groupby("AÑO")["Valor_Registrado"].idxmax()
        filas_pma = df_est.loc[idx_max]
        anios_pma_imputada = sorted(filas_pma.loc[filas_pma["IMPUTADO"], "AÑO"].astype(int).tolist())
        with st.expander(f"Imputación AGROMET: {n_imp:,} días rellenados ({n_imp / max(len(df_est), 1):.1%} de la serie)",
                         expanded=bool(anios_pma_imputada)):
            if anios_pma_imputada:
                st.warning("En estos años la PMA proviene de un día imputado, lo que afecta los cuantiles de diseño: "
                           + ", ".join(map(str, anios_pma_imputada)))
            else:
                st.write("Ninguna PMA anual proviene de un día imputado.")
            for aviso in avisos_agro:
                st.caption(aviso)

    pma_anual = df_est.groupby("AÑO")["Valor_Registrado"].max().reset_index()
    ajuste = ajustar_distribuciones(pma_anual["Valor_Registrado"])

    tabs = st.tabs(["Régimen Estacional", "Acumulación Interanual", "Análisis de Extremos (PMA)",
                    "Ajuste Probabilístico", "Hietogramas de Diseño (HEC-HMS)"])

    with tabs[0]:
        justificacion("Determinación de la concentración estacional de las precipitaciones para establecer condiciones de humedad antecedente.")
        mensual = df_est.groupby(["AÑO", "MES", "MES_NOMBRE"])["Valor_Registrado"].sum().reset_index()
        fig = px.box(mensual, x="MES_NOMBRE", y="Valor_Registrado", category_orders={"MES_NOMBRE": ORDEN_MESES},
                     labels={"MES_NOMBRE": "Mes", "Valor_Registrado": "Precipitación Total Mensual (mm)"},
                     color_discrete_sequence=["#2E5B82"], points="all")
        st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        justificacion("Evaluación del comportamiento acumulativo para la identificación de déficit hídrico prolongado.")
        anual = df_est.groupby("AÑO")["Valor_Registrado"].sum().reset_index()
        fig = px.bar(anual, x="AÑO", y="Valor_Registrado",
                     labels={"AÑO": "Año", "Valor_Registrado": "Precipitación Anual (mm)"},
                     color="Valor_Registrado", color_continuous_scale="Blues")
        st.plotly_chart(fig, use_container_width=True)

    with tabs[2]:
        justificacion("Cuantificación de la Precipitación Máxima Diaria Anual (PMA). Parámetro normativo para hietogramas de diseño.")
        media = pma_anual["Valor_Registrado"].mean()
        desv = pma_anual["Valor_Registrado"].std()
        cv = desv / media * 100 if media > 0 else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Media PMA (μ)", f"{media:.1f} mm")
        c2.metric("Desv. Estándar (σ)", f"{desv:.1f} mm")
        c3.metric("Coef. de Variación (CV)", f"{cv:.1f} %")
        st.divider()
        fig = px.line(pma_anual, x="AÑO", y="Valor_Registrado", markers=True,
                      labels={"AÑO": "Año", "Valor_Registrado": "PMA 24h (mm/día)"},
                      color_discrete_sequence=["#d62728"])
        st.plotly_chart(fig, use_container_width=True)

    with tabs[3]:
        justificacion("Modelación probabilística de la serie empírica de extremos para proyectar las Precipitaciones Máximas Diarias asociadas a los periodos de retorno (T).")
        if ajuste is None:
            st.error(f"Se requieren al menos {N_MIN_AJUSTE} años con PMA > 0 para ajustar distribuciones.")
        else:
            if ajuste["n"] < N_RECOMENDADO:
                st.warning(f"La serie tiene {ajuste['n']} años de registro (< {N_RECOMENDADO}). "
                           "La extrapolación a periodos de retorno elevados tiene validez estadística limitada.")
            if ajuste["n_ceros"]:
                st.caption(f"Se excluyeron {ajuste['n_ceros']} años con PMA = 0 (incompatibles con modelos logarítmicos).")

            df_res = pd.DataFrame({
                "Periodo de Retorno T (Años)": T_OBJETIVO,
                "Probabilidad Excedencia (%)": np.round(100 / T_OBJETIVO, 1),
                **{f"{d} (mm)": np.round(list(ajuste["cuantiles"][d].values()), 2) for d in ajuste["cuantiles"]},
            })
            st.subheader("Cuantiles de Precipitación de Diseño (PMA 24h)")
            st.dataframe(df_res.set_index("Periodo de Retorno T (Años)"), use_container_width=True)

            st.subheader("Bondad de Ajuste (Kolmogorov-Smirnov)")
            st.dataframe(ajuste["ks"], use_container_width=True, hide_index=True)
            st.caption(f"Menor estadístico D: **{ajuste['mejor']}**. Nota: los parámetros se estiman con la misma muestra, "
                       "por lo que la prueba KS es conservadora (tiende a aceptar). Úsela junto con la inspección gráfica.")

            c1, c2 = st.columns(2)
            c1.download_button("Descargar cuantiles (CSV)", a_csv(df_res), f"cuantiles_PMA_{estacion}.csv", "text/csv")
            c2.download_button("Descargar prueba KS (CSV)", a_csv(ajuste["ks"]), f"bondad_ajuste_{estacion}.csv", "text/csv")

            estilos = {"Gumbel": ("blue", "solid"), "Log-Pearson III": ("red", "dash"), "Log-Normal": ("green", "dot")}
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ajuste["t_empirico"], y=ajuste["x_sorted"], mode="markers",
                                     name="Datos Empíricos (Weibull)", marker=dict(color="black", size=8)))
            for dist, (color, dash) in estilos.items():
                fig.add_trace(go.Scatter(x=ajuste["t_empirico"], y=ajuste["curvas"][dist], mode="lines",
                                         name=f"Distribución {dist}", line=dict(color=color, dash=dash)))
            fig.update_layout(
                title="Curvas de Frecuencia Teóricas vs Empíricas",
                xaxis_title="Periodo de Retorno (Años)", yaxis_title="Precipitación Máxima Diaria (mm)",
                xaxis=dict(type="log", tickvals=[1.1, 2, 5, 10, 20, 50, 100, 200, 500],
                           ticktext=["1.1", "2", "5", "10", "20", "50", "100", "200", "500"]),
                hovermode="x unified", legend=dict(yanchor="bottom", y=0.01, xanchor="right", x=0.99),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tabs[4]:
        justificacion("Desagregación temporal de la tormenta de diseño (24 hrs) mediante curvas IDF y el método de Bloques Alternos. Define la serie de tiempo para el modelo lluvia-escorrentía HEC-HMS.")
        if ajuste is None:
            st.error("No hay ajuste probabilístico disponible para construir la tormenta de diseño.")
        else:
            dists = list(ajuste["cuantiles"].keys())
            c1, c2, c3, c4 = st.columns(4)
            dist_sel = c1.selectbox("Modelo Probabilístico:", dists, index=dists.index(ajuste["mejor"]))
            t_sel = c2.selectbox("Periodo de Retorno (Años):", [50, 100, 500])
            dt_sel = c3.selectbox("Intervalo de Tiempo Δt (min):", [5, 10, 15, 30])
            coef_b = c4.number_input("Coef. Desagregación (b):", min_value=0.1, max_value=0.5, value=0.33, step=0.01)

            p24 = ajuste["cuantiles"][dist_sel][t_sel]
            st.info(f"Precipitación Base ($P_{{24}}$): **{p24:.2f} mm** (Distribución {dist_sel}, T={t_sel} años). Coeficiente $b={coef_b}$.")

            duraciones = np.linspace(0.25, 24, 100)
            grid = dict(showgrid=True, gridcolor="rgba(128,128,128,0.4)",
                        minor=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)"))
            fig = go.Figure()
            for t_plot in [50, 100, 500]:
                p = ajuste["cuantiles"][dist_sel][t_plot]
                fig.add_trace(go.Scatter(x=duraciones, y=p * (duraciones / 24.0) ** coef_b / duraciones,
                                         mode="lines", name=f"T = {t_plot} años"))
            fig.update_layout(
                title=f"Curvas Intensidad-Duración-Frecuencia (IDF) - Modelo {dist_sel}",
                xaxis_title="Duración (Horas)", yaxis_title="Intensidad (mm/h)", hovermode="x unified",
                xaxis=dict(type="log", tickvals=[0.25, 0.5, 1, 2, 4, 6, 8, 12, 24],
                           ticktext=["0.25", "0.5", "1", "2", "4", "6", "8", "12", "24"], **grid),
                yaxis=dict(type="log", **grid),
            )
            st.plotly_chart(fig, use_container_width=True)

            tiempos, hieto = hietograma_bloques_alternos(p24, dt_sel, 24, coef_b)
            fig = go.Figure(data=[go.Bar(x=tiempos / 60.0, y=hieto, marker_color="#1f77b4")])
            fig.update_layout(title=f"Hietograma de Diseño - Bloques Alternos (T={t_sel} años, Δt={dt_sel} min)",
                              xaxis_title="Tiempo (Horas)", yaxis_title=f"Precipitación cada {dt_sel} min (mm)",
                              bargap=0, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Datos para Time-Series en HEC-HMS")
            df_hec = pd.DataFrame({"Tiempo Acumulado (minutos)": tiempos,
                                   "Precipitación Incremental (mm)": np.round(hieto, 3)})
            st.caption(f"Verificación: suma del hietograma = {hieto.sum():.2f} mm (P24 = {p24:.2f} mm).")
            st.dataframe(df_hec, use_container_width=True)
            st.download_button("Descargar hietograma (CSV)", a_csv(df_hec),
                               f"hietograma_T{t_sel}_dt{dt_sel}_{estacion}.csv", "text/csv")


# ==========================================
# MÓDULO 2: PARÁMETROS DE CUENCA (HEC-HMS)
# ==========================================
def validar_tabla_cn(df_cn):
    """Devuelve lista de errores de la tabla de coberturas."""
    errores = []
    if df_cn[["CN_Teórico", "%_Área"]].isna().any().any():
        errores.append("Hay celdas vacías en CN o % de área.")
    cn = pd.to_numeric(df_cn["CN_Teórico"], errors="coerce")
    area = pd.to_numeric(df_cn["%_Área"], errors="coerce")
    if ((cn < 30) | (cn > 100)).any():
        errores.append("Los valores de CN deben estar entre 30 y 100.")
    if (area < 0).any():
        errores.append("Los porcentajes de área no pueden ser negativos.")
    if abs(area.sum() - 100.0) > 0.1:
        errores.append(f"La suma de las áreas debe ser 100%. Suma actual: {area.sum():.1f}%")
    return errores


def modulo_cuenca():
    st.title("Parametrización Hidrológica de Cuenca (Inputs HEC-HMS)")
    st.caption("Cálculo de variables geomorfológicas y coeficientes de escorrentía para simulación hidrodinámica.")

    col1, col2 = st.columns(2)

    with col1:
        st.header("1. Morfometría y Tiempo de Concentración")
        st.markdown("Ingrese los parámetros extraídos desde el DEM.")
        area_km2 = st.number_input("Área de la Cuenca ($A$ en $km^2$):", min_value=0.1, value=15.5, step=0.1)
        longitud_km = st.number_input("Longitud del Cauce Principal ($L$ en $km$):", min_value=0.1, value=8.2, step=0.1)

        modo = st.radio("Método de Ingreso de Pendiente:", ["Pendiente Media (m/m)", "Desnivel Topográfico (m)"])
        if modo == "Pendiente Media (m/m)":
            pendiente = st.number_input("Pendiente Media del Cauce ($S$ en $m/m$):", min_value=0.001, value=0.045,
                                        step=0.001, format="%.3f")
            desnivel_m = pendiente * longitud_km * 1000
        else:
            desnivel_m = st.number_input("Desnivel Topográfico del Cauce ($H_{max} - H_{min}$ en $m$):",
                                         min_value=1.0, value=369.0, step=1.0)
            pendiente = desnivel_m / (longitud_km * 1000)

        if pendiente > 0.5:
            st.warning(f"Pendiente media de {pendiente:.3f} m/m (> 50%). Revise que L y el desnivel estén en las unidades correctas.")

        tc_kirpich = 0.0663 * longitud_km ** 0.77 / pendiente ** 0.385
        tc_california = (0.87 * longitud_km ** 3 / desnivel_m) ** 0.385
        tc_giandotti = (4 * np.sqrt(area_km2) + 1.5 * longitud_km) / (0.8 * np.sqrt(desnivel_m))

        st.markdown("### Resultados de Tiempo de Concentración ($t_c$)")
        st.info(f"**Fórmula de Kirpich:** {tc_kirpich:.2f} horas (Recomendado laderas fuertes)")
        st.info(f"**Fórmula de California:** {tc_california:.2f} horas")
        st.info(f"**Fórmula de Giandotti:** {tc_giandotti:.2f} horas")

        tcs = np.array([tc_kirpich, tc_california, tc_giandotti])
        if tcs.max() / tcs.min() > 3:
            st.warning("Las fórmulas difieren en más de 3 veces. Justifique el tc adoptado según el tipo de cuenca.")

        tc_adoptado = st.number_input("Tiempo de Concentración Adoptado ($t_c$ en horas):", min_value=0.1,
                                      value=float(round(tc_kirpich, 2)), step=0.1)
        t_lag = 0.6 * tc_adoptado

    with col2:
        st.header("2. Determinación del Número de Curva ($CN$)")
        st.markdown("Defina la distribución de cobertura de suelo y el Grupo Hidrológico de Suelo (GHS).")
        base = pd.DataFrame({
            "Cobertura/Suelo": ["Bosque Nativo/Plantación", "Matorral (Kia2)", "Suelo Agrícola (Q1)",
                                "Suelo Desnudo / Roca", "Urbano / Caminos"],
            "GHS (SCS)": ["B", "C", "B", "D", "C"],
            "CN_Teórico": [60, 73, 67, 91, 89],
            "%_Área": [10.0, 45.0, 30.0, 10.0, 5.0],
        })
        df_cn = st.data_editor(
            base, num_rows="dynamic", use_container_width=True,
            column_config={
                "CN_Teórico": st.column_config.NumberColumn(min_value=30, max_value=100, step=1),
                "%_Área": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.5),
                "GHS (SCS)": st.column_config.SelectboxColumn(options=["A", "B", "C", "D"]),
            },
        )

        errores = validar_tabla_cn(df_cn)
        cn_ponderado = None
        if errores:
            for err in errores:
                st.error(err)
        else:
            cn_ponderado = float((df_cn["CN_Teórico"] * df_cn["%_Área"] / 100).sum())
            s_ret = 25400 / cn_ponderado - 254
            ia = 0.2 * s_ret
            st.markdown("### Resultados de Retención e Infiltración")
            st.success(f"**Número de Curva Ponderado ($CN_{{AMC\\ II}}$):** {cn_ponderado:.1f}")
            st.info(f"**Retención Máxima Potencial ($S_{{ret}}$):** {s_ret:.1f} mm")
            st.info(f"**Abstracción Inicial ($I_a$):** {ia:.1f} mm")

    st.divider()
    st.header("3. Ficha Resumen para Modelo de Cuenca (HEC-HMS)")
    if cn_ponderado is None:
        st.info("Corrija la tabla de coberturas para generar la ficha.")
        return

    resumen = pd.DataFrame({
        "Parámetro HEC-HMS": ["Area (KM2)", "Initial Abstraction (MM)", "Curve Number", "Impervious (%)", "Lag Time (MIN)"],
        "Valor a Ingresar": [round(area_km2, 2), round(ia, 2), round(cn_ponderado, 1), 0.0, round(t_lag * 60, 1)],
    })
    st.table(resumen)
    st.download_button("Descargar ficha HEC-HMS (CSV)", a_csv(resumen), "ficha_HEC-HMS.csv", "text/csv")
    st.caption("Nota: El porcentaje impermeable se asume integrado en la ponderación del CN mediante las coberturas urbanas. "
               "El Lag Time (0.6·tc) se transformó a minutos según la convención de HEC-HMS.")


# ==========================================
# MÓDULO 3: CAUDALES
# ==========================================
def modulo_caudales(dir_datos):
    encabezado(
        "Análisis de Caudales y Disponibilidad Hídrica Superficial",
        "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas. Procesamiento de estaciones fluviométricas.",
        "Cuantificación del régimen de escurrimiento para la estimación de caudales ecológicos, derechos de aprovechamiento y dimensionamiento de estructuras de control fluvial.",
    )
    fuente = obtener_fuente("caudales", dir_datos)
    df = cargar_o_detener(fuente, "CAUDAL", "Procesando registros fluviométricos...")
    df_radio, col_est = filtrar_por_radio(df, radio_default=40)
    estacion, df_est = mostrar_red_estaciones(
        df_radio, col_est, "1. Red de Monitoreo Fluviométrico", "Ubicación de Puntos de Control Fluviométrico",
        px.colors.sequential.dense, "Seleccione la estación para análisis hidrodinámico:",
    )

    st.header(f"2. Análisis Hidrodinámico: {estacion}")
    tab_fdc, tab_crecidas = st.tabs(["Curva de Duración de Caudales", "Análisis de Crecidas Históricas"])

    with tab_fdc:
        justificacion("La Curva de Duración define la probabilidad de excedencia de caudales. Es el instrumento normativo para el cálculo del Caudal Ecológico.")
        q = df_est["Valor_Registrado"].dropna().sort_values(ascending=False).reset_index(drop=True)
        if q.empty:
            st.warning("La estación no tiene registros de caudal válidos.")
        else:
            excedencia = 100.0 * (q.index + 1) / (len(q) + 1)
            df_fdc = pd.DataFrame({"Probabilidad de Excedencia (%)": excedencia, "Caudal (m3/s)": q})
            n_ceros = int((q <= 0).sum())
            fig = px.line(df_fdc, x="Probabilidad de Excedencia (%)", y="Caudal (m3/s)", log_y=True,
                          title="Curva de Duración de Caudales (Escala Logarítmica)")
            fig.update_traces(line=dict(width=2, color="#1f77b4"))
            fig.update_xaxes(range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)
            if n_ceros:
                st.caption(f"{n_ceros} registros con caudal 0 no se muestran en escala logarítmica.")

            q50 = float(np.percentile(q, 50))   # excedido el 50% del tiempo
            q85 = float(np.percentile(q, 15))   # excedido el 85% del tiempo
            c1, c2 = st.columns(2)
            c1.metric("Caudal Mediano (Q50)", f"{q50:.2f} m³/s", "Disponibilidad al 50% del tiempo", delta_color="off")
            c2.metric("Caudal de Estiaje (Q85)", f"{q85:.2f} m³/s", "Excedido el 85% del tiempo", delta_color="off")

    with tab_crecidas:
        justificacion("Análisis de los caudales máximos diarios anuales (QMA) para modelaciones hidráulicas y cálculo de cota de inundación.")
        qma = df_est.groupby("AÑO")["Valor_Registrado"].max().reset_index()
        fig = px.bar(qma, x="AÑO", y="Valor_Registrado",
                     labels={"AÑO": "Año", "Valor_Registrado": "Caudal Máximo Anual (m³/s)"},
                     color="Valor_Registrado", color_continuous_scale="Reds")
        st.plotly_chart(fig, use_container_width=True)


# ==========================================
# MÓDULO 4: AGUAS SUBTERRÁNEAS
# ==========================================
def modulo_pozos(dir_datos):
    encabezado(
        "Análisis Hidrogeológico: Fluctuación de Niveles Estáticos",
        "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas. Red de pozos de observación hidrogeológica.",
        "Evaluación sistemática de la variación del nivel freático para identificar conos de depresión y cuantificar la recarga del acuífero.",
    )
    fuente = obtener_fuente("pozos", dir_datos)
    df = cargar_o_detener(fuente, "NIVEL", "Procesando perfiles de pozos de observación...")
    df_radio, col_est = filtrar_por_radio(df, radio_default=50)
    pozo, df_est = mostrar_red_estaciones(
        df_radio, col_est, "1. Red de Pozos de Observación DGA", "Ubicación de Puntos de Monitoreo Hidrogeológico",
        px.colors.sequential.Aggrnyl, "Seleccione el pozo para evaluación de niveles:",
    )

    st.header(f"2. Análisis de Comportamiento del Acuífero: {pozo}")
    tab_serie, tab_est = st.tabs(["Evolución Histórica de Niveles", "Amplitud de Fluctuación"])

    with tab_serie:
        justificacion("La inspección temporal del nivel estático evidencia tendencias de abatimiento sostenido o procesos de recuperación.")
        fig = px.line(df_est, x="FECHA_DT", y="Valor_Registrado", markers=True,
                      labels={"FECHA_DT": "Fecha de Medición", "Valor_Registrado": "Profundidad del Nivel Estático (m)"},
                      title="Serie Temporal (Eje Y invertido: profundidad bajo la superficie)")
        fig.update_traces(line=dict(width=2, color="#2ca02c"))
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

    with tab_est:
        justificacion("La dispersión estadística de la profundidad freática provee parámetros geométricos críticos para el diseño de captaciones.")
        fig = px.box(df_est, y="Valor_Registrado", points="all",
                     labels={"Valor_Registrado": "Distribución de Profundidad Histórica (m)"},
                     color_discrete_sequence=["#2ca02c"])
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        nivel_max = df_est["Valor_Registrado"].max()
        nivel_min = df_est["Valor_Registrado"].min()
        c1, c2, c3 = st.columns(3)
        c1.metric("Nivel Somero Máximo", f"{nivel_min:.2f} m", "Punto de mayor recuperación freática", delta_color="off")
        c2.metric("Abatimiento Máximo", f"{nivel_max:.2f} m", "Mayor profundidad registrada", delta_color="off")
        c3.metric("Amplitud Histórica", f"{nivel_max - nivel_min:.2f} m", "Delta de fluctuación total", delta_color="off")


# ==========================================
# MÓDULO 5: CALIDAD GEOQUÍMICA
# ==========================================
def modulo_calidad(dir_datos):
    encabezado(
        "Caracterización Fisicoquímica del Agua",
        "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas. Red de monitoreo de calidad de aguas.",
        "Análisis de las concentraciones iónicas e indicadores fisicoquímicos para la definición de la línea base ambiental.",
    )
    fuente = obtener_fuente("calidad", dir_datos)
    df = cargar_o_detener(fuente, "VALOR", "Indexando base de datos geoquímica multivariable...")
    df_radio, col_est = filtrar_por_radio(df, radio_default=60, radio_max=200, paso=10)
    _, df_est = mostrar_red_estaciones(
        df_radio, col_est, "1. Red de Monitoreo de Calidad Hídrica", "Ubicación de Puntos de Muestreo Geoquímico",
        px.colors.sequential.Plasma, "Seleccione la estación para evaluación analítica:",
    )

    st.header("2. Evaluación de Parámetros Específicos")
    col_param = next((c for c in df_est.columns if "PARAMETRO" in c and "COD" not in c), None)
    if col_param is None:
        st.warning("El archivo no incluye una columna de parámetros químicos (PARAMETRO).")
        return

    parametro = st.selectbox("Seleccione el componente o indicador fisicoquímico a evaluar:",
                             sorted(df_est[col_param].dropna().unique().tolist()))
    df_param = df_est[df_est[col_param] == parametro]
    unidad = df_param["UNIDAD"].iloc[0] if "UNIDAD" in df_param.columns and not df_param.empty else ""

    tab_evo, tab_dist = st.tabs(["Evolución Temporal del Analito", "Distribución de Concentración"])
    with tab_evo:
        justificacion(f"Seguimiento de la evolución temporal del parámetro {parametro} correlacionado con ciclos hidrológicos de dilución o concentración.")
        fig = px.line(df_param, x="FECHA_DT", y="Valor_Registrado", markers=True,
                      labels={"FECHA_DT": "Fecha de Muestreo", "Valor_Registrado": f"Concentración ({unidad})"},
                      title=f"Serie Temporal: {parametro}")
        fig.update_traces(line=dict(width=2, color="#9467bd"))
        st.plotly_chart(fig, use_container_width=True)
    with tab_dist:
        justificacion("La distribución estadística de las concentraciones facilita la identificación de valores atípicos.")
        fig = px.box(df_param, y="Valor_Registrado", points="all",
                     labels={"Valor_Registrado": f"Distribución ({unidad})"},
                     color_discrete_sequence=["#9467bd"], title=f"Rango de Dispersión Histórica: {parametro}")
        st.plotly_chart(fig, use_container_width=True)


# ==========================================
# NAVEGACIÓN PRINCIPAL
# ==========================================
MODULOS = {
    "Precipitaciones": modulo_precipitaciones,
    "Parámetros de Cuenca (HEC-HMS)": None,  # no usa archivos
    "Caudales": modulo_caudales,
    "Aguas Subterráneas": modulo_pozos,
    "Calidad Geoquímica": modulo_calidad,
}


def main():
    st.sidebar.title("Módulos de Análisis")
    modulo = st.sidebar.radio("Seleccione la disciplina a evaluar:", list(MODULOS.keys()))

    dir_datos = st.sidebar.text_input("Carpeta de datos:", value=DIR_DATOS_DEFAULT,
                                      help="Carpeta con los archivos DGA y AGROMET. También se puede fijar con la variable de entorno DGA_DATA_DIR.")
    dir_datos = dir_datos.strip().strip('"')
    st.sidebar.divider()

    if modulo == "Parámetros de Cuenca (HEC-HMS)":
        modulo_cuenca()
    else:
        MODULOS[modulo](dir_datos)


if __name__ == "__main__":
    main()