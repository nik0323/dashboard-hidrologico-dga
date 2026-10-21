"""Obtención de archivos de datos: carpeta configurada o subida desde el navegador."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from hidro.contexto import Contexto
from hidro.ui import cache

logger = logging.getLogger(__name__)


def obtener_fuente(ctx: Contexto, clave: str) -> str | bytes:
    """Ruta del archivo `clave` (ver [datos.archivos]) si existe; si no, ofrece subirlo. Detiene la app sin datos."""
    nombre = ctx.settings.archivos[clave]
    ruta = ctx.dir_datos / nombre
    if ruta.is_file():
        return str(ruta)

    st.warning(f"No se encontró **{nombre}** en `{ctx.dir_datos}`. Puedes subir el archivo aquí:")
    subido = st.file_uploader(f"Subir {nombre}", type=["txt", "csv"], key=ctx.key(f"upload_{clave}"))
    if subido is None:
        st.stop()
    return subido.getvalue()


def cargar_o_detener(fuente: str | bytes, columna_valor: str, mensaje: str,
                     conservar_sin_valor: bool = False) -> pd.DataFrame:
    with st.spinner(mensaje):
        try:
            return cache.cargar_serie_dga(fuente, columna_valor, conservar_sin_valor)
        except (OSError, ValueError, pd.errors.ParserError) as e:
            logger.exception("Error al cargar datos")
            st.error(f"No se pudieron cargar los datos: {e}")
            st.stop()
