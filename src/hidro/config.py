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
    """Opciones de la tormenta de diseño: T [años], Δt [min], exponente de desagregación b [-] y
    factor intervalo fijo → 24 h móviles [-]."""

    t_diseno: tuple[int, ...]
    dt_minutos: tuple[int, ...]
    b_defecto: float
    b_min: float
    b_max: float
    factor_intervalo_fijo: float
    factor_min: float
    factor_max: float


@dataclass(frozen=True)
class Settings:
    directorio_datos: Path
    archivos: dict[str, str]
    patron_agromet: str
    punto_control: PuntoControl
    t_objetivo: tuple[int, ...]
    n_min_ajuste: int
    n_recomendado: int
    t_cola: tuple[int, int]
    crecimiento_min_cola: float
    alfa_ks: float
    n_bootstrap: int
    semilla_bootstrap: int
    regional_usar: bool
    regional_n_min_anios: int
    regional_min_estaciones: int
    qa_max_precip_horaria_mm: float
    agromet_desfase_horas: int
    agromet_horas_min_dia: int
    cobertura_min_anual: float
    cobertura_min_maximos: float
    tormenta: Tormenta
    radios: dict[str, Radio]
    archivo_normas: Path

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
        t_cola=tuple(crudo["frecuencia"]["t_cola"]),
        crecimiento_min_cola=float(crudo["frecuencia"]["crecimiento_min_cola"]),
        alfa_ks=float(crudo["frecuencia"]["alfa_ks"]),
        n_bootstrap=int(crudo["frecuencia"]["n_bootstrap"]),
        semilla_bootstrap=int(crudo["frecuencia"]["semilla_bootstrap"]),
        regional_usar=bool(crudo["asimetria_regional"]["usar"]),
        regional_n_min_anios=int(crudo["asimetria_regional"]["n_min_anios"]),
        regional_min_estaciones=int(crudo["asimetria_regional"]["min_estaciones"]),
        qa_max_precip_horaria_mm=float(crudo["qa"]["max_precip_horaria_mm"]),
        agromet_desfase_horas=int(crudo["agromet"]["desfase_horas"]),
        agromet_horas_min_dia=int(crudo["agromet"]["horas_min_dia"]),
        cobertura_min_anual=float(crudo["imputacion"]["cobertura_min_anual"]),
        cobertura_min_maximos=float(crudo["maximos_anuales"]["cobertura_min_anual"]),
        tormenta=Tormenta(**{k: tuple(v) if isinstance(v, list) else v for k, v in crudo["tormenta"].items()}),
        radios={k: Radio(**v) for k, v in crudo["radios"].items()},
        archivo_normas=_resolver(ruta, crudo["normas"]["archivo"]),
    )
    _validar(settings)
    return settings


def _resolver(ruta_settings: Path, ruta: str) -> Path:
    """Ruta absoluta; las relativas se resuelven desde la carpeta del proyecto (padre de config/)."""
    p = Path(ruta)
    return p if p.is_absolute() else (ruta_settings.resolve().parent.parent / p).resolve()


def _validar(s: Settings) -> None:
    errores = []
    if not -90 <= s.punto_control.lat <= 90 or not -180 <= s.punto_control.lon <= 180:
        errores.append("punto_control fuera de rango.")
    if any(t <= 1 for t in s.t_objetivo) or list(s.t_objetivo) != sorted(set(s.t_objetivo)):
        errores.append("frecuencia.t_objetivo debe ser creciente, sin repetidos y con T > 1.")
    if s.n_min_ajuste < 3:
        errores.append("frecuencia.n_min_ajuste debe ser >= 3 (LP-III requiere asimetría).")
    if len(s.t_cola) != 2 or s.t_cola[0] >= s.t_cola[1] or not set(s.t_cola) <= set(s.t_objetivo):
        errores.append("frecuencia.t_cola debe ser [T_inf, T_sup] creciente y contenido en t_objetivo.")
    if not 0 < s.alfa_ks < 1:
        errores.append("frecuencia.alfa_ks debe estar en (0, 1).")
    if s.n_bootstrap < 0:
        errores.append("frecuencia.n_bootstrap debe ser >= 0.")
    if s.regional_n_min_anios < 10 or s.regional_min_estaciones < 2:
        errores.append("asimetria_regional: n_min_anios >= 10 y min_estaciones >= 2.")
    if not 0 <= s.crecimiento_min_cola < 1:
        errores.append("frecuencia.crecimiento_min_cola debe estar en [0, 1).")
    if not -23 <= s.agromet_desfase_horas <= 23:
        errores.append("agromet.desfase_horas debe estar entre -23 y 23.")
    if not 1 <= s.agromet_horas_min_dia <= 24:
        errores.append("agromet.horas_min_dia debe estar entre 1 y 24.")
    if not 0 <= s.cobertura_min_anual <= 1:
        errores.append("imputacion.cobertura_min_anual debe estar en [0, 1].")
    if not 0 <= s.cobertura_min_maximos <= 1:
        errores.append("maximos_anuales.cobertura_min_anual debe estar en [0, 1].")
    if not set(s.tormenta.t_diseno) <= set(s.t_objetivo):
        errores.append("tormenta.t_diseno debe estar contenido en frecuencia.t_objetivo.")
    if not s.tormenta.b_min <= s.tormenta.b_defecto <= s.tormenta.b_max:
        errores.append("tormenta.b_defecto fuera de [b_min, b_max].")
    t = s.tormenta
    if not 1.0 <= t.factor_min <= t.factor_intervalo_fijo <= t.factor_max:
        errores.append("tormenta.factor_intervalo_fijo debe cumplir 1.0 <= factor_min <= factor <= factor_max.")
    for clave, r in s.radios.items():
        if not r.min <= r.defecto <= r.max:
            errores.append(f"radios.{clave}: defecto fuera de [{r.min}, {r.max}].")
    if errores:
        raise ValueError("settings.toml inválido:\n- " + "\n- ".join(errores))
