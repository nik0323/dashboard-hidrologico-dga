"""Módulo 2: Parámetros de cuenca para HEC-HMS (tc, CN ponderado, S, Ia, lag)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import cuenca as calc
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui.componentes import descarga_csv

MODO_PENDIENTE = "Pendiente Media (m/m)"
MODO_DESNIVEL = "Desnivel Topográfico (m)"

# [SUPUESTO: cuenca de ejemplo del original (Lo Moscoso); el usuario reemplaza los valores con su DEM]
TABLA_CN_EJEMPLO = pd.DataFrame({
    "Cobertura/Suelo": ["Bosque Nativo/Plantación", "Matorral (Kia2)", "Suelo Agrícola (Q1)",
                        "Suelo Desnudo / Roca", "Urbano / Caminos"],
    "GHS (SCS)": ["B", "C", "B", "D", "C"],
    calc.COL_CN: [60, 73, 67, 91, 89],
    calc.COL_AREA: [10.0, 45.0, 30.0, 10.0, 5.0],
})


@registrar
class Cuenca(Modulo):
    clave = "cuenca"
    nombre = "Parámetros de Cuenca (HEC-HMS)"
    orden = 20

    def render(self, ctx: Contexto) -> None:
        st.title("Parametrización Hidrológica de Cuenca (Inputs HEC-HMS)")
        st.caption("Cálculo de variables geomorfológicas y coeficientes de escorrentía para simulación hidrodinámica.")

        col1, col2 = st.columns(2)
        with col1:
            area_km2, t_lag = self._morfometria(ctx)
        with col2:
            cn, retencion = self._numero_curva(ctx)

        st.divider()
        st.header("3. Ficha Resumen para Modelo de Cuenca (HEC-HMS)")
        if cn is None:
            st.info("Corrija la tabla de coberturas para generar la ficha.")
            return

        resumen = calc.ficha_hec_hms(area_km2, retencion.ia, cn, t_lag)
        st.table(resumen)
        descarga_csv("Descargar ficha HEC-HMS (CSV)", resumen, "ficha_HEC-HMS.csv", ctx.key("dl_ficha"))
        st.caption("Nota: El porcentaje impermeable se asume integrado en la ponderación del CN mediante las coberturas urbanas. "
                   "El Lag Time (0.6·tc) se transformó a minutos según la convención de HEC-HMS.")

    @staticmethod
    def _morfometria(ctx: Contexto) -> tuple[float, float]:
        """Entradas morfométricas y tc. Devuelve (área [km²], lag [h])."""
        st.header("1. Morfometría y Tiempo de Concentración")
        st.markdown("Ingrese los parámetros extraídos desde el DEM.")
        area_km2 = st.number_input("Área de la Cuenca ($A$ en $km^2$):", min_value=0.1, value=15.5, step=0.1,
                                   key=ctx.key("area"))
        longitud_km = st.number_input("Longitud del Cauce Principal ($L$ en $km$):", min_value=0.1, value=8.2,
                                      step=0.1, key=ctx.key("longitud"))

        modo = st.radio("Método de Ingreso de Pendiente:", [MODO_PENDIENTE, MODO_DESNIVEL], key=ctx.key("modo"))
        if modo == MODO_PENDIENTE:
            pendiente = st.number_input("Pendiente Media del Cauce ($S$ en $m/m$):", min_value=0.001, value=0.045,
                                        step=0.001, format="%.3f", key=ctx.key("pendiente"))
            geom = calc.geometria_desde_pendiente(longitud_km, pendiente)
        else:
            desnivel_m = st.number_input("Desnivel Topográfico del Cauce ($H_{max} - H_{min}$ en $m$):",
                                         min_value=1.0, value=369.0, step=1.0, key=ctx.key("desnivel"))
            geom = calc.geometria_desde_desnivel(longitud_km, desnivel_m)

        if geom.pendiente > calc.PENDIENTE_ALERTA:
            st.warning(f"Pendiente media de {geom.pendiente:.3f} m/m (> 50%). Revise que L y el desnivel estén en las unidades correctas.")

        tcs = calc.tiempos_concentracion(area_km2, longitud_km, geom)
        st.markdown("### Resultados de Tiempo de Concentración ($t_c$)")
        st.info(f"**Fórmula de Kirpich:** {tcs.kirpich:.2f} horas (Recomendado laderas fuertes)")
        st.info(f"**Fórmula de California:** {tcs.california:.2f} horas")
        st.info(f"**Fórmula de Giandotti:** {tcs.giandotti:.2f} horas")
        if tcs.dispersion_excesiva():
            st.warning("Las fórmulas difieren en más de 3 veces. Justifique el tc adoptado según el tipo de cuenca.")

        tc_adoptado = st.number_input("Tiempo de Concentración Adoptado ($t_c$ en horas):", min_value=0.1,
                                      value=float(round(tcs.kirpich, 2)), step=0.1, key=ctx.key("tc_adoptado"))
        return area_km2, calc.lag_scs(tc_adoptado)

    @staticmethod
    def _numero_curva(ctx: Contexto) -> tuple[float | None, calc.RetencionSCS | None]:
        """Tabla de coberturas y CN ponderado. Devuelve (CN, retención) o (None, None) si la tabla es inválida."""
        st.header("2. Determinación del Número de Curva ($CN$)")
        st.markdown("Defina la distribución de cobertura de suelo y el Grupo Hidrológico de Suelo (GHS).")
        df_cn = st.data_editor(
            TABLA_CN_EJEMPLO, num_rows="dynamic", width="stretch", key=ctx.key("tabla_cn"),
            column_config={
                calc.COL_CN: st.column_config.NumberColumn(min_value=30, max_value=100, step=1),
                calc.COL_AREA: st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.5),
                "GHS (SCS)": st.column_config.SelectboxColumn(options=["A", "B", "C", "D"]),
            },
        )

        errores = calc.validar_tabla_cn(df_cn)
        if errores:
            for err in errores:
                st.error(err)
            return None, None

        cn = calc.cn_ponderado(df_cn)
        retencion = calc.retencion_scs(cn)
        st.markdown("### Resultados de Retención e Infiltración")
        st.success(f"**Número de Curva Ponderado ($CN_{{AMC\\ II}}$):** {cn:.1f}")
        st.info(f"**Retención Máxima Potencial ($S_{{ret}}$):** {retencion.s_ret:.1f} mm")
        st.info(f"**Abstracción Inicial ($I_a$):** {retencion.ia:.1f} mm")
        return cn, retencion
