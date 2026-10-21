"""Curva de duración de caudales y percentiles de disponibilidad."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CurvaDuracion:
    """tabla: probabilidad de excedencia [%] (Weibull, m/(n+1)) vs caudal [m³/s], de mayor a menor.

    q50 / q85: caudal excedido el 50 % / 85 % del tiempo [m³/s]; n_ceros: registros con Q <= 0.
    """

    tabla: pd.DataFrame
    n_ceros: int
    q50: float
    q85: float


def curva_duracion(caudales: pd.Series) -> CurvaDuracion:
    """Curva de duración a partir de caudales diarios [m³/s].

    ADVERTENCIA (hallazgo #20): Q50/Q85 se obtienen con `np.percentile` (interpolación lineal),
    no con la posición de Weibull que usa la curva graficada.
    """
    q = caudales.dropna().sort_values(ascending=False).reset_index(drop=True)
    excedencia = 100.0 * (q.index + 1) / (len(q) + 1)
    tabla = pd.DataFrame({"Probabilidad de Excedencia (%)": excedencia, "Caudal (m3/s)": q})
    return CurvaDuracion(
        tabla=tabla,
        n_ceros=int((q <= 0).sum()),
        q50=float(np.percentile(q, 50)),   # excedido el 50% del tiempo
        q85=float(np.percentile(q, 15)),   # excedido el 85% del tiempo
    )
