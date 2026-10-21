"""Parámetros de cuenca para HEC-HMS: tiempo de concentración, CN ponderado SCS, S, Ia y lag."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

COL_CN = "CN_Teórico"
COL_AREA = "%_Área"
PENDIENTE_ALERTA = 0.5        # m/m; sobre este valor se sospecha error de unidades
FACTOR_DISPERSION_TC = 3      # razón tc_max / tc_min que gatilla advertencia


@dataclass(frozen=True)
class GeometriaCauce:
    """Pendiente media del cauce [m/m] y desnivel Hmax − Hmin [m]."""

    pendiente: float
    desnivel_m: float


def geometria_desde_pendiente(longitud_km: float, pendiente: float) -> GeometriaCauce:
    return GeometriaCauce(pendiente=pendiente, desnivel_m=pendiente * longitud_km * 1000)


def geometria_desde_desnivel(longitud_km: float, desnivel_m: float) -> GeometriaCauce:
    return GeometriaCauce(pendiente=desnivel_m / (longitud_km * 1000), desnivel_m=desnivel_m)


def tc_kirpich(longitud_km: float, pendiente: float) -> float:
    """Kirpich [h]: tc = 0.0663·L^0.77 / S^0.385, L [km], S [m/m]."""
    return 0.0663 * longitud_km ** 0.77 / pendiente ** 0.385


def tc_california(longitud_km: float, desnivel_m: float) -> float:
    """California (Culverts Practice) [h]: tc = (0.87·L³ / H)^0.385, L [km], H [m]."""
    return (0.87 * longitud_km ** 3 / desnivel_m) ** 0.385


def tc_giandotti(area_km2: float, longitud_km: float, h_media_sobre_salida_m: float) -> float:
    """Giandotti [h]: tc = (4·√A + 1.5·L) / (0.8·√H), A [km²], L [km].

    H [m] es la altitud media de la cuenca menos la cota de la salida, no el desnivel del cauce
    (hallazgo #3). Ver `altura_media_sobre_salida`.
    """
    return (4 * np.sqrt(area_km2) + 1.5 * longitud_km) / (0.8 * np.sqrt(h_media_sobre_salida_m))


def altura_media_sobre_salida(altitud_media_m: float, cota_salida_m: float) -> float:
    """H de Giandotti [m] = altitud media de la cuenca [m s.n.m.] − cota de la salida [m s.n.m.]."""
    h = altitud_media_m - cota_salida_m
    if h <= 0:
        raise ValueError("La altitud media de la cuenca debe ser mayor que la cota de la salida.")
    return h


@dataclass(frozen=True)
class TiemposConcentracion:
    """Tiempos de concentración [h] por fórmula; giandotti es None si falta H."""

    kirpich: float
    california: float
    giandotti: float | None

    def como_array(self) -> np.ndarray:
        """Tiempos disponibles (omite Giandotti si no se calculó)."""
        return np.array([t for t in (self.kirpich, self.california, self.giandotti) if t is not None])

    def dispersion_excesiva(self, factor: float = FACTOR_DISPERSION_TC) -> bool:
        tcs = self.como_array()
        return bool(tcs.max() / tcs.min() > factor)


def tiempos_concentracion(area_km2: float, longitud_km: float, geom: GeometriaCauce,
                          h_giandotti_m: float | None) -> TiemposConcentracion:
    """Kirpich y California con la geometría del cauce; Giandotti con H = altitud media − cota de salida [m].

    `h_giandotti_m=None` omite Giandotti. `h_giandotti_m=geom.desnivel_m` reproduce el dashboard
    original (hallazgo #3).
    """
    return TiemposConcentracion(
        kirpich=tc_kirpich(longitud_km, geom.pendiente),
        california=tc_california(longitud_km, geom.desnivel_m),
        giandotti=None if h_giandotti_m is None else tc_giandotti(area_km2, longitud_km, h_giandotti_m),
    )


def lag_scs(tc_horas: float) -> float:
    """Tiempo de retardo SCS [h]: t_lag = 0.6·tc."""
    return 0.6 * tc_horas


def validar_tabla_cn(df_cn: pd.DataFrame) -> list[str]:
    """Devuelve la lista de errores de la tabla de coberturas (vacía si es válida)."""
    errores = []
    if df_cn[[COL_CN, COL_AREA]].isna().any().any():
        errores.append("Hay celdas vacías en CN o % de área.")
    cn = pd.to_numeric(df_cn[COL_CN], errors="coerce")
    area = pd.to_numeric(df_cn[COL_AREA], errors="coerce")
    if ((cn < 30) | (cn > 100)).any():
        errores.append("Los valores de CN deben estar entre 30 y 100.")
    if (area < 0).any():
        errores.append("Los porcentajes de área no pueden ser negativos.")
    if abs(area.sum() - 100.0) > 0.1:
        errores.append(f"La suma de las áreas debe ser 100%. Suma actual: {area.sum():.1f}%")
    return errores


def cn_ponderado(df_cn: pd.DataFrame) -> float:
    """CN ponderado por área (AMC II): Σ CN_i·%A_i / 100."""
    return float((df_cn[COL_CN] * df_cn[COL_AREA] / 100).sum())


@dataclass(frozen=True)
class RetencionSCS:
    """Retención máxima potencial S [mm] y abstracción inicial Ia = 0.2·S [mm]."""

    s_ret: float
    ia: float


def retencion_scs(cn: float) -> RetencionSCS:
    """S = 25400/CN − 254 [mm]; Ia = 0.2·S [mm]."""
    s_ret = 25400 / cn - 254
    return RetencionSCS(s_ret=s_ret, ia=0.2 * s_ret)


def ficha_hec_hms(area_km2: float, ia_mm: float, cn: float, t_lag_horas: float) -> pd.DataFrame:
    """Ficha de subcuenca para HEC-HMS (lag en minutos, impermeable 0 % integrado en el CN)."""
    return pd.DataFrame({
        "Parámetro HEC-HMS": ["Area (KM2)", "Initial Abstraction (MM)", "Curve Number", "Impervious (%)", "Lag Time (MIN)"],
        "Valor a Ingresar": [round(area_km2, 2), round(ia_mm, 2), round(cn, 1), 0.0, round(t_lag_horas * 60, 1)],
    })
