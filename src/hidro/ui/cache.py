"""Lectura con caché de Streamlit. La clave incluye mtime y tamaño de los archivos (hallazgo #18)."""

from __future__ import annotations

import glob
import os

import pandas as pd
import streamlit as st

from hidro.io import lectura


def firma_archivo(ruta: str) -> tuple[str, float, int]:
    """(ruta, mtime, tamaño): cambia si el archivo se modifica en disco."""
    estado = os.stat(ruta)
    return ruta, estado.st_mtime, estado.st_size


@st.cache_data(show_spinner=False)
def _serie_dga(fuente: str | bytes, columna_valor: str, conservar_sin_valor: bool, firma: tuple | None) -> pd.DataFrame:
    return lectura.cargar_serie_dga(fuente, columna_valor, conservar_sin_valor)


def cargar_serie_dga(fuente: str | bytes, columna_valor: str, conservar_sin_valor: bool = False) -> pd.DataFrame:
    firma = firma_archivo(fuente) if isinstance(fuente, str) else None
    return _serie_dga(fuente, columna_valor, conservar_sin_valor, firma)


@st.cache_data(show_spinner=False)
def _agromet(directorio: str, patron: str, qa_max_mm_h: float, firma: tuple) -> tuple[pd.DataFrame, list[str]]:
    return lectura.cargar_agromet(directorio, patron, qa_max_mm_h)


def cargar_agromet(directorio: str, patron: str, qa_max_mm_h: float) -> tuple[pd.DataFrame, list[str]]:
    firma = tuple(firma_archivo(f) for f in sorted(glob.glob(os.path.join(directorio, patron))))
    return _agromet(directorio, patron, qa_max_mm_h, firma)
