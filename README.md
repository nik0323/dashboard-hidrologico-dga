# hidro — Plataforma de análisis hidrológico e hidrogeológico DGA

App Streamlit para analizar datos de la Dirección General de Aguas (Chile) en torno a un punto de
control: precipitaciones (PMA, ajuste Gumbel / Log-Pearson III / Log-Normal, KS, IDF, hietograma
para HEC-HMS), parámetros de cuenca (tc, CN SCS), caudales (curva de duración, QMA), niveles de
pozos y calidad fisicoquímica.

## Instalación

Requiere Python 3.10 o superior.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt     # instala dependencias fijadas + el paquete hidro en modo editable
```

## Uso

```powershell
streamlit run app.py
```

La carpeta de datos se elige en este orden: barra lateral → variable de entorno `DGA_DATA_DIR` →
`[datos].directorio` en `config/settings.toml`. Si falta un archivo, el módulo ofrece subirlo.

Archivos esperados (nombres configurables en `[datos.archivos]`):

| Clave | Archivo por defecto |
|---|---|
| precipitaciones | `prep_diarias_historico_6.txt` |
| caudales | `caudal_diario_historico.txt` |
| pozos | `niveles_estaticos_pozos_historico.txt` |
| calidad | `calidad_agua_historico.txt` |
| AGROMET (opcional) | patrón `*agromet_Placilla*.csv` |

## Configuración

Todo valor técnico vive en `config/settings.toml`: punto de control, periodos de retorno,
mínimo de años para el ajuste, umbral QA/QC de AGROMET, opciones de la tormenta de diseño y radios
de búsqueda por módulo. El archivo se valida al cargar; un valor inválido detiene la app con el
detalle del error. `HIDRO_SETTINGS=<ruta>` permite usar otro archivo (p. ej. otra cuenca).

## Estructura

```
app.py                 entrada Streamlit: menú, carpeta de datos y despacho al módulo
config/settings.toml   configuración
src/hidro/
  config.py            carga y validación de settings
  contexto.py          Contexto que recibe cada módulo (settings, carpeta, prefijo de keys)
  core/                cálculo puro, sin Streamlit (testeable con pytest)
  io/                  lectura DGA/AGROMET, normalización, imputación, exportación CSV
  ui/                  componentes Streamlit: caché, mapa y selector de estaciones, gráficos
  modulos/             un archivo por módulo + registro
tests/                 regresión numérica contra el original, config, registro, app
```

Regla de dependencias: `core` ← `io` ← `ui` ← `modulos` ← `app.py`. `core/` e `io/` nunca
importan Streamlit (hay un test que lo verifica).

## Cómo agregar un módulo

1. Crear `src/hidro/modulos/evapotranspiracion.py`:

   ```python
   import streamlit as st

   from hidro.contexto import Contexto
   from hidro.modulos.base import Modulo
   from hidro.modulos.registro import registrar


   @registrar
   class Evapotranspiracion(Modulo):
       clave = "etp"                       # prefijo único de keys de widgets
       nombre = "Evapotranspiración"       # texto del menú
       orden = 25                          # posición en el menú
       archivos_requeridos = ()            # claves de [datos.archivos], si usa archivos

       def render(self, ctx: Contexto) -> None:
           st.title("Evapotranspiración")
           # widgets con key=ctx.key("nombre"); cálculos en hidro/core/
   ```

2. Agregar el import en `src/hidro/modulos/__init__.py`.
3. Poner los cálculos en `src/hidro/core/` como funciones puras con su test en `tests/`.
4. Si usa un archivo nuevo, declararlo en `[datos.archivos]` y, si filtra estaciones, agregar su
   bloque `[radios.<clave>]`.

## Tests

```powershell
python -m pytest -q
```

- `test_regresion_original.py`: el original congelado (`tests/_original/`) sigue produciendo las
  salidas guardadas en `tests/golden/`.
- `test_regresion_hidro.py`: el paquete reproduce sus propias salidas congeladas
  (`tests/golden/salidas_hidro.pkl`) con tolerancia absoluta 1e-9, y **solo difiere del original
  en los casos listados en `tests/cambios_aprobados.py`**.
- `test_correcciones.py`: propiedades de cada corrección aprobada.
- `test_config.py`, `test_registro.py`, `test_ui_cache.py`, `test_app.py` (los 5 módulos con
  `streamlit.testing.AppTest` sobre datos sintéticos).

Para aplicar un cambio numérico aprobado:
1. Implementarlo y agregar sus tests en `test_correcciones.py`.
2. Registrar los casos afectados en `tests/cambios_aprobados.py`.
3. Regenerar el golden del paquete con `python tests/generar_golden.py --hidro`. El golden del
   original no se regenera.
4. Documentar el antes y después en `docs/cambios_numericos.md` y hacer un commit aparte.

## Migración desde `dashboard_dga.py`

| Original (`dashboard_dga.py`) | Nueva ubicación | Test |
|---|---|---|
| `dms_a_decimal` | `core/geo.py` | `dms_a_decimal` |
| `haversine_vectorizado` | `core/geo.py` | `haversine` |
| `hietograma_bloques_alternos` | `core/tormentas.py` | `hietograma`, `tormenta_diseno` |
| `ajustar_distribuciones` | `core/frecuencia.py` → `ResultadoAjuste` | `ajustar_distribuciones`, `precipitaciones_*` |
| tabla de cuantiles (l. 518) | `core/frecuencia.tabla_cuantiles` | `tormenta_diseno` |
| curva IDF (l. 572) | `core/tormentas.intensidad_idf` | `tormenta_diseno` |
| tabla HEC-HMS (l. 591) | `core/tormentas.tabla_hec_hms` | `tormenta_diseno` |
| PMA / QMA (l. 470, 754) | `core/series.maximos_anuales` | `precipitaciones_*`, `caudales` |
| totales mensual/anual (l. 478, 486) | `core/series.totales_mensuales/anuales` | `precipitaciones_sin_agromet` |
| media/σ/CV PMA (l. 494) | `core/series.estadisticos` | `precipitaciones_*` |
| niveles pozo (l. 798) | `core/series.rango_niveles` | `pozos` |
| tc Kirpich/California/Giandotti (l. 631) | `core/cuenca.tc_*`, `tiempos_concentracion` | `cuenca_tc` |
| lag 0.6·tc (l. 658) | `core/cuenca.lag_scs` | `cuenca_tc`, `cuenca_cn_ficha` |
| CN ponderado, S, Ia (l. 685) | `core/cuenca.cn_ponderado`, `retencion_scs` | `cuenca_cn_ficha` |
| `validar_tabla_cn` | `core/cuenca.py` | `validar_tabla_cn` |
| ficha HEC-HMS (l. 699) | `core/cuenca.ficha_hec_hms` | `cuenca_cn_ficha` |
| curva de duración, Q50/Q85 (l. 731) | `core/caudales.curva_duracion` | `caudales` |
| filtro por radio (l. 365) | `core/estaciones.filtrar_por_radio` + `ui/red.filtro_radio` | `red_estaciones`, `test_app` |
| resumen y serie de estación (l. 389, 408) | `core/estaciones.resumen_estaciones`, `serie_estacion` | `red_estaciones`, `pozos`, `calidad` |
| filtro de parámetro (l. 824) | `core/calidad.filtrar_parametro` | `calidad` |
| `_leer_csv` | `io/lectura.leer_csv` | `leer_csv_codificaciones` |
| `cargar_datos` | `io/lectura.cargar_serie_dga` + caché `ui/cache.py` | `cargar_datos`, `test_ui_cache` |
| `cargar_agromet` | `io/lectura.cargar_agromet` + caché `ui/cache.py` | `cargar_agromet` |
| `imputar_con_agromet` | `io/imputacion.py` | `imputar_con_agromet`, `precipitaciones_con_agromet` |
| serie sin AGROMET (l. 450) | `io/imputacion.serie_sin_imputar` | `precipitaciones_sin_agromet` |
| años PMA imputada (l. 455) | `io/imputacion.resumen_imputacion` | `precipitaciones_con_agromet` |
| `agregar_columnas_fecha` | `io/normalizacion.py` | `agregar_columnas_fecha` |
| detección de columnas (l. 365, 824) | `io/normalizacion.columna_estacion/parametro` | `red_estaciones`, `calidad` |
| `a_csv` | `io/exportar.py` | `a_csv` |
| `obtener_fuente`, `cargar_o_detener` | `ui/datos.py` | `test_app` |
| `filtrar_por_radio`, `mostrar_red_estaciones` | `ui/red.py` | `test_app` |
| `encabezado`, `justificacion` | `ui/componentes.py` | `test_app` |
| `modulo_precipitaciones` … `modulo_calidad` | `modulos/*.py` | `test_app` |
| `MODULOS`, `main` | `modulos/registro.py`, `app.py` | `test_registro`, `test_app` |
| constantes (l. 35-57) | `config/settings.toml` | `test_config` |

Los nombres de test en la tercera columna son los casos de `tests/casos.py`, ejecutados por
`test_regresion_original.py` y `test_regresion_hidro.py`.

## Limitaciones técnicas conocidas

Se conservan a propósito para no cambiar resultados sin revisión; cada una está marcada con
`ADVERTENCIA (hallazgo #n)` en el código. Las correcciones ya aplicadas están en
`docs/cambios_numericos.md`.

- #1 y #1b (corregidos): la imputación AGROMET solo rellena vacíos dentro del periodo DGA y en
  años con cobertura DGA >= 80 % (`[imputacion].cobertura_min_anual`).
- #2: AGROMET se aplica a cualquier estación sin importar la distancia.
- #3: Giandotti usa el desnivel del cauce en vez de la altitud media de la cuenca sobre la salida.
- #4: los máximos anuales no verifican la completitud de cada año.
- #5, #6: AGROMET usa el día calendario 00-24 h, y las horas faltantes y los valores rechazados por QA se suman como 0 mm.
- #7: P24 sin factor de intervalo fijo → 24 h móvil; b = 0.33 sin calibración local.
- #8: QMA se calcula con el caudal medio diario, no con el instantáneo.
- #9, #10: KS con D crítico asintótico; LP-III sin asimetría regional.
- #11, #12: datos censurados de calidad y observaciones de pozos ignorados.
- #13: casos borde de `dms_a_decimal`.
