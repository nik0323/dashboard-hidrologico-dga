"""Tormenta de diseño: curvas IDF y hietograma por Bloques Alternos."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

FACTOR_INTERVALO_FIJO_DEFECTO = 1.13


def p24_movil(p_diaria_mm: float, factor: float = FACTOR_INTERVALO_FIJO_DEFECTO) -> float:
    """P24 de 24 h móviles [mm] a partir de la precipitación diaria de intervalo fijo [mm].

    La lectura diaria (08-08 h) no captura el máximo de 24 h consecutivas que cruza el horario de
    lectura. Por eso se multiplica por un factor k >= 1. Con k = 1.13 (Weiss, 1964; OMM, Manual on
    Estimation of PMP) se pasa de un intervalo fijo observacional al máximo de 24 h. Con k = 1
    se reproduce el dashboard original.
    """
    return factor * p_diaria_mm


def hietograma_bloques_alternos(p24: float, dt_minutos: float, duracion_total_horas: float = 24,
                                b: float = 0.33) -> tuple[np.ndarray, np.ndarray]:
    """Hietograma de diseño por Bloques Alternos con desagregación potencial P(d) = P24·(d/24)^b.

    p24 [mm], dt_minutos [min], duracion_total_horas [h]. Devuelve (tiempo acumulado [min],
    precipitación incremental [mm]) con el bloque mayor al centro.

    p24 debe ser de 24 h móviles (ver `p24_movil`, hallazgo #7).
    ADVERTENCIA: b = 0.33 es un valor por defecto no calibrado localmente.
    """
    dt_horas = dt_minutos / 60.0
    n_bloques = int(round(duracion_total_horas / dt_horas))
    t_array = np.arange(1, n_bloques + 1) * dt_horas

    p_d = p24 * (t_array / duracion_total_horas) ** b
    delta_p = np.diff(p_d, prepend=0.0)
    delta_p_sorted = np.sort(delta_p)[::-1]

    hietograma = np.zeros(n_bloques)
    centro = (n_bloques - 1) // 2
    hietograma[centro] = delta_p_sorted[0]
    izq, der = centro - 1, centro + 1

    for i in range(1, n_bloques):
        derecha = (i % 2 != 0 and der < n_bloques) or izq < 0
        if derecha:
            hietograma[der] = delta_p_sorted[i]
            der += 1
        else:
            hietograma[izq] = delta_p_sorted[i]
            izq -= 1

    tiempo_array = np.arange(1, n_bloques + 1) * dt_minutos
    return tiempo_array, hietograma


def intensidad_idf(p24: float, duraciones_h: npt.ArrayLike, b: float) -> np.ndarray:
    """Intensidad [mm/h] para duraciones [h]: i(d) = P24·(d/24)^b / d."""
    duraciones_h = np.asarray(duraciones_h)
    return p24 * (duraciones_h / 24.0) ** b / duraciones_h


def tabla_hec_hms(tiempos_min: np.ndarray, hietograma_mm: np.ndarray) -> pd.DataFrame:
    """Serie de tiempo para HEC-HMS: tiempo acumulado [min] y precipitación incremental [mm] (3 decimales)."""
    return pd.DataFrame({"Tiempo Acumulado (minutos)": tiempos_min,
                         "Precipitación Incremental (mm)": np.round(hietograma_mm, 3)})
