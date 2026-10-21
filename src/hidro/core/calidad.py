"""Selección de parámetros fisicoquímicos."""

from __future__ import annotations

import pandas as pd


def parametros_disponibles(df: pd.DataFrame, col_param: str) -> list[str]:
    return sorted(df[col_param].dropna().unique().tolist())


def filtrar_parametro(df: pd.DataFrame, col_param: str, parametro: str) -> tuple[pd.DataFrame, str]:
    """Registros de un parámetro y su unidad.

    ADVERTENCIA (hallazgo #11): la unidad se toma de la primera fila; no se verifica que sea única.
    """
    df_param = df[df[col_param] == parametro]
    unidad = df_param["UNIDAD"].iloc[0] if "UNIDAD" in df_param.columns and not df_param.empty else ""
    return df_param, unidad
