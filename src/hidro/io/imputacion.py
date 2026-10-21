"""Relleno de vacíos de una serie DGA diaria con una estación auxiliar (AGROMET)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hidro.core import columnas as c
from hidro.core.series import COBERTURA_MIN_ANUAL_DEFECTO, cobertura_anual
from hidro.io.normalizacion import agregar_columnas_fecha


def imputar_con_agromet(df_estacion: pd.DataFrame, df_agro: pd.DataFrame, extender: bool = False,
                        cobertura_min_anual: float = COBERTURA_MIN_ANUAL_DEFECTO) -> pd.DataFrame:
    """Rellena días sin dato de la estación DGA con AGROMET [mm], alineando por fecha.

    Solo se rellenan vacíos de años calendario cuya cobertura DGA (ver `cobertura_anual`) es
    >= `cobertura_min_anual`; un año sin registro o casi sin registro no se completa con otra
    estación. Además, por defecto solo se consideran días entre la primera y la última fecha DGA
    (hallazgo #1). `extender=True, cobertura_min_anual=0` reproduce el dashboard original.

    Días DGA repetidos se promedian. Devuelve una serie diaria con columna booleana IMPUTADO.
    """
    serie = df_estacion.groupby(df_estacion[c.FECHA].dt.normalize())[c.VALOR].mean()
    agro = df_agro.set_index(c.FECHA)["Precip_mm"]

    indice = serie.index.union(agro.index)
    if not extender:
        indice = indice[(indice >= serie.index.min()) & (indice <= serie.index.max())]
    serie = serie.reindex(indice)
    faltantes = serie.isna()
    relleno = agro.reindex(indice)
    if cobertura_min_anual > 0:
        cobertura = cobertura_anual(df_estacion)
        anio_valido = indice.year.map(cobertura).fillna(0.0) >= cobertura_min_anual
        relleno = relleno.where(anio_valido)
    serie = serie.fillna(relleno)

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


N_MIN_CORRELACION = 30


@dataclass(frozen=True)
class Correlacion:
    """Correlación de Pearson [-] entre la precipitación diaria DGA y AGROMET en días comunes (hallazgo #2)."""

    r: float
    n_dias: int


def correlacion_con_agromet(df_estacion: pd.DataFrame, df_agro: pd.DataFrame,
                            n_min: int = N_MIN_CORRELACION) -> Correlacion:
    """Pearson en días con dato en ambas series; r = NaN si hay menos de `n_min` días comunes o varianza nula."""
    dga = df_estacion.groupby(df_estacion[c.FECHA].dt.normalize())[c.VALOR].mean()
    agro = df_agro.set_index(c.FECHA)["Precip_mm"].dropna()
    comun = dga.index.intersection(agro.index)
    if len(comun) < n_min or dga[comun].std() == 0 or agro[comun].std() == 0:
        return Correlacion(r=np.nan, n_dias=len(comun))
    return Correlacion(r=float(np.corrcoef(dga[comun], agro[comun])[0, 1]), n_dias=len(comun))


def anios_bajo_cobertura(df_estacion: pd.DataFrame, df_agro: pd.DataFrame, cobertura_min_anual: float) -> list[int]:
    """Años dentro del periodo DGA con datos AGROMET que NO se imputan por cobertura DGA insuficiente."""
    cobertura = cobertura_anual(df_estacion)
    periodo = range(int(df_estacion[c.FECHA].dt.year.min()), int(df_estacion[c.FECHA].dt.year.max()) + 1)
    anios_agro = set(df_agro[c.FECHA].dt.year.astype(int))
    return [a for a in periodo if a in anios_agro and cobertura.get(a, 0.0) < cobertura_min_anual]


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
