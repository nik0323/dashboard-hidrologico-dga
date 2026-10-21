"""Análisis de frecuencia de máximos anuales: Gumbel, Log-Pearson III y Log-Normal con prueba KS."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import gumbel_r, kstest, lognorm, pearson3, skew

T_OBJETIVO_DEFECTO = np.array([2, 5, 10, 25, 50, 100, 200, 500])
N_MIN_AJUSTE_DEFECTO = 3
T_COLA_DEFECTO = (50, 500)
CRECIMIENTO_MIN_COLA_DEFECTO = 0.05


@dataclass(frozen=True)
class ResultadoAjuste:
    """Resultado del ajuste de distribuciones.

    n: años usados (PMA > 0); n_ceros: años excluidos por PMA = 0.
    x_sorted: máximos ordenados de mayor a menor (unidades de la serie, p. ej. mm).
    t_empirico: periodo de retorno empírico de Weibull, T = (n+1)/m [años].
    cuantiles: {distribución: {T [años]: valor}}.
    curvas: {distribución: valores teóricos evaluados en t_empirico}.
    ks: tabla Kolmogorov-Smirnov ordenada por estadístico D; mejor: distribución con menor D.
    lp3_cota_superior: cota superior de LP-III [unidades de la serie] si la asimetría de log10
    es negativa: 10^(μ − 2σ/g); infinito si g >= 0.
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
    lp3_cota_superior: float


def ajustar_distribuciones(serie_maximos: npt.ArrayLike,
                           t_objetivo: npt.ArrayLike = T_OBJETIVO_DEFECTO,
                           n_min: int = N_MIN_AJUSTE_DEFECTO) -> ResultadoAjuste | None:
    """Ajusta Gumbel (momentos), Log-Pearson III (momentos de log10) y Log-Normal (MV, loc = 0).

    Se descartan valores no finitos y <= 0 (los modelos logarítmicos no admiten ceros).
    Devuelve None si quedan menos de `n_min` valores.

    ADVERTENCIA (hallazgos #9 y #10): D crítico asintótico 1.36/√n (α = 0.05) con parámetros
    estimados de la misma muestra; asimetría de LP-III sin ponderación regional (ver
    `diagnosticar_cola` para detectar techos); Gumbel con factores asintóticos.
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
    cota_lp3 = float(10 ** (mean_log - 2 * std_log / skew_log)) if skew_log < 0 else np.inf
    return ResultadoAjuste(
        n=n, n_ceros=n_ceros, x_sorted=x_sorted, t_empirico=t_empirico, cuantiles=cuantiles,
        curvas=curvas, ks=df_ks, mejor=df_ks.loc[0, "Distribución"], t_objetivo=t_objetivo,
        lp3_cota_superior=cota_lp3,
    )


@dataclass(frozen=True)
class DiagnosticoCola:
    """Crecimiento relativo [-] del cuantil entre T_inf y T_sup; con_techo si es < al mínimo o no finito."""

    crecimiento: float
    con_techo: bool


def diagnosticar_cola(ajuste: ResultadoAjuste, t_cola: tuple[int, int] = T_COLA_DEFECTO,
                      crecimiento_min: float = CRECIMIENTO_MIN_COLA_DEFECTO) -> dict[str, DiagnosticoCola]:
    """Detecta distribuciones cuyos cuantiles casi no crecen con T (hallazgo #10).

    Crecimiento = x(T_sup) / x(T_inf) − 1. Un valor < `crecimiento_min` (5 % entre T = 50 y 500
    años, por defecto) indica una cota superior que domina la cola, típico de LP-III con
    asimetría negativa fuerte y pocos años.

    LIMITACIÓN: en series con CV muy bajo (≈ 5 %) todas las distribuciones crecen poco y pueden
    marcarse aunque no tengan cota; en PMA chilenas típicas (CV 20-40 %) no ocurre.
    """
    t_inf, t_sup = t_cola
    diagnostico = {}
    for dist, q in ajuste.cuantiles.items():
        a, b = q[t_inf], q[t_sup]
        crecimiento = b / a - 1 if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan
        diagnostico[dist] = DiagnosticoCola(
            crecimiento=float(crecimiento),
            con_techo=bool(not np.isfinite(crecimiento) or crecimiento < crecimiento_min),
        )
    return diagnostico


def distribucion_recomendada(ajuste: ResultadoAjuste, diagnostico: dict[str, DiagnosticoCola]) -> str:
    """Distribución de menor D de KS sin techo; si todas tienen techo, la de menor D."""
    for dist in ajuste.ks["Distribución"]:
        if not diagnostico[dist].con_techo:
            return dist
    return ajuste.mejor


def tabla_cuantiles(ajuste: ResultadoAjuste) -> pd.DataFrame:
    """Tabla de cuantiles de diseño [mm] por periodo de retorno T [años], redondeada a 2 decimales."""
    return pd.DataFrame({
        "Periodo de Retorno T (Años)": ajuste.t_objetivo,
        "Probabilidad Excedencia (%)": np.round(100 / ajuste.t_objetivo, 1),
        **{f"{d} (mm)": np.round(list(ajuste.cuantiles[d].values()), 2) for d in ajuste.cuantiles},
    })
