"""Comparación de muestras de calidad con límites normativos, respetando la censura DGA."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hidro.core import columnas as c
from hidro.core.calidad import BAJO_LD, COL_CATEGORIA, CUANTIFICADO, SIN_MARCA, SOBRE_RANGO, clasificar_marca

COL_ESTADO = "Estado"
CUMPLE = "Cumple"
CUMPLE_BAJO_LD = "Cumple (bajo LD)"
EXCEDE = "Excede"
INDETERMINADO = "Indeterminado (censurado)"
NO_EVALUABLE = "No evaluable (marca desconocida)"
DETERMINADOS = (CUMPLE, CUMPLE_BAJO_LD, EXCEDE)

SIN_PARAMETRO_DGA = "Sin parámetro DGA"
SIN_DATOS = "Sin datos"
UNIDAD_INCOMPATIBLE = "Unidad incompatible"


@dataclass(frozen=True)
class Norma:
    clave: str
    nombre: str
    fuente: str


@dataclass(frozen=True)
class Limite:
    """Límite de un parámetro en una norma. maximo / minimo en la unidad `unidad_dga`."""

    norma: str
    parametro: str
    parametros_dga: tuple[str, ...]
    unidad_dga: str
    maximo: float | None = None
    minimo: float | None = None
    verificado: bool = False
    nota: str = ""

    def texto(self) -> str:
        if self.minimo is not None and self.maximo is not None:
            return f"{self.minimo:g} – {self.maximo:g}"
        if self.maximo is not None:
            return f"≤ {self.maximo:g}"
        return f"≥ {self.minimo:g}"


def normalizar_unidad(unidad: object) -> str:
    """Primer término de la unidad DGA en minúsculas ("Mg/L Al" → "mg/l", "unid. ph" → "unid.")."""
    texto = str(unidad).strip().lower() if unidad is not None and not pd.isna(unidad) else ""
    return texto.split()[0] if texto else ""


def evaluar_muestras(df: pd.DataFrame, limite: Limite) -> pd.Series:
    """Estado de cada muestra frente al límite.

    Medidas (marca "=" o sin marca): Excede si está fuera de [minimo, maximo]; si no, Cumple.
    "<" (valor real < LD = VALOR): Excede si LD <= minimo; Cumple (bajo LD) si LD <= maximo y no
    hay mínimo; si no, Indeterminado (p. ej. LD sobre el máximo).
    ">" (valor real > VALOR): Excede si VALOR >= maximo; Cumple si no hay máximo y VALOR >= minimo;
    si no, Indeterminado. Otras marcas: No evaluable.
    """
    v = df[c.VALOR].astype(float)
    cat = df[COL_CATEGORIA] if COL_CATEGORIA in df.columns else clasificar_marca(df)
    sin_max = limite.maximo is None
    sin_min = limite.minimo is None
    fuera = pd.Series(False, index=df.index)
    if not sin_max:
        fuera |= v > limite.maximo
    if not sin_min:
        fuera |= v < limite.minimo

    medido = cat.isin([CUANTIFICADO, SIN_MARCA])
    bajo_ld = cat == BAJO_LD
    sobre = cat == SOBRE_RANGO

    ld_excede = bajo_ld & (False if sin_min else v <= limite.minimo)
    ld_cumple = bajo_ld & sin_min & (True if sin_max else v <= limite.maximo)
    sobre_excede = sobre & (False if sin_max else v >= limite.maximo)
    sobre_cumple = sobre & sin_max & (True if sin_min else v >= limite.minimo)

    estado = np.select(
        [medido & fuera, medido, ld_excede, ld_cumple, sobre_excede, sobre_cumple, bajo_ld | sobre],
        [EXCEDE, CUMPLE, EXCEDE, CUMPLE_BAJO_LD, EXCEDE, CUMPLE, INDETERMINADO],
        default=NO_EVALUABLE,
    )
    return pd.Series(estado, index=df.index, name=COL_ESTADO)


def muestras_limite(df: pd.DataFrame, col_param: str, limite: Limite) -> pd.DataFrame:
    """Muestras de los parámetros DGA asociados al límite."""
    return df[df[col_param].isin(limite.parametros_dga)]


def resumen_cumplimiento(df: pd.DataFrame, col_param: str, limites: list[Limite]) -> pd.DataFrame:
    """Una fila por límite: muestras, determinadas, excedencias, % de excedencia sobre las
    determinadas, indeterminadas, máximo medido, última muestra y estado global."""
    filas = []
    for lim in limites:
        fila = {"Parámetro": lim.parametro, "Parámetro DGA": ", ".join(lim.parametros_dga) or "—",
                "Límite": lim.texto(), "Unidad": lim.unidad_dga, "Muestras": 0, "Determinadas": 0,
                "Excedencias": 0, "% excedencia": np.nan, "Indeterminadas": 0, "Máx. medido": np.nan,
                "Última muestra": pd.NaT, "Estado": SIN_DATOS, "Verificado": lim.verificado, "Nota": lim.nota}
        d = muestras_limite(df, col_param, lim)
        if not lim.parametros_dga:
            fila["Estado"] = SIN_PARAMETRO_DGA
        elif d.empty:
            pass
        elif "UNIDAD" in d.columns and (d["UNIDAD"].map(normalizar_unidad) != lim.unidad_dga).any():
            fila["Muestras"] = len(d)
            fila["Estado"] = UNIDAD_INCOMPATIBLE
        else:
            est = evaluar_muestras(d, lim)
            cat = d[COL_CATEGORIA] if COL_CATEGORIA in d.columns else clasificar_marca(d)
            medidos = d.loc[cat.isin([CUANTIFICADO, SIN_MARCA]), c.VALOR]
            n_det = int(est.isin(DETERMINADOS).sum())
            n_exc = int((est == EXCEDE).sum())
            n_ind = int((est == INDETERMINADO).sum())
            fila.update({
                "Muestras": len(d), "Determinadas": n_det, "Excedencias": n_exc,
                "% excedencia": 100 * n_exc / n_det if n_det else np.nan, "Indeterminadas": n_ind,
                "Máx. medido": medidos.max() if not medidos.empty else np.nan,
                "Última muestra": d[c.FECHA].max(),
                "Estado": EXCEDE if n_exc else CUMPLE if n_det else INDETERMINADO if n_ind else NO_EVALUABLE,
            })
        filas.append(fila)
    return pd.DataFrame(filas)
