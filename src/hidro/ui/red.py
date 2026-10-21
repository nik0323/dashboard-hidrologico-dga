"""Red de estaciones: filtro por radio, mapa y selector."""

from __future__ import annotations

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core.estaciones import filtrar_por_radio, resumen_estaciones, serie_estacion
from hidro.io.normalizacion import columna_estacion
from hidro.ui.componentes import grafico

logger = logging.getLogger(__name__)


def filtro_radio(ctx: Contexto, df: pd.DataFrame, clave_radio: str) -> tuple[pd.DataFrame, str]:
    """Slider lateral de radio [km] y filtro espacial. Devuelve (df dentro del radio, columna de estación)."""
    if c.LAT not in df.columns:
        st.error("El archivo no contiene coordenadas (LATITUD / LONGITUD).")
        st.stop()

    pc = ctx.settings.punto_control
    radio = ctx.settings.radio(clave_radio)
    col_estacion = columna_estacion(df.columns)

    st.sidebar.header("Filtros Espaciales")
    radio_km = st.sidebar.slider("Radio de Búsqueda (km):", min_value=radio.min, max_value=radio.max,
                                 value=radio.defecto, step=radio.paso, key=ctx.key("radio_km"))
    resultado = filtrar_por_radio(df, pc.lat, pc.lon, radio_km, col_estacion)

    if resultado.sin_coordenadas:
        st.sidebar.caption(f"⚠️ {len(resultado.sin_coordenadas)} estación(es) con coordenadas inválidas fueron excluidas.")
        logger.warning("Estaciones sin coordenadas válidas: %s", resultado.sin_coordenadas)

    if resultado.df_radio.empty:
        st.warning(f"No hay estaciones a menos de {radio_km} km de {pc.nombre}. Aumenta el radio de búsqueda.")
        st.stop()
    return resultado.df_radio, col_estacion


def mapa_y_selector(ctx: Contexto, df_radio: pd.DataFrame, col_estacion: str, titulo_seccion: str,
                    titulo_mapa: str, escala: list[str], etiqueta_selector: str) -> tuple[str, pd.DataFrame]:
    """Mapa de estaciones coloreado por distancia y selector. Devuelve (estación, serie ordenada por fecha)."""
    st.header(titulo_seccion)
    pc = ctx.settings.punto_control

    info = resumen_estaciones(df_radio, col_estacion)
    hover = [col for col in (c.DISTANCIA, "ALTITUD") if col in info.columns]

    fig = px.scatter_map(
        info, lat=c.LAT, lon=c.LON, hover_name=col_estacion, hover_data=hover,
        color=c.DISTANCIA, color_continuous_scale=escala, zoom=9, height=400, title=titulo_mapa,
        labels={c.DISTANCIA: f"Distancia a {pc.nombre} (km)"},
    )
    fig.update_traces(marker=dict(size=12))
    fig.add_scattermap(lat=[pc.lat], lon=[pc.lon], mode="markers",
                       marker=dict(size=14, color="red"), name=f"Punto de Control ({pc.nombre})")
    fig.update_layout(map_style="open-street-map", margin={"r": 0, "t": 40, "l": 0, "b": 0})
    grafico(fig)

    estacion = st.selectbox(etiqueta_selector, info[col_estacion].tolist(), key=ctx.key("estacion"))
    return estacion, serie_estacion(df_radio, col_estacion, estacion)
