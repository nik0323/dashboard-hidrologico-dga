"""Módulo 4: Aguas subterráneas (fluctuación de niveles estáticos)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core.pozos import (COL_CONDICION, DINAMICO, EMBANCADO, ESTATICO, SECO, SIN_ACCESO, clasificar_condicion,
                              niveles_estaticos, resumen_condiciones)
from hidro.core.series import rango_niveles
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui import datos, red
from hidro.ui.componentes import encabezado, grafico, justificacion, tabla

MAX_LINEAS_SECO = 60   # sobre este número de eventos "Seco" no se dibujan líneas verticales


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
        # Se conservan mediciones sin nivel (Seco / Sin acceso) para informarlas (hallazgo #12)
        df = datos.cargar_o_detener(fuente, "NIVEL", "Procesando perfiles de pozos de observación...",
                                    conservar_sin_valor=True)
        df_radio, col_est = red.filtro_radio(ctx, df, "pozos")
        pozo, df_est = red.mapa_y_selector(
            ctx, df_radio, col_est, "1. Red de Pozos de Observación DGA", "Ubicación de Puntos de Monitoreo Hidrogeológico",
            px.colors.sequential.Aggrnyl, "Seleccione el pozo para evaluación de niveles:",
        )
        df_est = df_est.assign(**{COL_CONDICION: clasificar_condicion(df_est)})
        estaticos = niveles_estaticos(df_est)

        st.header(f"2. Análisis de Comportamiento del Acuífero: {pozo}")
        self._avisos_condiciones(df_est)
        if estaticos.empty:
            st.warning("El pozo no tiene mediciones de nivel estático válidas.")
            return

        tab_serie, tab_est = st.tabs(["Evolución Histórica de Niveles", "Amplitud de Fluctuación"])
        with tab_serie:
            self._serie(ctx, df_est, estaticos)
        with tab_est:
            justificacion("La dispersión estadística de la profundidad freática provee parámetros geométricos críticos para el diseño de captaciones.")
            fig = px.box(estaticos, y=c.VALOR, points="all",
                         labels={c.VALOR: "Distribución de Profundidad Histórica (m)"},
                         color_discrete_sequence=["#2ca02c"])
            fig.update_yaxes(autorange="reversed")
            grafico(fig)

            r = rango_niveles(estaticos)
            c1, c2, c3 = st.columns(3)
            c1.metric("Nivel Somero Máximo", f"{r.nivel_min:.2f} m", "Punto de mayor recuperación freática", delta_color="off")
            c2.metric("Abatimiento Máximo", f"{r.nivel_max:.2f} m", "Mayor profundidad registrada", delta_color="off")
            c3.metric("Amplitud Histórica", f"{r.amplitud:.2f} m", "Delta de fluctuación total", delta_color="off")
            st.caption("Calculado solo con niveles estáticos (sin observación o surgentes). "
                       "Profundidades negativas = nivel sobre la superficie (pozo surgente).")

    @staticmethod
    def _avisos_condiciones(df_est: pd.DataFrame) -> None:
        """Hallazgo #12: informa mediciones excluidas del nivel estático y eventos sin nivel."""
        cond = df_est[COL_CONDICION]
        n = {k: int((cond == k).sum()) for k in (DINAMICO, EMBANCADO, SECO, SIN_ACCESO)}
        excluidas = [f"{n[DINAMICO]} dinámicas (con bombeo)" if n[DINAMICO] else "",
                     f"{n[EMBANCADO]} con pozo embancado" if n[EMBANCADO] else ""]
        excluidas = [e for e in excluidas if e]
        if excluidas:
            st.warning("Mediciones excluidas del nivel estático: " + " y ".join(excluidas) + ".")
        if n[SECO]:
            anios = sorted(df_est.loc[cond == SECO, c.FECHA].dt.year.unique().tolist())
            st.info(f"{n[SECO]} visitas con el pozo **seco** (nivel bajo el fondo del pozo, sin profundidad medida), "
                    f"en los años: {', '.join(map(str, anios))}.")
        ceros = int(((cond == ESTATICO) & (df_est[c.VALOR] == 0)).sum())
        if ceros:
            st.caption(f"{ceros} mediciones estáticas sin observación registran nivel = 0 m; "
                       "verifique si corresponden a nivel en superficie o a un valor faltante.")
        with st.expander("Mediciones por condición (columna OBSERVACION de la DGA)"):
            tabla(resumen_condiciones(df_est), hide_index=True)

    @staticmethod
    def _serie(ctx: Contexto, df_est: pd.DataFrame, estaticos: pd.DataFrame) -> None:
        justificacion("La inspección temporal del nivel estático evidencia tendencias de abatimiento sostenido o procesos de recuperación.")
        estaticos = estaticos.sort_values(c.FECHA)
        fig = go.Figure(go.Scatter(x=estaticos[c.FECHA], y=estaticos[c.VALOR], mode="lines+markers",
                                   name="Nivel estático", line=dict(width=2, color="#2ca02c")))
        dinamicos = df_est[(df_est[COL_CONDICION] == DINAMICO) & df_est[c.VALOR].notna()]
        if not dinamicos.empty and st.checkbox("Mostrar niveles dinámicos (con bombeo)", value=False,
                                               key=ctx.key("mostrar_dinamicos")):
            fig.add_trace(go.Scatter(x=dinamicos[c.FECHA], y=dinamicos[c.VALOR], mode="markers",
                                     name="Nivel dinámico (excluido)", marker=dict(symbol="x", color="#ff7f0e")))
        secos = df_est.loc[df_est[COL_CONDICION] == SECO, c.FECHA]
        if 0 < len(secos) <= MAX_LINEAS_SECO:
            for fecha in secos:
                fig.add_vline(x=fecha, line_dash="dot", line_color="#d62728", opacity=0.4)
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name="Pozo seco (sin nivel)",
                                     line=dict(dash="dot", color="#d62728")))
        fig.update_layout(title="Serie Temporal (Eje Y invertido: profundidad bajo la superficie)",
                          xaxis_title="Fecha de Medición", yaxis_title="Profundidad del Nivel Estático (m)")
        fig.update_yaxes(autorange="reversed")
        grafico(fig)
