"""Registro de módulos mediante el decorador `@registrar`."""

from __future__ import annotations

from hidro.modulos.base import Modulo

_REGISTRO: dict[str, type[Modulo]] = {}


def registrar(cls: type[Modulo]) -> type[Modulo]:
    """Registra una subclase concreta de `Modulo`. Falla si la clave o el nombre faltan o se repiten."""
    if not (isinstance(cls, type) and issubclass(cls, Modulo)):
        raise TypeError(f"{cls!r} no es subclase de Modulo.")
    if getattr(cls, "__abstractmethods__", None):
        raise TypeError(f"{cls.__name__} no implementa: {sorted(cls.__abstractmethods__)}.")
    for atributo in ("clave", "nombre"):
        if not isinstance(getattr(cls, atributo, None), str) or not getattr(cls, atributo):
            raise ValueError(f"{cls.__name__} debe definir '{atributo}'.")
    for otro in _REGISTRO.values():
        if otro is not cls and (otro.clave == cls.clave or otro.nombre == cls.nombre):
            raise ValueError(f"{cls.__name__} repite la clave o el nombre de {otro.__name__}.")
    _REGISTRO[cls.clave] = cls
    return cls


def modulos() -> list[type[Modulo]]:
    """Módulos registrados ordenados por (orden, nombre)."""
    return sorted(_REGISTRO.values(), key=lambda m: (m.orden, m.nombre))
