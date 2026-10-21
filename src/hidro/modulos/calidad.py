"""Módulo 5: Calidad geoquímica (evolución y distribución por parámetro)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core.calidad import filtrar_parametro, parametros_disponibles
from hidro.io.normalizacion import columna_parametro
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui import datos, red
from hidro.ui.componentes import encabezado, grafico, justificacion


@registrar
class Calidad(Modulo):
    clave = "calidad"
    nombre = "Calidad Geoquímica"
    orden = 50
    archivos_requeridos = ("calidad",)

    def render(self, ctx: Contexto) -> None:
        encabezado(
            "Caracterización Fisicoquímica del Agua",
            "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas. Red de monitoreo de calidad de aguas.",
            "Análisis de las concentraciones iónicas e indicadores fisicoquímicos para la definición de la línea base ambiental.",
        )
        fuente = datos.obtener_fuente(ctx, "calidad")
        df = datos.cargar_o_detener(fuente, "VALOR", "Indexando base de datos geoquímica multivariable...")
        df_radio, col_est = red.filtro_radio(ctx, df, "calidad")
        _, df_est = red.mapa_y_selector(
            ctx, df_radio, col_est, "1. Red de Monitoreo de Calidad Hídrica", "Ubicación de Puntos de Muestreo Geoquímico",
            px.colors.sequential.Plasma, "Seleccione la estación para evaluación analítica:",
        )

        st.header("2. Evaluación de Parámetros Específicos")
        col_param = columna_parametro(df_est.columns)
        if col_param is None:
            st.warning("El archivo no incluye una columna de parámetros químicos (PARAMETRO).")
            return

        parametro = st.selectbox("Seleccione el componente o indicador fisicoquímico a evaluar:",
                                 parametros_disponibles(df_est, col_param), key=ctx.key("parametro"))
        df_param, unidad = filtrar_parametro(df_est, col_param, parametro)

        tab_evo, tab_dist = st.tabs(["Evolución Temporal del Analito", "Distribución de Concentración"])
        with tab_evo:
            justificacion(f"Seguimiento de la evolución temporal del parámetro {parametro} correlacionado con ciclos hidrológicos de dilución o concentración.")
            fig = px.line(df_param, x=c.FECHA, y=c.VALOR, markers=True,
                          labels={c.FECHA: "Fecha de Muestreo", c.VALOR: f"Concentración ({unidad})"},
                          title=f"Serie Temporal: {parametro}")
            fig.update_traces(line=dict(width=2, color="#9467bd"))
            grafico(fig)
        with tab_dist:
            justificacion("La distribución estadística de las concentraciones facilita la identificación de valores atípicos.")
            fig = px.box(df_param, y=c.VALOR, points="all",
                         labels={c.VALOR: f"Distribución ({unidad})"},
                         color_discrete_sequence=["#9467bd"], title=f"Rango de Dispersión Histórica: {parametro}")
            grafico(fig)
