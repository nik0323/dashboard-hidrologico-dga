"""Agregaciones temporales de series diarias normalizadas (columnas de `hidro.core.columnas`)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass

import pandas as pd

from hidro.core import columnas as c

COBERTURA_MIN_ANUAL_DEFECTO = 0.80


def cobertura_anual(df: pd.DataFrame) -> pd.Series:
    """Fracción [-] de días de cada año calendario con registro (días distintos / 365 o 366)."""
    dias = df[c.FECHA].dt.normalize().drop_duplicates()
    n = dias.groupby(dias.dt.year).size()
    dias_anio = pd.Series([366 if calendar.isleap(int(a)) else 365 for a in n.index], index=n.index)
    return n / dias_anio


def anios_incompletos(df: pd.DataFrame, cobertura_min_anual: float) -> list[int]:
    """Años presentes en la serie cuya cobertura es < `cobertura_min_anual`."""
    cobertura = cobertura_anual(df)
    return sorted(int(a) for a, f in cobertura.items() if f < cobertura_min_anual)


def maximos_anuales(df: pd.DataFrame, cobertura_min_anual: float = COBERTURA_MIN_ANUAL_DEFECTO) -> pd.DataFrame:
    """Máximo por año calendario (PMA en mm/día o QMA en m³/s, según la serie).

    Se excluyen los años con cobertura < `cobertura_min_anual` (hallazgo #4): un año con
    registro parcial puede no contener el evento máximo y sesgar los cuantiles a la baja.
    `cobertura_min_anual=0` reproduce el dashboard original.
    """
    maximos = df.groupby(c.ANIO)[c.VALOR].max().reset_index()
    if cobertura_min_anual > 0:
        cobertura = cobertura_anual(df)
        completos = maximos[c.ANIO].map(cobertura).fillna(0.0) >= cobertura_min_anual
        maximos = maximos[completos].reset_index(drop=True)
    return maximos


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
