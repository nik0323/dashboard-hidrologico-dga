"""Módulo 5: Calidad geoquímica (evolución y distribución por parámetro)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core.calidad import (COL_CATEGORIA, CENSURADAS, clasificar_marca, filtrar_parametro,
                                parametros_disponibles, resumen_marcas)
from hidro.io.normalizacion import columna_parametro
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui import datos, red
from hidro.ui.componentes import encabezado, grafico, justificacion, tabla


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
        df_param = df_param.assign(**{COL_CATEGORIA: clasificar_marca(df_param)}).sort_values(c.FECHA)
        self._aviso_marcas(df_param)

        etiquetas = {c.FECHA: "Fecha de Muestreo", c.VALOR: f"Concentración ({unidad})", COL_CATEGORIA: "Marca DGA"}
        tab_evo, tab_dist = st.tabs(["Evolución Temporal del Analito", "Distribución de Concentración"])
        with tab_evo:
            justificacion(f"Seguimiento de la evolución temporal del parámetro {parametro} correlacionado con ciclos hidrológicos de dilución o concentración.")
            medidos = df_param[~df_param[COL_CATEGORIA].isin(CENSURADAS)]
            fig = px.scatter(df_param, x=c.FECHA, y=c.VALOR, color=COL_CATEGORIA, symbol=COL_CATEGORIA,
                             labels=etiquetas, title=f"Serie Temporal: {parametro}")
            fig.add_trace(go.Scatter(x=medidos[c.FECHA], y=medidos[c.VALOR], mode="lines", name="Serie (sin censurados)",
                                     line=dict(width=2, color="#9467bd")))
            grafico(fig)
        with tab_dist:
            justificacion("La distribución estadística de las concentraciones facilita la identificación de valores atípicos. "
                          "Cada marca DGA se muestra por separado: los valores censurados no son concentraciones medidas.")
            fig = px.box(df_param, x=COL_CATEGORIA, y=c.VALOR, color=COL_CATEGORIA, points="all",
                         labels={**etiquetas, c.VALOR: f"Distribución ({unidad})"},
                         title=f"Rango de Dispersión Histórica: {parametro}")
            grafico(fig)

    @staticmethod
    def _aviso_marcas(df_param: pd.DataFrame) -> None:
        """Hallazgo #11: informa cuántas muestras son censuradas según la columna CALIDAD de la DGA."""
        resumen = resumen_marcas(df_param[COL_CATEGORIA])
        n_cens = int(df_param[COL_CATEGORIA].isin(CENSURADAS).sum())
        if n_cens:
            st.warning(f"{n_cens} de {len(df_param)} muestras ({n_cens / len(df_param):.1%}) son censuradas: "
                       "con marca '<' el valor registrado es el límite de detección y con '>' el límite superior del "
                       "rango, no concentraciones medidas. Se muestran por separado y no forman parte de la línea de la serie.")
        with st.expander("Muestras por marca de calidad DGA"):
            tabla(resumen, hide_index=True)
