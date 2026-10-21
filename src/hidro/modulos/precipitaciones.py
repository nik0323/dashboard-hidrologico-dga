"""Módulo 1: Precipitaciones (régimen, PMA, ajuste probabilístico, IDF y hietograma HEC-HMS)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core import frecuencia, series, tormentas
from hidro.io.imputacion import anios_bajo_cobertura, imputar_con_agromet, resumen_imputacion, serie_sin_imputar
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui import cache, datos, red
from hidro.ui.componentes import descarga_csv, encabezado, grafico, justificacion, tabla

ESTILOS_DIST = {"Gumbel": ("blue", "solid"), "Log-Pearson III": ("red", "dash"), "Log-Normal": ("green", "dot")}


@registrar
class Precipitaciones(Modulo):
    clave = "precipitaciones"
    nombre = "Precipitaciones"
    orden = 10
    archivos_requeridos = ("precipitaciones",)

    def render(self, ctx: Contexto) -> None:
        s = ctx.settings
        encabezado(
            "Análisis Espacial de Precipitaciones DGA",
            "Fuente: Dirección General de Aguas (DGA) - Ministerio de Obras Públicas (mapas2.mop.gob.cl).",
            "Evaluación de parámetros pluviométricos para el diseño hidrológico de obras civiles y mitigación "
            f"de amenazas aluvionales en el sector {s.punto_control.nombre}.",
        )

        fuente = datos.obtener_fuente(ctx, "precipitaciones")
        df = datos.cargar_o_detener(fuente, "PRECIPIT", "Procesando series de tiempo pluviométricas...")
        df_radio, col_est = red.filtro_radio(ctx, df, "precipitaciones")
        estacion, df_est = red.mapa_y_selector(
            ctx, df_radio, col_est, "1. Red de Monitoreo Pluviométrico",
            "Distribución de Estaciones Pluviométricas (Gradiente de proximidad)",
            px.colors.sequential.Teal, "Seleccione la estación para extracción de datos:",
        )

        # --- Imputación AGROMET (opcional y trazable) ---
        if ctx.dir_datos.is_dir():
            df_agro, avisos_agro = cache.cargar_agromet(str(ctx.dir_datos), s.patron_agromet, s.qa_max_precip_horaria_mm)
        else:
            df_agro, avisos_agro = pd.DataFrame(), []
        cobertura_min = s.cobertura_min_anual
        usar_agromet = sin_restricciones = False
        if not df_agro.empty:
            usar_agromet = st.sidebar.checkbox(
                "Rellenar vacíos con AGROMET", value=True, key=ctx.key("usar_agromet"),
                help=f"Completa días sin registro DGA con la estación auxiliar AGROMET, solo dentro del periodo "
                     f"de registro y en años con cobertura DGA >= {cobertura_min:.0%}.")
            if usar_agromet:
                sin_restricciones = st.sidebar.checkbox(
                    "Imputación sin restricciones (dashboard original)", value=False, key=ctx.key("agromet_original"),
                    help="Rellena también fuera del periodo DGA y años sin registro DGA. Solo para comparar: "
                         "esos años quedan con PMA de otra estación.")
        anios_excluidos: list[int] = []
        if usar_agromet and sin_restricciones:
            df_est = imputar_con_agromet(df_est, df_agro, extender=True, cobertura_min_anual=0.0)
        elif usar_agromet:
            anios_excluidos = anios_bajo_cobertura(df_est, df_agro, cobertura_min)
            df_est = imputar_con_agromet(df_est, df_agro, cobertura_min_anual=cobertura_min)
        else:
            df_est = serie_sin_imputar(df_est)

        st.header(f"2. Análisis Hidrometeorológico: {estacion}")
        if sin_restricciones:
            st.warning("Imputación sin restricciones: la serie incluye años completos tomados de AGROMET "
                       "(fuera del periodo DGA o sin registro DGA), que modifican n, momentos y cuantiles de diseño.")
        if usar_agromet:
            self._panel_imputacion(df_est, avisos_agro, anios_excluidos, cobertura_min)

        pma_anual = series.maximos_anuales(df_est, s.cobertura_min_maximos)
        incompletos = series.anios_incompletos(df_est, s.cobertura_min_maximos)
        aviso_incompletos = (f"Años excluidos de la serie de PMA por cobertura < {s.cobertura_min_maximos:.0%}: "
                             + ", ".join(map(str, incompletos))) if incompletos else ""
        ajuste = frecuencia.ajustar_distribuciones(pma_anual[c.VALOR], s.t_objetivo, s.n_min_ajuste)

        tabs = st.tabs(["Régimen Estacional", "Acumulación Interanual", "Análisis de Extremos (PMA)",
                        "Ajuste Probabilístico", "Hietogramas de Diseño (HEC-HMS)"])
        with tabs[0]:
            self._regimen_estacional(df_est)
        with tabs[1]:
            self._acumulacion_anual(df_est)
        with tabs[2]:
            self._extremos(pma_anual, aviso_incompletos)
        with tabs[3]:
            self._ajuste(ctx, ajuste, estacion, aviso_incompletos)
        with tabs[4]:
            self._tormenta(ctx, ajuste, estacion)

    @staticmethod
    def _panel_imputacion(df_est: pd.DataFrame, avisos: list[str], anios_excluidos: list[int],
                          cobertura_min: float) -> None:
        r = resumen_imputacion(df_est)
        with st.expander(f"Imputación AGROMET: {r.n_imputados:,} días rellenados ({r.fraccion:.1%} de la serie)",
                         expanded=bool(r.anios_pma_imputada)):
            if anios_excluidos:
                st.info(f"Años no imputados por cobertura DGA < {cobertura_min:.0%}: "
                        + ", ".join(map(str, anios_excluidos)))
            if r.anios_pma_imputada:
                st.warning("En estos años la PMA proviene de un día imputado, lo que afecta los cuantiles de diseño: "
                           + ", ".join(map(str, r.anios_pma_imputada)))
            else:
                st.write("Ninguna PMA anual proviene de un día imputado.")
            for aviso in avisos:
                st.caption(aviso)

    @staticmethod
    def _regimen_estacional(df_est: pd.DataFrame) -> None:
        justificacion("Determinación de la concentración estacional de las precipitaciones para establecer condiciones de humedad antecedente.")
        fig = px.box(series.totales_mensuales(df_est), x=c.MES_NOMBRE, y=c.VALOR,
                     category_orders={c.MES_NOMBRE: c.ORDEN_MESES},
                     labels={c.MES_NOMBRE: "Mes", c.VALOR: "Precipitación Total Mensual (mm)"},
                     color_discrete_sequence=["#2E5B82"], points="all")
        grafico(fig)

    @staticmethod
    def _acumulacion_anual(df_est: pd.DataFrame) -> None:
        justificacion("Evaluación del comportamiento acumulativo para la identificación de déficit hídrico prolongado.")
        fig = px.bar(series.totales_anuales(df_est), x=c.ANIO, y=c.VALOR,
                     labels={c.ANIO: "Año", c.VALOR: "Precipitación Anual (mm)"},
                     color=c.VALOR, color_continuous_scale="Blues")
        grafico(fig)

    @staticmethod
    def _extremos(pma_anual: pd.DataFrame, aviso_incompletos: str) -> None:
        justificacion("Cuantificación de la Precipitación Máxima Diaria Anual (PMA). Parámetro normativo para hietogramas de diseño.")
        if aviso_incompletos:
            st.caption(aviso_incompletos)
        e = series.estadisticos(pma_anual)
        c1, c2, c3 = st.columns(3)
        c1.metric("Media PMA (μ)", f"{e.media:.1f} mm")
        c2.metric("Desv. Estándar (σ)", f"{e.desv:.1f} mm")
        c3.metric("Coef. de Variación (CV)", f"{e.cv:.1f} %")
        st.divider()
        fig = px.line(pma_anual, x=c.ANIO, y=c.VALOR, markers=True,
                      labels={c.ANIO: "Año", c.VALOR: "PMA 24h (mm/día)"},
                      color_discrete_sequence=["#d62728"])
        grafico(fig)

    @staticmethod
    def _ajuste(ctx: Contexto, ajuste: frecuencia.ResultadoAjuste | None, estacion: str, aviso_incompletos: str) -> None:
        s = ctx.settings
        justificacion("Modelación probabilística de la serie empírica de extremos para proyectar las Precipitaciones Máximas Diarias asociadas a los periodos de retorno (T).")
        if aviso_incompletos:
            st.caption(aviso_incompletos)
        if ajuste is None:
            st.error(f"Se requieren al menos {s.n_min_ajuste} años completos (cobertura >= "
                     f"{s.cobertura_min_maximos:.0%}) con PMA > 0 para ajustar distribuciones.")
            return
        if ajuste.n < s.n_recomendado:
            st.warning(f"La serie tiene {ajuste.n} años de registro (< {s.n_recomendado}). "
                       "La extrapolación a periodos de retorno elevados tiene validez estadística limitada.")
        if ajuste.n_ceros:
            st.caption(f"Se excluyeron {ajuste.n_ceros} años con PMA = 0 (incompatibles con modelos logarítmicos).")

        df_res = frecuencia.tabla_cuantiles(ajuste)
        st.subheader("Cuantiles de Precipitación de Diseño (PMA 24h)")
        tabla(df_res.set_index("Periodo de Retorno T (Años)"))

        st.subheader("Bondad de Ajuste (Kolmogorov-Smirnov)")
        tabla(ajuste.ks, hide_index=True)
        st.caption(f"Menor estadístico D: **{ajuste.mejor}**. Nota: los parámetros se estiman con la misma muestra, "
                   "por lo que la prueba KS es conservadora (tiende a aceptar). Úsela junto con la inspección gráfica.")

        c1, c2 = st.columns(2)
        descarga_csv("Descargar cuantiles (CSV)", df_res, f"cuantiles_PMA_{estacion}.csv", ctx.key("dl_cuantiles"), c1)
        descarga_csv("Descargar prueba KS (CSV)", ajuste.ks, f"bondad_ajuste_{estacion}.csv", ctx.key("dl_ks"), c2)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ajuste.t_empirico, y=ajuste.x_sorted, mode="markers",
                                 name="Datos Empíricos (Weibull)", marker=dict(color="black", size=8)))
        for dist, (color, dash) in ESTILOS_DIST.items():
            fig.add_trace(go.Scatter(x=ajuste.t_empirico, y=ajuste.curvas[dist], mode="lines",
                                     name=f"Distribución {dist}", line=dict(color=color, dash=dash)))
        fig.update_layout(
            title="Curvas de Frecuencia Teóricas vs Empíricas",
            xaxis_title="Periodo de Retorno (Años)", yaxis_title="Precipitación Máxima Diaria (mm)",
            xaxis=dict(type="log", tickvals=[1.1, 2, 5, 10, 20, 50, 100, 200, 500],
                       ticktext=["1.1", "2", "5", "10", "20", "50", "100", "200", "500"]),
            hovermode="x unified", legend=dict(yanchor="bottom", y=0.01, xanchor="right", x=0.99),
        )
        grafico(fig)

    @staticmethod
    def _tormenta(ctx: Contexto, ajuste: frecuencia.ResultadoAjuste | None, estacion: str) -> None:
        tc = ctx.settings.tormenta
        justificacion("Desagregación temporal de la tormenta de diseño (24 hrs) mediante curvas IDF y el método de Bloques Alternos. Define la serie de tiempo para el modelo lluvia-escorrentía HEC-HMS.")
        if ajuste is None:
            st.error("No hay ajuste probabilístico disponible para construir la tormenta de diseño.")
            return

        dists = list(ajuste.cuantiles.keys())
        c1, c2, c3, c4 = st.columns(4)
        dist_sel = c1.selectbox("Modelo Probabilístico:", dists, index=dists.index(ajuste.mejor), key=ctx.key("dist"))
        t_sel = c2.selectbox("Periodo de Retorno (Años):", list(tc.t_diseno), key=ctx.key("t_diseno"))
        dt_sel = c3.selectbox("Intervalo de Tiempo Δt (min):", list(tc.dt_minutos), key=ctx.key("dt"))
        coef_b = c4.number_input("Coef. Desagregación (b):", min_value=tc.b_min, max_value=tc.b_max,
                                 value=tc.b_defecto, step=0.01, key=ctx.key("coef_b"))

        p24 = ajuste.cuantiles[dist_sel][t_sel]
        st.info(f"Precipitación Base ($P_{{24}}$): **{p24:.2f} mm** (Distribución {dist_sel}, T={t_sel} años). Coeficiente $b={coef_b}$.")

        duraciones = np.linspace(0.25, 24, 100)
        grid = dict(showgrid=True, gridcolor="rgba(128,128,128,0.4)",
                    minor=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)"))
        fig = go.Figure()
        for t_plot in tc.t_diseno:
            fig.add_trace(go.Scatter(x=duraciones,
                                     y=tormentas.intensidad_idf(ajuste.cuantiles[dist_sel][t_plot], duraciones, coef_b),
                                     mode="lines", name=f"T = {t_plot} años"))
        fig.update_layout(
            title=f"Curvas Intensidad-Duración-Frecuencia (IDF) - Modelo {dist_sel}",
            xaxis_title="Duración (Horas)", yaxis_title="Intensidad (mm/h)", hovermode="x unified",
            xaxis=dict(type="log", tickvals=[0.25, 0.5, 1, 2, 4, 6, 8, 12, 24],
                       ticktext=["0.25", "0.5", "1", "2", "4", "6", "8", "12", "24"], **grid),
            yaxis=dict(type="log", **grid),
        )
        grafico(fig)

        tiempos, hieto = tormentas.hietograma_bloques_alternos(p24, dt_sel, 24, coef_b)
        fig = go.Figure(data=[go.Bar(x=tiempos / 60.0, y=hieto, marker_color="#1f77b4")])
        fig.update_layout(title=f"Hietograma de Diseño - Bloques Alternos (T={t_sel} años, Δt={dt_sel} min)",
                          xaxis_title="Tiempo (Horas)", yaxis_title=f"Precipitación cada {dt_sel} min (mm)",
                          bargap=0, hovermode="x unified")
        grafico(fig)

        st.subheader("Datos para Time-Series en HEC-HMS")
        df_hec = tormentas.tabla_hec_hms(tiempos, hieto)
        st.caption(f"Verificación: suma del hietograma = {hieto.sum():.2f} mm (P24 = {p24:.2f} mm).")
        tabla(df_hec)
        descarga_csv("Descargar hietograma (CSV)", df_hec, f"hietograma_T{t_sel}_dt{dt_sel}_{estacion}.csv",
                     ctx.key("dl_hietograma"))
