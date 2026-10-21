"""Carga y validación de `config/settings.toml`."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_SETTINGS_DEFECTO = RAIZ_PROYECTO / "config" / "settings.toml"
RADIO_MIN_KM = 10


@dataclass(frozen=True)
class PuntoControl:
    """Punto de referencia para distancias: nombre y coordenadas [° decimales]."""

    nombre: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Radio:
    """Slider de radio de búsqueda [km]."""

    defecto: int
    max: int
    paso: int
    min: int = RADIO_MIN_KM


@dataclass(frozen=True)
class Tormenta:
    """Opciones de la tormenta de diseño: T [años], Δt [min] y exponente de desagregación b [-]."""

    t_diseno: tuple[int, ...]
    dt_minutos: tuple[int, ...]
    b_defecto: float
    b_min: float
    b_max: float


@dataclass(frozen=True)
class Settings:
    directorio_datos: Path
    archivos: dict[str, str]
    patron_agromet: str
    punto_control: PuntoControl
    t_objetivo: tuple[int, ...]
    n_min_ajuste: int
    n_recomendado: int
    qa_max_precip_horaria_mm: float
    tormenta: Tormenta
    radios: dict[str, Radio]

    def radio(self, clave: str) -> Radio:
        return self.radios[clave]


def cargar_settings(ruta: str | os.PathLike | None = None) -> Settings:
    """Lee el .toml (por defecto `HIDRO_SETTINGS` o config/settings.toml) y valida sus valores.

    `DGA_DATA_DIR`, si está definida, reemplaza `[datos].directorio`.
    """
    ruta = Path(ruta or os.environ.get("HIDRO_SETTINGS") or RUTA_SETTINGS_DEFECTO)
    with open(ruta, "rb") as fh:
        crudo = tomllib.load(fh)

    datos = crudo["datos"]
    directorio = Path(os.environ.get("DGA_DATA_DIR") or datos["directorio"])
    if not directorio.is_absolute():
        directorio = (ruta.resolve().parent.parent / directorio).resolve()

    settings = Settings(
        directorio_datos=directorio,
        archivos=dict(datos["archivos"]),
        patron_agromet=datos["patron_agromet"],
        punto_control=PuntoControl(**crudo["punto_control"]),
        t_objetivo=tuple(crudo["frecuencia"]["t_objetivo"]),
        n_min_ajuste=crudo["frecuencia"]["n_min_ajuste"],
        n_recomendado=crudo["frecuencia"]["n_recomendado"],
        qa_max_precip_horaria_mm=float(crudo["qa"]["max_precip_horaria_mm"]),
        tormenta=Tormenta(**{k: tuple(v) if isinstance(v, list) else v for k, v in crudo["tormenta"].items()}),
        radios={k: Radio(**v) for k, v in crudo["radios"].items()},
    )
    _validar(settings)
    return settings


def _validar(s: Settings) -> None:
    errores = []
    if not -90 <= s.punto_control.lat <= 90 or not -180 <= s.punto_control.lon <= 180:
        errores.append("punto_control fuera de rango.")
    if any(t <= 1 for t in s.t_objetivo) or list(s.t_objetivo) != sorted(set(s.t_objetivo)):
        errores.append("frecuencia.t_objetivo debe ser creciente, sin repetidos y con T > 1.")
    if s.n_min_ajuste < 3:
        errores.append("frecuencia.n_min_ajuste debe ser >= 3 (LP-III requiere asimetría).")
    if not set(s.tormenta.t_diseno) <= set(s.t_objetivo):
        errores.append("tormenta.t_diseno debe estar contenido en frecuencia.t_objetivo.")
    if not s.tormenta.b_min <= s.tormenta.b_defecto <= s.tormenta.b_max:
        errores.append("tormenta.b_defecto fuera de [b_min, b_max].")
    for clave, r in s.radios.items():
        if not r.min <= r.defecto <= r.max:
            errores.append(f"radios.{clave}: defecto fuera de [{r.min}, {r.max}].")
    if errores:
        raise ValueError("settings.toml inválido:\n- " + "\n- ".join(errores))
