"""Lectura de series DGA y estaciones auxiliares AGROMET."""

from __future__ import annotations

import glob
import io
import logging
import os

import pandas as pd

from hidro.core import columnas as c
from hidro.core.geo import dms_a_decimal

logger = logging.getLogger(__name__)

Fuente = str | os.PathLike | bytes | bytearray


def leer_csv(fuente: Fuente, **kwargs) -> pd.DataFrame:
    """Lee un CSV desde una ruta o desde bytes, probando UTF-8 y luego Latin-1."""
    for encoding in ("utf-8", "latin-1"):
        try:
            origen = io.BytesIO(fuente) if isinstance(fuente, (bytes, bytearray)) else fuente
            return pd.read_csv(origen, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            logger.info("Codificación %s falló, probando la siguiente.", encoding)
    raise ValueError("No fue posible decodificar el archivo con UTF-8 ni Latin-1.")


def cargar_serie_dga(fuente: Fuente, columna_valor: str) -> pd.DataFrame:
    """Lee una serie DGA y homologa cabeceras.

    `columna_valor` es "VALOR" (coincidencia exacta) o un fragmento del nombre de la columna
    de la variable ("PRECIPIT", "CAUDAL", "NIVEL"). Devuelve FECHA_DT, AÑO, MES, MES_NOMBRE,
    Valor_Registrado y, si hay coordenadas, LAT_DEC / LON_DEC [°]. Descarta filas con fecha
    o valor inválido.

    ADVERTENCIA (hallazgo #11): valores censurados ("<0.01") quedan como NaN y se descartan.
    """
    df = leer_csv(fuente, sep=",")
    df.columns = df.columns.str.strip().str.upper()
    df = df.rename(columns={"FECHA MEDICION": "FECHA", "LATITUD": "LAT", "LONGITUD": "LONG"})

    if "FECHA" not in df.columns:
        raise ValueError(f"El archivo no tiene columna de fecha. Columnas: {list(df.columns)}")

    df[c.FECHA] = pd.to_datetime(df["FECHA"], dayfirst=True, errors="coerce")
    df[c.ANIO] = df[c.FECHA].dt.year
    df[c.MES] = df[c.FECHA].dt.month
    df[c.MES_NOMBRE] = df[c.FECHA].dt.strftime("%b")

    if columna_valor == "VALOR":
        col_var = "VALOR" if "VALOR" in df.columns else None
    else:
        col_var = next((col for col in df.columns if columna_valor.upper() in col), None)
    if col_var is None:
        raise ValueError(f"No se encontró una columna que contenga '{columna_valor}'. Columnas: {list(df.columns)}")

    df = df.rename(columns={col_var: c.VALOR})
    if df[c.VALOR].dtype == "object":
        df[c.VALOR] = df[c.VALOR].astype(str).str.replace(",", ".", regex=False)
    df[c.VALOR] = pd.to_numeric(df[c.VALOR], errors="coerce")

    if "LAT" in df.columns and "LONG" in df.columns:
        df[c.LAT] = df["LAT"].apply(dms_a_decimal)
        df[c.LON] = df["LONG"].apply(dms_a_decimal)

    n_antes = len(df)
    df = df.dropna(subset=[c.FECHA, c.VALOR])
    if len(df) < n_antes:
        logger.info("Se descartaron %d filas con fecha o valor inválido.", n_antes - len(df))
    return df


def cargar_agromet(directorio: str | os.PathLike, patron: str, qa_max_mm_h: float) -> tuple[pd.DataFrame, list[str]]:
    """Lee estaciones AGROMET horarias, aplica QA/QC y agrega a precipitación diaria [mm].

    Los registros horarios > `qa_max_mm_h` [mm/h] se anulan. Si un día aparece en varios
    archivos se conserva el primero. Devuelve (DataFrame FECHA_DT / Precip_mm, advertencias).

    ADVERTENCIA (hallazgos #5 y #6): día calendario 00-24 h (DGA usa 08-08 h), horas sin
    dato se suman como 0 mm y los valores rechazados por QA se reemplazan por 0, no por NaN.
    """
    archivos = glob.glob(os.path.join(directorio, patron))
    advertencias = []
    lista = []
    for archivo in archivos:
        nombre = os.path.basename(archivo)
        try:
            df = leer_csv(archivo)
        except (OSError, ValueError, pd.errors.ParserError) as e:
            advertencias.append(f"{nombre}: no se pudo leer ({e}).")
            logger.warning("AGROMET %s ilegible: %s", nombre, e)
            continue

        col_fecha = df.columns[0]
        col_precip = next((col for col in df.columns if "PRECIPIT" in col.upper()), None)
        if col_precip is None:
            advertencias.append(f"{nombre}: sin columna de precipitación, se omite.")
            continue

        df[c.FECHA] = pd.to_datetime(df[col_fecha], format="%d/%m/%Y %H:%M", errors="coerce")
        df["Precip_mm"] = pd.to_numeric(df[col_precip], errors="coerce").fillna(0)

        n_qa = int((df["Precip_mm"] > qa_max_mm_h).sum())
        if n_qa:
            advertencias.append(f"{nombre}: {n_qa} registros > {qa_max_mm_h:.0f} mm/h anulados por QA/QC.")
        df.loc[df["Precip_mm"] > qa_max_mm_h, "Precip_mm"] = 0.0

        df = df.dropna(subset=[c.FECHA])
        diario = df.groupby(df[c.FECHA].dt.normalize())["Precip_mm"].sum().reset_index()
        lista.append(diario)

    if not lista:
        return pd.DataFrame(columns=[c.FECHA, "Precip_mm"]), advertencias

    total = pd.concat(lista, ignore_index=True).sort_values(c.FECHA)
    total = total.drop_duplicates(subset=[c.FECHA])
    return total, advertencias
