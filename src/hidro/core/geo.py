"""Conversión de coordenadas DGA y distancias geodésicas."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

RADIO_TIERRA_KM = 6371


def dms_a_decimal(dms_val: object) -> float:
    """Convierte coordenadas DGA (DMS concatenado, ej. 343810 = 34°38'10'') a grados decimales.

    El signo es siempre negativo (hemisferio sur / oeste). Si el valor ya parece estar en
    grados decimales (|v| <= 180 con parte fraccionaria) se respeta. Devuelve NaN si el valor
    no es interpretable o tiene minutos/segundos fuera de rango.

    ADVERTENCIA (hallazgo #13): un decimal entero como -34.0 se interpreta como DMS
    (0°0'34''), y no se valida latitud <= 90°.
    """
    try:
        v = float(dms_val)
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(v):
        return np.nan

    # Coordenada ya en grados decimales
    if abs(v) <= 180 and v != int(v):
        return -abs(v)

    val_str = str(abs(int(v))).zfill(6)
    s = float(val_str[-2:])
    m = float(val_str[-4:-2])
    d = float(val_str[:-4])
    if m >= 60 or s >= 60 or d > 180:
        return np.nan
    return -(d + m / 60.0 + s / 3600.0)


def haversine_vectorizado(lat_ref: float, lon_ref: float, lat: npt.ArrayLike, lon: npt.ArrayLike):
    """Distancia geodésica (Haversine, R = 6371 km) en km desde (lat_ref, lon_ref) [°] a (lat, lon) [°].

    Acepta escalares, arreglos o Series y conserva el tipo de entrada.
    """
    lat1, lon1, lat2, lon2 = map(np.radians, [lat_ref, lon_ref, lat, lon])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return RADIO_TIERRA_KM * 2 * np.arcsin(np.sqrt(a))
