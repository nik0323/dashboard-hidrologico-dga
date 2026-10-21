"""Textos, gráficos, tablas y descargas con estilo común."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from hidro.io.exportar import a_csv


def encabezado(titulo: str, fuente: str, fundamento: str) -> None:
    st.title(titulo)
    st.caption(fuente)
    st.markdown(f"**Fundamento Técnico:** {fundamento}")


def justificacion(texto: str) -> None:
    st.markdown(f"**Justificación Técnica:** {texto}")


def grafico(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch")


def tabla(df: pd.DataFrame, **kwargs) -> None:
    st.dataframe(df, width="stretch", **kwargs)


def descarga_csv(etiqueta: str, df: pd.DataFrame, nombre_archivo: str, key: str, contenedor=st) -> None:
    """Botón de descarga en CSV regional chileno (; y coma decimal)."""
    contenedor.download_button(etiqueta, a_csv(df), nombre_archivo, "text/csv", key=key)
