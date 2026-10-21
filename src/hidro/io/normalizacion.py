"""Columnas derivadas y detección de columnas en archivos DGA."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from hidro.core import columnas as c


def agregar_columnas_fecha(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega AÑO, MES y MES_NOMBRE a partir de FECHA_DT (copia).

    ADVERTENCIA (hallazgo #19): MES_NOMBRE usa `strftime("%b")`, que depende del locale.
    """
    df = df.copy()
    df[c.ANIO] = df[c.FECHA].dt.year
    df[c.MES] = df[c.FECHA].dt.month
    df[c.MES_NOMBRE] = df[c.FECHA].dt.strftime("%b")
    return df


def columna_estacion(columnas: Sequence[str]) -> str:
    """Columna con el nombre de la estación (contiene 'ESTACI' y no 'COD'); si no hay, la primera."""
    return next((col for col in columnas if "ESTACI" in col and "COD" not in col), columnas[0])


def columna_parametro(columnas: Sequence[str]) -> str | None:
    """Columna con el nombre del parámetro químico (contiene 'PARAMETRO' y no 'COD')."""
    return next((col for col in columnas if "PARAMETRO" in col and "COD" not in col), None)
