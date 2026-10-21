"""Hallazgos #9 (KS exacto + bootstrap paramétrico) y #10b (LP-III con asimetría ponderada, Bulletin 17B)."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import kstest, lognorm, skew

from casos import SERIES_PMA, api_original
from hidro.config import cargar_settings
from hidro.core import frecuencia as fr

GUMBEL_30 = SERIES_PMA["gumbel_30"](np.random.default_rng(2))


# ---------------------------------------------------------------- #9
@pytest.mark.parametrize("n, tabla", [(10, 0.40925), (20, 0.29408)])   # tabla clásica de Kolmogorov, α = 0.05
def test_d_critico_exacto(n, tabla):
    aj = fr.ajustar_distribuciones(np.arange(1.0, n + 1), n_bootstrap=0)
    assert aj.ks["D crítico exacto (α=0.05)"].iloc[0] == pytest.approx(tabla, abs=1e-4)


def test_cuantiles_y_d_iguales_al_original():
    """El cambio de #9 solo agrega columnas a la tabla KS: cuantiles, curvas y D no cambian."""
    o = api_original().ajustar_distribuciones(GUMBEL_30)
    h = fr.ajustar_distribuciones(GUMBEL_30)
    assert list(h.cuantiles) == list(o["cuantiles"])
    for d in o["cuantiles"]:
        assert h.cuantiles[d] == pytest.approx(o["cuantiles"][d], abs=1e-9)
        np.testing.assert_allclose(h.curvas[d], o["curvas"][d], rtol=0, atol=1e-9)
    pd.testing.assert_series_equal(h.ks.set_index("Distribución")["Estadístico D"],
                                   o["ks"].set_index("Distribución")["Estadístico D"])
    assert h.mejor == o["mejor"]


def test_bootstrap_reproducible_y_en_rango():
    a = fr.ajustar_distribuciones(GUMBEL_30, semilla=7)
    b = fr.ajustar_distribuciones(GUMBEL_30, semilla=7)
    pd.testing.assert_frame_equal(a.ks, b.ks)
    p = a.ks["p-valor bootstrap"]
    assert ((p > 0) & (p <= 1)).all()
    assert (a.ks["Resultado"] == np.where(p >= 0.05, "Aceptada", "Rechazada")).all()


def test_bootstrap_corrige_sesgo_por_estimar_parametros():
    """Muestra uniforme (n = 60): la KS clásica, que supone parámetros conocidos, acepta Gumbel
    (p ≈ 0.13); el bootstrap paramétrico la rechaza (p ≈ 0.006)."""
    x = np.random.default_rng(0).uniform(20, 80, 60)
    ks = fr.ajustar_distribuciones(x).ks.set_index("Distribución")
    assert ks.loc["Gumbel", "p-valor KS (parámetros conocidos)"] > 0.05
    assert ks.loc["Gumbel", "p-valor bootstrap"] < 0.05
    assert ks.loc["Gumbel", "Resultado"] == "Rechazada"


def test_bootstrap_menos_permisivo_que_ks_clasica():
    """Con parámetros estimados, la KS clásica sobrestima el p-valor; el bootstrap lo corrige."""
    for semilla in range(3):
        for x in (np.random.default_rng(semilla).normal(50, 10, 60), SERIES_PMA["gumbel_30"](np.random.default_rng(semilla))):
            ks = fr.ajustar_distribuciones(x).ks
            assert (ks["p-valor bootstrap"] <= ks["p-valor KS (parámetros conocidos)"] + 0.01).all()


def test_bootstrap_lognormal_refit_igual_a_scipy():
    """El reajuste vectorizado (MV analítico) coincide con lognorm.fit(floc=0), usado en el ajuste observado."""
    x = SERIES_PMA["lognormal_50"](np.random.default_rng(2))
    forma, _, escala = lognorm.fit(x, floc=0)
    lx = np.log(x)
    assert (forma, escala) == pytest.approx((lx.std(), np.exp(lx.mean())), rel=1e-12)


def test_d_vectorizado_igual_a_kstest():
    from hidro.core.frecuencia import _d_ks_filas
    from scipy.stats import gumbel_r
    s = np.sort(GUMBEL_30)[None, :]
    d = _d_ks_filas(s, gumbel_r.cdf(s, loc=40, scale=15))[0]
    assert d == pytest.approx(kstest(GUMBEL_30, "gumbel_r", args=(40, 15)).statistic, abs=1e-12)


def test_sin_bootstrap_resultado_por_d_critico():
    ks = fr.ajustar_distribuciones(GUMBEL_30, n_bootstrap=0).ks
    assert ks["p-valor bootstrap"].isna().all()
    assert (ks["Resultado"] == np.where(ks["Estadístico D"] < ks["D crítico exacto (α=0.05)"],
                                        "Aceptada", "Rechazada")).all()


# ---------------------------------------------------------------- #10b
def test_mse_17b():
    # G = 0: A = −0.33, B = 0.94 → MSE(n=10) = 10^−0.33; MSE(n=100) = 10^−1.27
    assert fr.mse_asimetria_17b(0.0, 10) == pytest.approx(10 ** -0.33)
    assert fr.mse_asimetria_17b(0.0, 100) == pytest.approx(10 ** -1.27)
    # |G| = 1.2: A = 0.52 + 0.36 = 0.88, B = 0.94 − 0.312 = 0.628
    assert fr.mse_asimetria_17b(-1.2, 40) == pytest.approx(10 ** (0.88 - 0.628 * np.log10(4)))
    # |G| = 2: B = 0.55
    assert fr.mse_asimetria_17b(2.0, 20) == pytest.approx(10 ** (1.12 - 0.55 * np.log10(2)))


def _series_regionales():
    rng = np.random.default_rng(3)
    return {f"E{i}": rng.lognormal(4.5, 0.35, 30 + 5 * i) for i in range(4)} | {"CORTA": rng.lognormal(4, 0.3, 10)}


def test_asimetria_regional_y_ponderada():
    series = _series_regionales()
    reg = fr.asimetria_regional(series, excluir="E0", n_min_anios=25, min_estaciones=3)
    assert reg.estaciones == ("E1", "E2", "E3")                       # sin la evaluada ni la corta
    gs = [skew(np.log10(series[e]), bias=False) for e in reg.estaciones]
    assert reg.g == pytest.approx(np.mean(gs)) and reg.mse == pytest.approx(np.var(gs, ddof=1))
    g, n = -1.5, 8
    gw = fr.asimetria_ponderada(g, n, reg)
    mse_g = fr.mse_asimetria_17b(g, n)
    assert gw == pytest.approx((reg.mse * g + mse_g * reg.g) / (reg.mse + mse_g))
    assert min(g, reg.g) <= gw <= max(g, reg.g)
    assert fr.asimetria_regional(series, excluir="E0", n_min_anios=25, min_estaciones=4) is None


def test_ajuste_con_regional_agrega_lp3_ponderada():
    reg = fr.asimetria_regional(_series_regionales(), n_min_anios=25)
    x = np.array([70.0, 69.0, 68.0, 66.0, 40.0])          # serie corta con techo en LP-III (hallazgo #10)
    sin = fr.ajustar_distribuciones(x)
    con = fr.ajustar_distribuciones(x, regional=reg)
    assert fr.LP3_PONDERADA not in sin.cuantiles and fr.LP3_PONDERADA in con.cuantiles
    for d in sin.cuantiles:                                 # las otras tres no cambian
        assert con.cuantiles[d] == sin.cuantiles[d]
    assert con.asimetria_ponderada == pytest.approx(float(fr.asimetria_ponderada(con.asimetria_log, 5, reg)))
    # con n = 5 la ponderación acerca G a la regional y suaviza el techo de LP-III
    diag = fr.diagnosticar_cola(con)
    assert diag[fr.LP3].con_techo and not diag[fr.LP3_PONDERADA].con_techo


def test_configuracion():
    s = cargar_settings()
    assert (s.alfa_ks, s.n_bootstrap, s.semilla_bootstrap) == (0.05, 1000, 20261021)
    assert (s.regional_usar, s.regional_n_min_anios, s.regional_min_estaciones) == (True, 25, 3)
