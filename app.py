"""
Plataforma de Análisis Hidrológico e Hidrogeológico DGA
=======================================================

Ejecutar con:
    streamlit run app.py

Carpeta de datos (en orden de prioridad):
    1. Lo que escribas en la barra lateral ("Carpeta de datos").
    2. La variable de entorno DGA_DATA_DIR.
    3. [datos].directorio en config/settings.toml.
Si un archivo no se encuentra en la carpeta, el módulo ofrece subirlo desde el navegador.
"""

import logging
import sys
from pathlib import Path

import streamlit as st

try:
    import hidro  # noqa: F401
except ImportError:  # sin `pip install -e .`: usar el código fuente del repositorio
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from hidro.config import cargar_settings
from hidro.contexto import Contexto
from hidro.modulos import registro

st.set_page_config(page_title="Plataforma de Análisis Hidrológico e Hidrogeológico DGA", layout="wide")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    settings = cargar_settings()
    modulos = {cls.nombre: cls for cls in registro.modulos()}

    st.sidebar.title("Módulos de Análisis")
    nombre = st.sidebar.radio("Seleccione la disciplina a evaluar:", list(modulos), key="app__modulo")

    dir_datos = st.sidebar.text_input(
        "Carpeta de datos:", value=str(settings.directorio_datos), key="app__dir_datos",
        help="Carpeta con los archivos DGA y AGROMET. También se puede fijar con la variable de entorno DGA_DATA_DIR.")
    dir_datos = Path(dir_datos.strip().strip('"'))
    st.sidebar.divider()

    cls = modulos[nombre]
    cls().render(Contexto(settings=settings, dir_datos=dir_datos, clave_modulo=cls.clave))


if __name__ == "__main__":
    main()
