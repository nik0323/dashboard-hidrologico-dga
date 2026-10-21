"""Registro de módulos: sin entradas None, claves únicas y extensible sin tocar el resto."""

import pytest

import hidro.modulos  # noqa: F401  (registra los módulos)
from hidro.config import cargar_settings
from hidro.modulos import registro
from hidro.modulos.base import Modulo


@pytest.fixture
def registro_aislado(monkeypatch):
    monkeypatch.setattr(registro, "_REGISTRO", dict(registro._REGISTRO))


def test_modulos_registrados():
    clases = registro.modulos()
    assert [m.clave for m in clases] == ["precipitaciones", "cuenca", "caudales", "pozos", "calidad", "normas"]
    assert all(isinstance(m, type) and issubclass(m, Modulo) for m in clases)


def test_archivos_requeridos_existen_en_settings():
    archivos = cargar_settings().archivos
    for m in registro.modulos():
        assert set(m.archivos_requeridos) <= set(archivos), m.clave


def test_agregar_modulo_nuevo(registro_aislado):
    @registro.registrar
    class Evapotranspiracion(Modulo):
        clave = "etp"
        nombre = "Evapotranspiración"
        orden = 25

        def render(self, ctx):
            pass

    assert [m.clave for m in registro.modulos()][:3] == ["precipitaciones", "cuenca", "etp"]


def test_rechaza_modulos_invalidos(registro_aislado):
    class SinRender(Modulo):
        clave, nombre = "x", "X"

    class ClaveRepetida(Modulo):
        clave, nombre = "caudales", "Otro"

        def render(self, ctx):
            pass

    class SinNombre(Modulo):
        clave = "y"

        def render(self, ctx):
            pass

    with pytest.raises(TypeError):
        registro.registrar(SinRender)
    with pytest.raises(ValueError):
        registro.registrar(ClaveRepetida)
    with pytest.raises(ValueError):
        registro.registrar(SinNombre)
    with pytest.raises(TypeError):
        registro.registrar(None)
