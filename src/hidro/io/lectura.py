"""Lectura de series DGA y estaciones auxiliares AGROMET."""

from __future__ import annotations

import glob
import io
import logging
import os

import numpy as np
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


def cargar_serie_dga(fuente: Fuente, columna_valor: str, conservar_sin_valor: bool = False) -> pd.DataFrame:
    """Lee una serie DGA y homologa cabeceras.

    `columna_valor` es "VALOR" (coincidencia exacta) o un fragmento del nombre de la columna
    de la variable ("PRECIPIT", "CAUDAL", "NIVEL"). Devuelve FECHA_DT, AÑO, MES, MES_NOMBRE,
    Valor_Registrado y, si hay coordenadas, LAT_DEC / LON_DEC [°]. Descarta filas con fecha
    inválida y, salvo `conservar_sin_valor=True`, filas sin valor numérico (p. ej. pozos
    "Seco" / "Sin acceso", que el módulo de pozos necesita conservar; hallazgo #12).

    La censura de calidad viene en la columna CALIDAD (ver `core.calidad`); un VALOR textual
    como "<0.01" no es numérico y se trata como fila sin valor.
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
        df[c.LAT] = df["LAT"].apply(dms_a_decimal, tipo="lat")
        df[c.LON] = df["LONG"].apply(dms_a_decimal, tipo="lon")

    n_antes = len(df)
    df = df.dropna(subset=[c.FECHA] if conservar_sin_valor else [c.FECHA, c.VALOR])
    if len(df) < n_antes:
        logger.info("Se descartaron %d filas con fecha o valor inválido.", n_antes - len(df))
    return df


DESFASE_DIA_PLUVIOMETRICO_H = 8
HORAS_MIN_DIA = 24


def cargar_agromet(directorio: str | os.PathLike, patron: str, qa_max_mm_h: float,
                   desfase_horas: int = DESFASE_DIA_PLUVIOMETRICO_H,
                   horas_min_dia: int = HORAS_MIN_DIA) -> tuple[pd.DataFrame, list[str]]:
    """Lee estaciones AGROMET horarias, aplica QA/QC y agrega a precipitación diaria [mm].

    Cada registro horario con marca t acumula la hora (t − 1 h, t]. El día pluviométrico D
    suma las horas en (D + desfase, D + desfase + 24 h], es decir de 08:00 de D a 08:00 de D+1
    con el desfase por defecto, que es la ventana de lectura de los pluviómetros DGA (hallazgo #5;
    respaldado por la correlación con DGA CONVENTO VIEJO: r = 0.92 contra 0.81 con 00-24 h).

    Las horas sin dato y los registros > `qa_max_mm_h` [mm/h] quedan como faltantes, no como 0.
    Solo se conservan los días con al menos `horas_min_dia` horas válidas (hallazgo #6). Si una
    misma hora aparece en varios archivos, se conserva la del primero en orden alfabético.
    Devuelve (DataFrame FECHA_DT / Precip_mm, advertencias).
    """
    archivos = sorted(glob.glob(os.path.join(directorio, patron)))
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

        horario = pd.DataFrame({
            "t": pd.to_datetime(df[col_fecha], format="%d/%m/%Y %H:%M", errors="coerce"),
            "p": pd.to_numeric(df[col_precip], errors="coerce"),
        })
        n_qa = int((horario["p"] > qa_max_mm_h).sum())
        if n_qa:
            advertencias.append(f"{nombre}: {n_qa} registros > {qa_max_mm_h:.0f} mm/h anulados por QA/QC.")
        horario.loc[horario["p"] > qa_max_mm_h, "p"] = np.nan
        lista.append(horario.dropna(subset=["t"]))

    if not lista:
        return pd.DataFrame(columns=[c.FECHA, "Precip_mm"]), advertencias

    horario = pd.concat(lista, ignore_index=True).drop_duplicates(subset=["t"], keep="first")
    dia = (horario["t"] - pd.Timedelta(hours=desfase_horas) - pd.Timedelta(seconds=1)).dt.normalize()
    agrupado = horario.groupby(dia)["p"]
    diario = pd.DataFrame({"Precip_mm": agrupado.sum(min_count=1), "horas": agrupado.count()})
    completos = diario["horas"] >= horas_min_dia
    n_incompletos = int((~completos).sum())
    if n_incompletos:
        advertencias.append(f"{n_incompletos} días AGROMET con menos de {horas_min_dia} h válidas se descartan "
                            "(no se usan para imputar).")
    advertencias.append(f"Día pluviométrico AGROMET: {desfase_horas:02d}:00 de la fecha a {desfase_horas:02d}:00 "
                        "del día siguiente (ventana de lectura DGA).")
    total = (diario.loc[completos, ["Precip_mm"]].rename_axis(c.FECHA).reset_index()
             .sort_values(c.FECHA, ignore_index=True))
    return total, advertencias
