"""Selección espacial de estaciones respecto a un punto de control."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hidro.core import columnas as c
from hidro.core.geo import haversine_vectorizado


@dataclass(frozen=True)
class FiltroRadio:
    """Resultado del filtro espacial.

    df_radio: filas a <= radio_km del punto de control, con columna `Distancia_km` [km].
    sin_coordenadas: estaciones excluidas por tener LAT/LON inválidas.
    """

    df_radio: pd.DataFrame
    sin_coordenadas: list


def filtrar_por_radio(df: pd.DataFrame, lat_ref: float, lon_ref: float, radio_km: float,
                      col_estacion: str) -> FiltroRadio:
    """Calcula la distancia [km] de cada fila al punto de control y conserva las de distancia <= radio_km."""
    sin_coord = df.loc[df[c.LAT].isna() | df[c.LON].isna(), col_estacion].unique()
    df = df.dropna(subset=[c.LAT, c.LON]).copy()
    df[c.DISTANCIA] = haversine_vectorizado(lat_ref, lon_ref, df[c.LAT], df[c.LON])
    return FiltroRadio(df_radio=df[df[c.DISTANCIA] <= radio_km], sin_coordenadas=list(sin_coord))


def resumen_estaciones(df_radio: pd.DataFrame, col_estacion: str) -> pd.DataFrame:
    """Una fila por estación (coordenadas, distancia [km] y altitud [m] si existe), ordenada por distancia."""
    agregaciones = {c.LAT: "first", c.LON: "first", c.DISTANCIA: "first"}
    if "ALTITUD" in df_radio.columns:
        agregaciones["ALTITUD"] = "first"
    return df_radio.groupby(col_estacion).agg(agregaciones).reset_index().sort_values(c.DISTANCIA)


def serie_estacion(df_radio: pd.DataFrame, col_estacion: str, estacion: str) -> pd.DataFrame:
    """Registros de una estación ordenados por fecha."""
    return df_radio[df_radio[col_estacion] == estacion].sort_values(c.FECHA).copy()
