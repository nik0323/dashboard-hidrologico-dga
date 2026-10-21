"""Módulo 4: Aguas subterráneas (fluctuación de niveles estáticos)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core.series import rango_niveles
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui import datos, red
from hidro.ui.componentes import encabezado, grafico, justificacion


@registrar
class Pozos(Modulo):
    clave = "pozos"
    nombre = "Aguas Subterráneas"
    orden = 40
    archivos_requeridos = ("pozos",)

    def render(self, ctx: Contexto) -> None:
        encabezado(
            "Análisis Hidrogeológico: Fluctuación de Niveles Estáticos",
            "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas. Red de pozos de observación hidrogeológica.",
            "Evaluación sistemática de la variación del nivel freático para identificar conos de depresión y cuantificar la recarga del acuífero.",
        )
        fuente = datos.obtener_fuente(ctx, "pozos")
        df = datos.cargar_o_detener(fuente, "NIVEL", "Procesando perfiles de pozos de observación...")
        df_radio, col_est = red.filtro_radio(ctx, df, "pozos")
        pozo, df_est = red.mapa_y_selector(
            ctx, df_radio, col_est, "1. Red de Pozos de Observación DGA", "Ubicación de Puntos de Monitoreo Hidrogeológico",
            px.colors.sequential.Aggrnyl, "Seleccione el pozo para evaluación de niveles:",
        )

        st.header(f"2. Análisis de Comportamiento del Acuífero: {pozo}")
        tab_serie, tab_est = st.tabs(["Evolución Histórica de Niveles", "Amplitud de Fluctuación"])

        with tab_serie:
            justificacion("La inspección temporal del nivel estático evidencia tendencias de abatimiento sostenido o procesos de recuperación.")
            fig = px.line(df_est, x=c.FECHA, y=c.VALOR, markers=True,
                          labels={c.FECHA: "Fecha de Medición", c.VALOR: "Profundidad del Nivel Estático (m)"},
                          title="Serie Temporal (Eje Y invertido: profundidad bajo la superficie)")
            fig.update_traces(line=dict(width=2, color="#2ca02c"))
            fig.update_yaxes(autorange="reversed")
            grafico(fig)

        with tab_est:
            justificacion("La dispersión estadística de la profundidad freática provee parámetros geométricos críticos para el diseño de captaciones.")
            fig = px.box(df_est, y=c.VALOR, points="all",
                         labels={c.VALOR: "Distribución de Profundidad Histórica (m)"},
                         color_discrete_sequence=["#2ca02c"])
            fig.update_yaxes(autorange="reversed")
            grafico(fig)

            r = rango_niveles(df_est)
            c1, c2, c3 = st.columns(3)
            c1.metric("Nivel Somero Máximo", f"{r.nivel_min:.2f} m", "Punto de mayor recuperación freática", delta_color="off")
            c2.metric("Abatimiento Máximo", f"{r.nivel_max:.2f} m", "Mayor profundidad registrada", delta_color="off")
            c3.metric("Amplitud Histórica", f"{r.amplitud:.2f} m", "Delta de fluctuación total", delta_color="off")
