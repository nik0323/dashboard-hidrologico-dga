"""Análisis de frecuencia de máximos anuales: Gumbel, Log-Pearson III y Log-Normal con prueba KS."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import gumbel_r, kstest, lognorm, pearson3, skew

T_OBJETIVO_DEFECTO = np.array([2, 5, 10, 25, 50, 100, 200, 500])
N_MIN_AJUSTE_DEFECTO = 3


@dataclass(frozen=True)
class ResultadoAjuste:
    """Resultado del ajuste de distribuciones.

    n: años usados (PMA > 0); n_ceros: años excluidos por PMA = 0.
    x_sorted: máximos ordenados de mayor a menor (unidades de la serie, p. ej. mm).
    t_empirico: periodo de retorno empírico de Weibull, T = (n+1)/m [años].
    cuantiles: {distribución: {T [años]: valor}}.
    curvas: {distribución: valores teóricos evaluados en t_empirico}.
    ks: tabla Kolmogorov-Smirnov ordenada por estadístico D; mejor: distribución con menor D.
    """

    n: int
    n_ceros: int
    x_sorted: np.ndarray
    t_empirico: np.ndarray
    cuantiles: dict[str, dict[int, float]]
    curvas: dict[str, np.ndarray]
    ks: pd.DataFrame
    mejor: str
    t_objetivo: np.ndarray


def ajustar_distribuciones(serie_maximos: npt.ArrayLike,
                           t_objetivo: npt.ArrayLike = T_OBJETIVO_DEFECTO,
                           n_min: int = N_MIN_AJUSTE_DEFECTO) -> ResultadoAjuste | None:
    """Ajusta Gumbel (momentos), Log-Pearson III (momentos de log10) y Log-Normal (MV, loc = 0).

    Se descartan valores no finitos y <= 0 (los modelos logarítmicos no admiten ceros).
    Devuelve None si quedan menos de `n_min` valores.

    ADVERTENCIA (hallazgos #9 y #10): D crítico asintótico 1.36/√n (α = 0.05) con parámetros
    estimados de la misma muestra; asimetría de LP-III sin ponderación regional; Gumbel con
    factores asintóticos.
    """
    t_objetivo = np.asarray(t_objetivo)
    x = np.asarray(serie_maximos, dtype=float)
    x = x[np.isfinite(x)]
    n_ceros = int((x <= 0).sum())
    x = x[x > 0]
    n = len(x)
    if n < n_min:
        return None

    # Posición de graficación de Weibull
    x_sorted = np.sort(x)[::-1]
    t_empirico = (n + 1) / np.arange(1, n + 1)
    p_emp = 1 - 1 / t_empirico
    p_obj = 1 - 1 / t_objetivo

    # Gumbel (método de momentos)
    media, desv = np.mean(x), np.std(x, ddof=1)
    alpha_g = desv * np.sqrt(6) / np.pi
    u_g = media - 0.5772 * alpha_g

    # Log-Pearson III (momentos de log10)
    log_x = np.log10(x)
    mean_log, std_log = np.mean(log_x), np.std(log_x, ddof=1)
    skew_log = float(skew(log_x, bias=False)) if n > 2 else 0.0

    # Log-Normal (máxima verosimilitud, loc = 0)
    shape_ln, loc_ln, scale_ln = lognorm.fit(x, floc=0)

    modelos = {
        "Gumbel": {
            "ppf": lambda p: gumbel_r.ppf(p, loc=u_g, scale=alpha_g),
            "ks": kstest(x, "gumbel_r", args=(u_g, alpha_g)),
        },
        "Log-Pearson III": {
            "ppf": lambda p: 10 ** pearson3.ppf(p, skew_log, loc=mean_log, scale=std_log),
            "ks": kstest(log_x, "pearson3", args=(skew_log, mean_log, std_log)),
        },
        "Log-Normal": {
            "ppf": lambda p: lognorm.ppf(p, shape_ln, loc=loc_ln, scale=scale_ln),
            "ks": kstest(x, "lognorm", args=(shape_ln, loc_ln, scale_ln)),
        },
    }

    d_critico = 1.36 / np.sqrt(n)  # aproximación α = 0.05
    cuantiles, curvas, filas_ks = {}, {}, []
    for nombre, mod in modelos.items():
        valores = mod["ppf"](p_obj)
        cuantiles[nombre] = {int(t): float(v) for t, v in zip(t_objetivo, valores)}
        curvas[nombre] = mod["ppf"](p_emp)
        d_stat, p_val = mod["ks"].statistic, mod["ks"].pvalue
        filas_ks.append({
            "Distribución": nombre,
            "Estadístico D": round(float(d_stat), 4),
            "D crítico (α=0.05)": round(float(d_critico), 4),
            "p-valor": round(float(p_val), 4),
            "Resultado": "Aceptada" if d_stat < d_critico else "Rechazada",
        })

    df_ks = pd.DataFrame(filas_ks).sort_values("Estadístico D").reset_index(drop=True)
    return ResultadoAjuste(
        n=n, n_ceros=n_ceros, x_sorted=x_sorted, t_empirico=t_empirico, cuantiles=cuantiles,
        curvas=curvas, ks=df_ks, mejor=df_ks.loc[0, "Distribución"], t_objetivo=t_objetivo,
    )


def tabla_cuantiles(ajuste: ResultadoAjuste) -> pd.DataFrame:
    """Tabla de cuantiles de diseño [mm] por periodo de retorno T [años], redondeada a 2 decimales."""
    return pd.DataFrame({
        "Periodo de Retorno T (Años)": ajuste.t_objetivo,
        "Probabilidad Excedencia (%)": np.round(100 / ajuste.t_objetivo, 1),
        **{f"{d} (mm)": np.round(list(ajuste.cuantiles[d].values()), 2) for d in ajuste.cuantiles},
    })
