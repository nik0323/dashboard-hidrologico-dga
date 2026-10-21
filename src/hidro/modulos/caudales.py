"""Módulo 3: Caudales (curva de duración y caudales máximos anuales)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core import series
from hidro.core.caudales import curva_duracion
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui import datos, red
from hidro.ui.componentes import encabezado, grafico, justificacion


@registrar
class Caudales(Modulo):
    clave = "caudales"
    nombre = "Caudales"
    orden = 30
    archivos_requeridos = ("caudales",)

    def render(self, ctx: Contexto) -> None:
        encabezado(
            "Análisis de Caudales y Disponibilidad Hídrica Superficial",
            "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas. Procesamiento de estaciones fluviométricas.",
            "Cuantificación del régimen de escurrimiento para la estimación de caudales ecológicos, derechos de aprovechamiento y dimensionamiento de estructuras de control fluvial.",
        )
        fuente = datos.obtener_fuente(ctx, "caudales")
        df = datos.cargar_o_detener(fuente, "CAUDAL", "Procesando registros fluviométricos...")
        df_radio, col_est = red.filtro_radio(ctx, df, "caudales")
        estacion, df_est = red.mapa_y_selector(
            ctx, df_radio, col_est, "1. Red de Monitoreo Fluviométrico", "Ubicación de Puntos de Control Fluviométrico",
            px.colors.sequential.dense, "Seleccione la estación para análisis hidrodinámico:",
        )

        st.header(f"2. Análisis Hidrodinámico: {estacion}")
        tab_fdc, tab_crecidas = st.tabs(["Curva de Duración de Caudales", "Análisis de Crecidas Históricas"])

        with tab_fdc:
            justificacion("La Curva de Duración define la probabilidad de excedencia de caudales. Es el instrumento normativo para el cálculo del Caudal Ecológico.")
            if df_est[c.VALOR].dropna().empty:
                st.warning("La estación no tiene registros de caudal válidos.")
            else:
                fdc = curva_duracion(df_est[c.VALOR])
                fig = px.line(fdc.tabla, x="Probabilidad de Excedencia (%)", y="Caudal (m3/s)", log_y=True,
                              title="Curva de Duración de Caudales (Escala Logarítmica)")
                fig.update_traces(line=dict(width=2, color="#1f77b4"))
                fig.update_xaxes(range=[0, 100])
                grafico(fig)
                if fdc.n_ceros:
                    st.caption(f"{fdc.n_ceros} registros con caudal 0 no se muestran en escala logarítmica.")

                c1, c2 = st.columns(2)
                c1.metric("Caudal Mediano (Q50)", f"{fdc.q50:.2f} m³/s", "Disponibilidad al 50% del tiempo", delta_color="off")
                c2.metric("Caudal de Estiaje (Q85)", f"{fdc.q85:.2f} m³/s", "Excedido el 85% del tiempo", delta_color="off")

        with tab_crecidas:
            justificacion("Análisis de los caudales máximos diarios anuales (QMA) para modelaciones hidráulicas y cálculo de cota de inundación.")
            cobertura_min = ctx.settings.cobertura_min_maximos
            incompletos = series.anios_incompletos(df_est, cobertura_min)
            if incompletos:
                st.caption(f"Años excluidos por cobertura < {cobertura_min:.0%}: " + ", ".join(map(str, incompletos)))
            qma = series.maximos_anuales(df_est, cobertura_min)
            if qma.empty:
                st.warning(f"La estación no tiene años con cobertura >= {cobertura_min:.0%}: no hay QMA confiables.")
                return
            fig = px.bar(qma, x=c.ANIO, y=c.VALOR,
                         labels={c.ANIO: "Año", c.VALOR: "Caudal Máximo Anual (m³/s)"},
                         color=c.VALOR, color_continuous_scale="Reds")
            grafico(fig)
