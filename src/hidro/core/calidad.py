"""Selección de parámetros fisicoquímicos y clasificación por marca de calidad DGA."""

from __future__ import annotations

import pandas as pd

COL_MARCA_DGA = "CALIDAD"
COL_CATEGORIA = "Marca"

CUANTIFICADO = "Cuantificado (=)"
SIN_MARCA = "Sin marca"
BAJO_LD = "Bajo límite de detección (<)"
SOBRE_RANGO = "Sobre rango (>)"
MARCAS_DGA = {"=": CUANTIFICADO, "": SIN_MARCA, "<": BAJO_LD, ">": SOBRE_RANGO}
CENSURADAS = (BAJO_LD, SOBRE_RANGO)


def parametros_disponibles(df: pd.DataFrame, col_param: str) -> list[str]:
    return sorted(df[col_param].dropna().unique().tolist())


def filtrar_parametro(df: pd.DataFrame, col_param: str, parametro: str) -> tuple[pd.DataFrame, str]:
    """Registros de un parámetro y su unidad (tomada de la primera fila; en los datos DGA revisados
    cada parámetro tiene una sola unidad)."""
    df_param = df[df[col_param] == parametro]
    unidad = df_param["UNIDAD"].iloc[0] if "UNIDAD" in df_param.columns and not df_param.empty else ""
    return df_param, unidad


def clasificar_marca(df: pd.DataFrame) -> pd.Series:
    """Categoría de cada muestra según la columna CALIDAD de la DGA (hallazgo #11).

    "<": el VALOR registrado es el límite de detección, no una concentración medida.
    ">": el VALOR es el límite superior del rango analítico. Códigos no documentados quedan
    como "Otra marca (x)". Sin columna CALIDAD, todas las muestras quedan "Sin marca".
    """
    if COL_MARCA_DGA not in df.columns:
        return pd.Series(SIN_MARCA, index=df.index, name=COL_CATEGORIA)
    marca = df[COL_MARCA_DGA].fillna("").astype(str).str.strip()
    return marca.map(lambda m: MARCAS_DGA.get(m, f"Otra marca ({m})")).rename(COL_CATEGORIA)


def resumen_marcas(categorias: pd.Series) -> pd.DataFrame:
    """Número y porcentaje [%] de muestras por categoría, de mayor a menor."""
    n = categorias.value_counts()
    return pd.DataFrame({COL_CATEGORIA: n.index, "Muestras": n.values,
                         "%": (100 * n.values / max(len(categorias), 1)).round(1)})
