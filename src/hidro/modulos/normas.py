"""Módulo 6: Cumplimiento de normas de calidad de agua (NCh 409/1 agua potable, NCh 1333 riego)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from hidro.contexto import Contexto
from hidro.core import columnas as c
from hidro.core.calidad import COL_CATEGORIA, clasificar_marca
from hidro.core.normas import (COL_ESTADO, CUMPLE, CUMPLE_BAJO_LD, EXCEDE, INDETERMINADO, NO_EVALUABLE,
                               evaluar_muestras, muestras_limite, resumen_cumplimiento)
from hidro.io.normalizacion import columna_parametro
from hidro.io.normas import cargar_normas
from hidro.modulos.base import Modulo
from hidro.modulos.registro import registrar
from hidro.ui import datos, red
from hidro.ui.componentes import descarga_csv, encabezado, grafico, justificacion, tabla

COLORES_ESTADO = {CUMPLE: "#2ca02c", CUMPLE_BAJO_LD: "#98df8a", EXCEDE: "#d62728",
                  INDETERMINADO: "#ff7f0e", NO_EVALUABLE: "#7f7f7f"}


@registrar
class Normas(Modulo):
    clave = "normas"
    nombre = "Normas de Calidad (NCh 409 / 1333)"
    orden = 55
    archivos_requeridos = ("calidad",)

    def render(self, ctx: Contexto) -> None:
        encabezado(
            "Cumplimiento Normativo de Calidad de Agua",
            "Fuente: DGA - Red de monitoreo de calidad de aguas. Límites: config/normas.toml.",
            "Comparación de las concentraciones registradas con los requisitos de NCh 409/1 (agua potable) "
            "y NCh 1333 (riego), considerando la censura por límite de detección informada por la DGA.",
        )
        try:
            normas, limites = cargar_normas(ctx.settings.archivo_normas)
        except (OSError, ValueError) as e:
            st.error(f"No se pudo leer el archivo de normas: {e}")
            st.stop()

        fuente = datos.obtener_fuente(ctx, "calidad")
        df = datos.cargar_o_detener(fuente, "VALOR", "Indexando base de datos geoquímica multivariable...")
        df_radio, col_est = red.filtro_radio(ctx, df, "normas")
        estacion, df_est = red.mapa_y_selector(
            ctx, df_radio, col_est, "1. Estación de Monitoreo", "Ubicación de Puntos de Muestreo Geoquímico",
            px.colors.sequential.Plasma, "Seleccione la estación a evaluar:",
        )
        col_param = columna_parametro(df_est.columns)
        if col_param is None:
            st.warning("El archivo no incluye una columna de parámetros químicos (PARAMETRO).")
            return
        df_est = df_est.assign(**{COL_CATEGORIA: clasificar_marca(df_est)})

        st.header(f"2. Evaluación Normativa: {estacion}")
        clave_norma = st.selectbox("Norma:", list(normas), format_func=lambda k: normas[k].nombre,
                                   key=ctx.key("norma"))
        norma = normas[clave_norma]
        limites_norma = [lim for lim in limites if lim.norma == clave_norma]
        st.caption(f"Fuente de los límites: {norma.fuente}")

        sin_verificar = [lim.parametro for lim in limites_norma if not lim.verificado]
        if sin_verificar:
            st.warning(f"{len(sin_verificar)} de {len(limites_norma)} límites de esta norma NO están verificados "
                       "contra el texto oficial (`verificado = false` en config/normas.toml). "
                       "No use estos resultados en un informe sin verificarlos.")

        resumen = resumen_cumplimiento(df_est, col_param, limites_norma)
        evaluados = resumen[resumen["Determinadas"] > 0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Parámetros con datos determinados", f"{len(evaluados)} de {len(resumen)}")
        c2.metric("Parámetros con excedencias", f"{int((evaluados['Excedencias'] > 0).sum())}")
        c3.metric("Muestras indeterminadas (LD sobre el límite)", f"{int(resumen['Indeterminadas'].sum())}")

        justificacion("Una muestra bajo el límite de detección (marca '<') solo se considera conforme si el límite "
                      "de detección es menor o igual que el límite normativo; en caso contrario queda indeterminada. "
                      "El porcentaje de excedencia se calcula sobre las muestras determinadas.")
        tabla(resumen, hide_index=True)
        descarga_csv("Descargar evaluación (CSV)", resumen, f"normas_{clave_norma}_{estacion}.csv", ctx.key("dl_resumen"))

        self._detalle(ctx, df_est, col_param, limites_norma, clave_norma)

    @staticmethod
    def _detalle(ctx: Contexto, df_est, col_param: str, limites_norma, clave_norma: str) -> None:
        con_datos = [lim for lim in limites_norma if not muestras_limite(df_est, col_param, lim).empty]
        if not con_datos:
            st.info("La estación no tiene muestras de los parámetros de esta norma.")
            return
        st.subheader("3. Detalle por Parámetro")
        nombres = [lim.parametro for lim in con_datos]
        lim = con_datos[nombres.index(st.selectbox("Parámetro:", nombres, key=ctx.key(f"param__{clave_norma}")))]
        d = muestras_limite(df_est, col_param, lim)
        d = d.assign(**{COL_ESTADO: evaluar_muestras(d, lim)}).sort_values(c.FECHA)

        fig = px.scatter(d, x=c.FECHA, y=c.VALOR, color=COL_ESTADO, symbol=COL_CATEGORIA,
                         color_discrete_map=COLORES_ESTADO,
                         labels={c.FECHA: "Fecha de Muestreo", c.VALOR: f"{lim.parametro} ({lim.unidad_dga})",
                                 COL_CATEGORIA: "Marca DGA"},
                         title=f"{lim.parametro}: límite {lim.texto()} {lim.unidad_dga}")
        for valor, nombre in ((lim.maximo, "Máximo"), (lim.minimo, "Mínimo")):
            if valor is not None:
                fig.add_hline(y=valor, line_dash="dash", line_color="#d62728",
                              annotation_text=f"{nombre} norma: {valor:g}")
        grafico(fig)
        if lim.nota:
            st.caption(f"Nota: {lim.nota}")
