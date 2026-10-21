"""Agregaciones temporales de series diarias normalizadas (columnas de `hidro.core.columnas`)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hidro.core import columnas as c


def maximos_anuales(df: pd.DataFrame) -> pd.DataFrame:
    """Máximo por año calendario (PMA en mm/día o QMA en m³/s, según la serie).

    ADVERTENCIA (hallazgo #4): no verifica la completitud de cada año; un año con registro
    parcial entra igual a la serie de máximos.
    """
    return df.groupby(c.ANIO)[c.VALOR].max().reset_index()


def totales_mensuales(df: pd.DataFrame) -> pd.DataFrame:
    """Suma por año y mes (precipitación mensual en mm)."""
    return df.groupby([c.ANIO, c.MES, c.MES_NOMBRE])[c.VALOR].sum().reset_index()


def totales_anuales(df: pd.DataFrame) -> pd.DataFrame:
    """Suma por año calendario (precipitación anual en mm)."""
    return df.groupby(c.ANIO)[c.VALOR].sum().reset_index()


@dataclass(frozen=True)
class Estadisticos:
    """Media y desviación estándar muestral (unidades de la serie) y coeficiente de variación [%]."""

    media: float
    desv: float
    cv: float


def estadisticos(df: pd.DataFrame) -> Estadisticos:
    """Estadísticos de la columna de valor; CV = 0 si la media no es positiva."""
    media = df[c.VALOR].mean()
    desv = df[c.VALOR].std()
    cv = desv / media * 100 if media > 0 else 0
    return Estadisticos(media=media, desv=desv, cv=cv)


@dataclass(frozen=True)
class RangoNiveles:
    """Profundidad del nivel estático [m bajo superficie]: mínima (más somera), máxima y amplitud."""

    nivel_min: float
    nivel_max: float
    amplitud: float


def rango_niveles(df: pd.DataFrame) -> RangoNiveles:
    nivel_max = df[c.VALOR].max()
    nivel_min = df[c.VALOR].min()
    return RangoNiveles(nivel_min=nivel_min, nivel_max=nivel_max, amplitud=nivel_max - nivel_min)
