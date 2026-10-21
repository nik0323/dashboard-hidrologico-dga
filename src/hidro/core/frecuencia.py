"""Análisis de frecuencia de máximos anuales: Gumbel, Log-Pearson III y Log-Normal con prueba KS.

Bondad de ajuste (hallazgo #9): D crítico exacto de Kolmogorov para n finito (referencial: supone
parámetros conocidos) y p-valor por bootstrap paramétrico (tipo Lilliefors: se simulan muestras de
la distribución ajustada, se reajusta con el mismo método y se recalcula D), que decide el resultado.
LP-III ponderada (hallazgo #10b): asimetría de la estación ponderada con una asimetría regional según
el Bulletin 17B (IACWD, 1982).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import gumbel_r, kstest, kstwo, lognorm, pearson3, skew

T_OBJETIVO_DEFECTO = np.array([2, 5, 10, 25, 50, 100, 200, 500])
N_MIN_AJUSTE_DEFECTO = 3
T_COLA_DEFECTO = (50, 500)
CRECIMIENTO_MIN_COLA_DEFECTO = 0.05
ALFA_KS_DEFECTO = 0.05
N_BOOTSTRAP_DEFECTO = 1000
SEMILLA_BOOTSTRAP_DEFECTO = 20261021

LP3 = "Log-Pearson III"
LP3_PONDERADA = "Log-Pearson III (ponderada)"


# ---------------------------------------------------------------- asimetría regional (17B)
@dataclass(frozen=True)
class AsimetriaRegional:
    """Asimetría regional de log10 de la PMA [-] y su error cuadrático medio [-]."""

    g: float
    mse: float
    estaciones: tuple[str, ...]
    asimetrias: tuple[float, ...]
    n_anios: tuple[int, ...]


def mse_asimetria_17b(g: npt.ArrayLike, n: int) -> np.ndarray:
    """MSE de la asimetría muestral de log10 (Bulletin 17B, ec. 6): 10^(A − B·log10(n/10)).

    A = −0.33 + 0.08|G| si |G| <= 0.90, si no 0.52 + 0.30|G|; B = 0.94 − 0.26|G| si |G| <= 1.50, si no 0.55.
    """
    g = np.abs(np.asarray(g, dtype=float))
    a = np.where(g <= 0.90, -0.33 + 0.08 * g, 0.52 + 0.30 * g)
    b = np.where(g <= 1.50, 0.94 - 0.26 * g, 0.55)
    return 10 ** (a - b * np.log10(n / 10))


def asimetria_ponderada(g: npt.ArrayLike, n: int, regional: AsimetriaRegional) -> np.ndarray:
    """G_w = (MSE_reg·G + MSE_G·G_reg) / (MSE_reg + MSE_G)  (Bulletin 17B, ec. 5)."""
    g = np.asarray(g, dtype=float)
    mse_g = mse_asimetria_17b(g, n)
    return (regional.mse * g + mse_g * regional.g) / (regional.mse + mse_g)


def asimetria_regional(series_maximos: Mapping[str, npt.ArrayLike], excluir: str | None = None,
                       n_min_anios: int = 25, min_estaciones: int = 3) -> AsimetriaRegional | None:
    """Asimetría regional como promedio de las asimetrías de log10 (insesgadas) de las estaciones con
    al menos `n_min_anios` máximos > 0, excluida la estación evaluada.

    [SUPUESTO: sin mapa regional oficial para Chile, la región son las estaciones vecinas dentro del
    radio de búsqueda; el MSE regional se estima con la varianza muestral entre estaciones, que
    incluye su error de muestreo y es por lo tanto conservadora.]
    Devuelve None si hay menos de `min_estaciones` estaciones válidas.
    """
    nombres, gs, ns = [], [], []
    for nombre, x in series_maximos.items():
        if nombre == excluir:
            continue
        x = np.asarray(x, dtype=float)
        x = x[np.isfinite(x) & (x > 0)]
        if len(x) >= n_min_anios:
            nombres.append(nombre)
            gs.append(float(skew(np.log10(x), bias=False)))
            ns.append(len(x))
    if len(gs) < min_estaciones:
        return None
    return AsimetriaRegional(g=float(np.mean(gs)), mse=float(np.var(gs, ddof=1)), estaciones=tuple(nombres),
                             asimetrias=tuple(gs), n_anios=tuple(ns))


# ---------------------------------------------------------------- bootstrap paramétrico (KS)
def _asimetria_filas(a: np.ndarray) -> np.ndarray:
    """Asimetría insesgada por fila (igual a scipy.stats.skew(bias=False, axis=1))."""
    n = a.shape[1]
    d = a - a.mean(axis=1, keepdims=True)
    return np.sqrt(n * (n - 1)) / (n - 2) * (d ** 3).mean(axis=1) / (d ** 2).mean(axis=1) ** 1.5


def _d_ks_filas(ordenadas: np.ndarray, cdf: np.ndarray) -> np.ndarray:
    """Estadístico D de KS por fila, con las muestras ordenadas de menor a mayor."""
    n = ordenadas.shape[1]
    i = np.arange(1, n + 1)
    return np.maximum((i / n - cdf).max(axis=1), (cdf - (i - 1) / n).max(axis=1))


def _boot_gumbel(rng, n, b, loc, escala):
    s = np.sort(gumbel_r.rvs(loc=loc, scale=escala, size=(b, n), random_state=rng), axis=1)
    a = s.std(axis=1, ddof=1) * np.sqrt(6) / np.pi
    u = s.mean(axis=1) - 0.5772 * a
    return _d_ks_filas(s, gumbel_r.cdf(s, loc=u[:, None], scale=a[:, None]))


def _boot_lognormal(rng, n, b, forma, escala):
    s = np.sort(lognorm.rvs(forma, loc=0, scale=escala, size=(b, n), random_state=rng), axis=1)
    ls = np.log(s)   # MV con loc = 0: forma = σ(ln x, ddof=0), escala = exp(μ(ln x)), igual a lognorm.fit(floc=0)
    return _d_ks_filas(s, lognorm.cdf(s, ls.std(axis=1)[:, None], loc=0, scale=np.exp(ls.mean(axis=1))[:, None]))


def _boot_lp3(rng, n, b, g, media, desv, regional):
    y = np.sort(pearson3.rvs(g, loc=media, scale=desv, size=(b, n), random_state=rng), axis=1)
    g_b = _asimetria_filas(y)
    if regional is not None:
        g_b = asimetria_ponderada(g_b, n, regional)
    cdf = pearson3.cdf(y, g_b[:, None], loc=y.mean(axis=1)[:, None], scale=y.std(axis=1, ddof=1)[:, None])
    return _d_ks_filas(y, cdf)


def p_valor_bootstrap(d_obs: float, simular_d: Callable[[np.random.Generator], np.ndarray],
                      semilla: int) -> float:
    """p = (1 + #{D* >= D_obs}) / (B + 1), con D* simulados bajo la distribución ajustada."""
    d_sim = simular_d(np.random.default_rng(semilla))
    return float((1 + np.sum(d_sim >= d_obs)) / (len(d_sim) + 1))


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
    asimetria_log: asimetría muestral de log10 [-]; asimetria_ponderada: G_w (None sin regional).
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
    asimetria_log: float
    asimetria_ponderada: float | None


def ajustar_distribuciones(serie_maximos: npt.ArrayLike,
                           t_objetivo: npt.ArrayLike = T_OBJETIVO_DEFECTO,
                           n_min: int = N_MIN_AJUSTE_DEFECTO,
                           regional: AsimetriaRegional | None = None,
                           n_bootstrap: int = N_BOOTSTRAP_DEFECTO,
                           semilla: int = SEMILLA_BOOTSTRAP_DEFECTO,
                           alfa: float = ALFA_KS_DEFECTO) -> ResultadoAjuste | None:
    """Ajusta Gumbel (momentos), Log-Pearson III (momentos de log10) y Log-Normal (MV, loc = 0);
    con `regional`, además LP-III con asimetría ponderada (Bulletin 17B).

    Se descartan valores no finitos y <= 0 (los modelos logarítmicos no admiten ceros).
    Devuelve None si quedan menos de `n_min` valores.

    Tabla KS: D, D crítico exacto (kstwo, parámetros conocidos), p-valor KS clásico, p-valor
    bootstrap (`n_bootstrap` réplicas, semilla fija) y resultado según el p-valor bootstrap
    (o según el D crítico exacto si `n_bootstrap = 0`).
    ADVERTENCIA: Gumbel usa los factores asintóticos del método de momentos.
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
            "boot": lambda rng: _boot_gumbel(rng, n, n_bootstrap, u_g, alpha_g),
        },
        LP3: {
            "ppf": lambda p: 10 ** pearson3.ppf(p, skew_log, loc=mean_log, scale=std_log),
            "ks": kstest(log_x, "pearson3", args=(skew_log, mean_log, std_log)),
            "boot": lambda rng: _boot_lp3(rng, n, n_bootstrap, skew_log, mean_log, std_log, None),
        },
        "Log-Normal": {
            "ppf": lambda p: lognorm.ppf(p, shape_ln, loc=loc_ln, scale=scale_ln),
            "ks": kstest(x, "lognorm", args=(shape_ln, loc_ln, scale_ln)),
            "boot": lambda rng: _boot_lognormal(rng, n, n_bootstrap, shape_ln, scale_ln),
        },
    }
    g_w = None
    if regional is not None:
        g_w = float(asimetria_ponderada(skew_log, n, regional))
        modelos[LP3_PONDERADA] = {
            "ppf": lambda p: 10 ** pearson3.ppf(p, g_w, loc=mean_log, scale=std_log),
            "ks": kstest(log_x, "pearson3", args=(g_w, mean_log, std_log)),
            "boot": lambda rng: _boot_lp3(rng, n, n_bootstrap, g_w, mean_log, std_log, regional),
        }

    d_critico = float(kstwo.ppf(1 - alfa, n))   # exacto para n finito con parámetros conocidos
    cuantiles, curvas, filas_ks = {}, {}, []
    for i, (nombre, mod) in enumerate(modelos.items()):
        valores = mod["ppf"](p_obj)
        cuantiles[nombre] = {int(t): float(v) for t, v in zip(t_objetivo, valores)}
        curvas[nombre] = mod["ppf"](p_emp)
        d_stat, p_val = float(mod["ks"].statistic), float(mod["ks"].pvalue)
        p_boot = p_valor_bootstrap(d_stat, mod["boot"], semilla + i) if n_bootstrap > 0 else np.nan
        aceptada = p_boot >= alfa if n_bootstrap > 0 else d_stat < d_critico
        filas_ks.append({
            "Distribución": nombre,
            "Estadístico D": round(d_stat, 4),
            f"D crítico exacto (α={alfa:g})": round(d_critico, 4),
            "p-valor KS (parámetros conocidos)": round(p_val, 4),
            "p-valor bootstrap": round(p_boot, 4),
            "Resultado": "Aceptada" if aceptada else "Rechazada",
        })

    df_ks = pd.DataFrame(filas_ks).sort_values("Estadístico D", kind="stable").reset_index(drop=True)
    cota_lp3 = float(10 ** (mean_log - 2 * std_log / skew_log)) if skew_log < 0 else np.inf
    return ResultadoAjuste(
        n=n, n_ceros=n_ceros, x_sorted=x_sorted, t_empirico=t_empirico, cuantiles=cuantiles,
        curvas=curvas, ks=df_ks, mejor=df_ks.loc[0, "Distribución"], t_objetivo=t_objetivo,
        lp3_cota_superior=cota_lp3, asimetria_log=skew_log, asimetria_ponderada=g_w,
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
