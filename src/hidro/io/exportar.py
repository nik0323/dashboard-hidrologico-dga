"""Exportación de tablas."""

import pandas as pd


def a_csv(df: pd.DataFrame) -> bytes:
    """CSV listo para Excel en configuración regional chilena (; y coma decimal, UTF-8 con BOM)."""
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
