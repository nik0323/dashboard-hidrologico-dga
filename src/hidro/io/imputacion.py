"""Relleno de vacíos de una serie DGA diaria con una estación auxiliar (AGROMET)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hidro.core import columnas as c
from hidro.io.normalizacion import agregar_columnas_fecha


def imputar_con_agromet(df_estacion: pd.DataFrame, df_agro: pd.DataFrame, extender: bool = False) -> pd.DataFrame:
    """Rellena días sin dato de la estación DGA con AGROMET [mm], alineando por fecha.

    Por defecto solo se rellenan vacíos internos: días entre la primera y la última fecha
    con registro DGA. Con `extender=True` también se agregan días AGROMET antes y después
    del periodo DGA (comportamiento del dashboard original, hallazgo #1); esos años quedan
    con PMA proveniente de otra estación y alteran n, momentos y cuantiles.

    Días DGA repetidos se promedian. Devuelve una serie diaria con columna booleana IMPUTADO.
    """
    serie = df_estacion.groupby(df_estacion[c.FECHA].dt.normalize())[c.VALOR].mean()
    agro = df_agro.set_index(c.FECHA)["Precip_mm"]

    indice = serie.index.union(agro.index)
    if not extender:
        indice = indice[(indice >= serie.index.min()) & (indice <= serie.index.max())]
    serie = serie.reindex(indice)
    faltantes = serie.isna()
    serie = serie.fillna(agro.reindex(indice))

    out = pd.DataFrame({
        c.FECHA: indice,
        c.VALOR: serie.values,
        c.IMPUTADO: (faltantes & serie.notna()).values,
    }).dropna(subset=[c.VALOR])
    return agregar_columnas_fecha(out)


def serie_sin_imputar(df_estacion: pd.DataFrame) -> pd.DataFrame:
    """Serie DGA con las columnas de trabajo e IMPUTADO = False."""
    df = df_estacion[[c.FECHA, c.ANIO, c.MES, c.MES_NOMBRE, c.VALOR]].copy()
    df[c.IMPUTADO] = False
    return df


@dataclass(frozen=True)
class ResumenImputacion:
    """Días imputados, fracción de la serie [-] y años cuya PMA proviene de un día imputado."""

    n_imputados: int
    fraccion: float
    anios_pma_imputada: list[int]


def resumen_imputacion(df: pd.DataFrame) -> ResumenImputacion:
    n_imp = int(df[c.IMPUTADO].sum())
    idx_max = df.groupby(c.ANIO)[c.VALOR].idxmax()
    filas_pma = df.loc[idx_max]
    anios = sorted(filas_pma.loc[filas_pma[c.IMPUTADO], c.ANIO].astype(int).tolist())
    return ResumenImputacion(n_imputados=n_imp, fraccion=n_imp / max(len(df), 1), anios_pma_imputada=anios)
