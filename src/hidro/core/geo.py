"""Conversión de coordenadas DGA y distancias geodésicas."""

from __future__ import annotations

from typing import Literal

import numpy as np
import numpy.typing as npt

RADIO_TIERRA_KM = 6371


def dms_a_decimal(dms_val: object, tipo: Literal["lat", "lon"] | None = None) -> float:
    """Convierte coordenadas DGA (DMS concatenado, ej. 343810 = 34°38'10'') a grados decimales.

    El signo es siempre negativo (hemisferio sur / oeste). Si |v| <= 180 el valor se toma como
    grados decimales: un DMS con al menos 1° tiene 5 dígitos o más (10000), y un DMS menor
    que 180 (menos de 2') no es una coordenada plausible (hallazgo #13). Devuelve NaN si el
    valor no es interpretable, es 0 (coordenada faltante), tiene minutos/segundos fuera de
    rango o, con `tipo="lat"`, supera 90°.
    """
    try:
        v = float(dms_val)
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(v) or v == 0:
        return np.nan

    if abs(v) <= 180:
        # Coordenada ya en grados decimales (con o sin parte fraccionaria)
        decimal = -abs(v)
    else:
        val_str = str(abs(int(v))).zfill(6)
        s = float(val_str[-2:])
        m = float(val_str[-4:-2])
        d = float(val_str[:-4])
        if m >= 60 or s >= 60 or d > 180:
            return np.nan
        decimal = -(d + m / 60.0 + s / 3600.0)

    if tipo == "lat" and abs(decimal) > 90:
        return np.nan
    return decimal


def haversine_vectorizado(lat_ref: float, lon_ref: float, lat: npt.ArrayLike, lon: npt.ArrayLike):
    """Distancia geodésica (Haversine, R = 6371 km) en km desde (lat_ref, lon_ref) [°] a (lat, lon) [°].

    Acepta escalares, arreglos o Series y conserva el tipo de entrada.
    """
    lat1, lon1, lat2, lon2 = map(np.radians, [lat_ref, lon_ref, lat, lon])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return RADIO_TIERRA_KM * 2 * np.arcsin(np.sqrt(a))
