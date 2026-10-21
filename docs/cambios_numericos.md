# Cambios numéricos respecto del dashboard original

Cada cambio fue aprobado de forma explícita, se implementó en un commit propio y quedó registrado
en `tests/cambios_aprobados.py`. Los resultados de "antes" se reproducen con la opción indicada.

## Hallazgo #1: la imputación AGROMET extendía la serie fuera del periodo DGA

**Problema.** `imputar_con_agromet` alineaba la serie DGA y la AGROMET usando la *unión* de sus
fechas. Si una estación DGA terminó antes (o empezó después) que AGROMET (2021-2023), los años
fuera de su registro se agregaban completos con lluvia de Placilla Chacarilla. Así entraban a la
serie de PMA y modificaban n, los momentos, los cuantiles y la prueba KS.

**Corrección.** Por defecto, `imputar_con_agromet(df_dga, df_agro)` solo rellena días entre la
primera y la última fecha con registro DGA. El comportamiento anterior queda disponible con
`extender=True` (en la app: casilla "Extender serie fuera del periodo DGA", desactivada por
defecto y con advertencia visible).

**Efecto sobre los datos reales.** Estaciones a <= 30 km de Lo Moscoso, `prep_diarias_historico_6.txt`
y AGROMET Placilla Chacarilla del 01/01/2021 al 31/12/2023. "Mejor" es la distribución con menor D de KS.

| Estación | Registro DGA | Variante | n años | P24 T=100 mejor [mm] | P24 T=100 Gumbel [mm] |
|---|---|---|---|---|---|
| VIÑA VIEJA | 1960 – jul 2003 | Solo DGA | 38 | 126.09 (LP-III) | 149.37 |
| | | Antes (extiende) | 41 | 127.52 (LP-III) | 147.82 |
| | | **Corregido** | **38** | **126.09** (LP-III) | **149.37** |
| PANIAHUE | 1979 – ago 1988 | Solo DGA | 10 | 178.37 (LP-III) | 179.19 |
| | | Antes (extiende) | 13 | 183.28 (LP-III) | 171.52 |
| | | **Corregido** | **10** | **178.37** (LP-III) | **179.19** |
| TRANQUE LAS PATAGUAS | ene – sep 2025 | Solo DGA | 1 | sin ajuste | sin ajuste |
| | | Antes (extiende) | 4 | 134.38 (LP-III) | 144.94 |
| | | **Corregido** | **1** | **sin ajuste** | **sin ajuste** |
| TRANQUE MILLAHUE | ene – abr 2025 | Solo DGA | 1 | sin ajuste | sin ajuste |
| | | Antes (extiende) | 4 | 147.55 (LP-III) | 133.28 |
| | | **Corregido** | **1** | **sin ajuste** | **sin ajuste** |

Antes, en las dos estaciones "Tranque" se reportaban cuantiles de diseño a T = 100 años
construidos con 3 años de AGROMET y 1 año parcial de DGA.

**Sin cambio con esta corrección:** SAN FERNANDO, RIO CLARO EN EL VALLE, CONVENTO VIEJO, RIO
TINGUIRIRICA BAJO LOS BRIONES, MILLAHUE y LA RUFINA. Su registro DGA continúa hasta 2026, así que
2021-2023 quedan *dentro* del periodo. Sin embargo, el archivo DGA no trae datos de esos tres años
(salvo en CONVENTO VIEJO), por lo que AGROMET los seguía rellenando completos. Eso se resuelve en
el hallazgo #1b.

## Hallazgo #1b: la imputación AGROMET completaba años sin registro DGA

**Problema.** Dentro del periodo de registro, la imputación rellenaba cualquier día faltante.
En el archivo `prep_diarias_historico_6.txt` faltan completos los años 2021, 2022 y 2023 en casi
todas las estaciones. Por eso AGROMET (Placilla Chacarilla) aportaba 1.094 días, es decir, tres
PMA anuales enteras tomadas de otra estación.

**Corrección.** Solo se rellenan vacíos en años calendario con cobertura DGA >= 80 %. La cobertura
es el número de días distintos con registro dividido por 365 o 366
(`[imputacion].cobertura_min_anual` en `config/settings.toml`; umbral aprobado por el usuario).
Los años bajo el umbral conservan solo sus días DGA y la app los lista en el panel de imputación.
El comportamiento original queda disponible con la casilla "Imputación sin restricciones
(dashboard original)", que en código corresponde a `extender=True, cobertura_min_anual=0`.

**Efecto sobre los datos reales** (mismas estaciones y fuentes que en el hallazgo #1; "Corregido"
incluye las correcciones #1 y #1b):

| Estación | Variante | n años | P24 T=100 mejor [mm] | P24 T=100 Gumbel [mm] | Días imputados |
|---|---|---|---|---|---|
| SAN FERNANDO | Solo DGA | 53 | 171.68 (LP-III) | 178.96 | 0 |
| | Original | 56 | 173.46 (LP-III) | 177.46 | 1.094 |
| | **Corregido** | **53** | **171.68** (LP-III) | **178.96** | **0** |
| RIO CLARO EN EL VALLE | Solo DGA | 8 | 73.08 (LP-III) | 90.45 | 0 |
| | Original | 11 | 96.01 (LP-III) | 101.17 | 1.094 |
| | **Corregido** | **8** | **73.08** (LP-III) | **90.45** | **0** |
| RIO TINGUIRIRICA BAJO LOS BRIONES | Solo DGA | 25 | 126.85 (Log-Normal) | 129.50 | 0 |
| | Original | 28 | 139.89 (LP-III) | 128.36 | 1.094 |
| | **Corregido** | **25** | **126.85** (Log-Normal) | **129.50** | **0** |
| MILLAHUE | Solo DGA | 52 | 133.36 (LP-III) | 162.65 | 0 |
| | Original | 55 | 136.64 (LP-III) | 161.96 | 1.094 |
| | **Corregido** | **52** | **133.36** (LP-III) | **162.65** | **0** |
| LA RUFINA | Solo DGA | 64 | 169.92 (LP-III) | 193.56 | 0 |
| | Original | 67 | 172.05 (LP-III) | 194.47 | 1.094 |
| | **Corregido** | **64** | **169.92** (LP-III) | **193.56** | **0** |
| CONVENTO VIEJO | todas | 56 | 117.19 (LP-III) | 132.30 | 15 en "Original" y "Corregido" (vacíos cortos) |

**Conclusión.** Con los datos actuales, en las 10 estaciones a <= 30 km, la serie corregida da
los mismos cuantiles que la serie solo DGA. La única imputación que sobrevive son 15 días
aislados en CONVENTO VIEJO, que no alteran ninguna PMA. Los cuantiles reportados antes con
AGROMET activado (opción por defecto del dashboard original) estaban influidos por 3 años de
lluvia de Placilla Chacarilla en 7 de las 10 estaciones; en RIO CLARO EN EL VALLE la diferencia
es de +31 % en P24 T=100.

## Hallazgo #4: años incompletos en la serie de máximos anuales (PMA y QMA)

**Problema.** El máximo anual se calculaba con todos los años presentes, sin revisar cuántos días
con registro tenían. Un año parcial puede no incluir el evento máximo. Por ejemplo, 2026 trae datos
solo hasta el 31/05, antes del peak invernal. Esos años entraban con una PMA o QMA subestimada.

**Corrección.** Solo entran a la serie de máximos los años calendario con cobertura >= 80 %
(días distintos con registro / 365 o 366; `[maximos_anuales].cobertura_min_anual` en
`config/settings.toml`; umbral aprobado por el usuario). Se aplica a la PMA (precipitaciones) y
al QMA (caudales), y la app muestra los años excluidos. Con `cobertura_min_anual = 0` se
reproduce el dashboard original. [SUPUESTO: año calendario; no se evaluó la cobertura de la
temporada húmeda por separado.]

**Efecto sobre la PMA (datos reales, estaciones a <= 30 km).** "Original" corresponde al dashboard
inicial con AGROMET activado por defecto. "Final" incluye las correcciones #1, #1b y #4.

| Estación | Excluidos por #4 | n (original → final) | P24 T=100 mejor [mm], original → final | P24 T=100 Gumbel [mm], original → final |
|---|---|---|---|---|
| SAN FERNANDO | 1971, 2026 | 56 → 51 | 173.46 → **170.01** (LP-III) | 177.46 → **180.19** |
| RIO CLARO EN EL VALLE | 2016, 2020, 2026 | 11 → 5 | 96.01 → **70.07** (LP-III) | 101.17 → **92.33** |
| CONVENTO VIEJO | 1971, 2026 | 56 → 54 | 117.19 → **115.23** (LP-III) | 132.30 → **132.76** |
| RIO TINGUIRIRICA BAJO LOS BRIONES | 2002, 2026 | 28 → 23 | 139.89 (LP-III) → **131.84** (Gumbel) | 128.36 → **131.84** |
| VIÑA VIEJA | 2003 | 41 → 37 | 127.52 → **127.88** (LP-III) | 147.82 → **150.59** |
| MILLAHUE | 1976, 2006, 2026 | 55 → 49 | 136.64 → **156.41** (LP-III) | 161.96 → **158.30** |
| LA RUFINA | 2026 | 67 → 63 | 172.05 → **168.00** (LP-III) | 194.47 → **193.48** |
| PANIAHUE | 1988 | 13 → 9 | 183.28 → **180.82** (LP-III) | 171.52 → **176.16** |
| TRANQUE LAS PATAGUAS | 2025 | 4 → 0 | 134.38 → sin ajuste | 144.94 → sin ajuste |
| TRANQUE MILLAHUE | 2025 | 4 → 0 | 147.55 → sin ajuste | 133.28 → sin ajuste |

Observaciones:
- En MILLAHUE, al excluir 3 años, LP-III a T=100 sube un 14,5 % respecto del original (y un
  17 % respecto de la serie solo DGA), mientras que Gumbel cambia menos de un 3 %. La asimetría
  muestral de log10 es sensible a pocos datos (hallazgo #10). Conviene justificar en el informe la
  distribución adoptada y no basarse solo en el menor D de la prueba KS.
- RIO CLARO EN EL VALLE queda con 5 años completos. La app ya advierte que con menos de 15 años
  la extrapolación a T altos tiene validez limitada.

**Efecto sobre el QMA (estaciones fluviométricas a <= 40 km).** Se excluyen entre 1 y 15 años por
estación. Casos notables: RIO TINGUIRIRICA EN PUENTE RUTA 90 (la estación que la app selecciona por
defecto) pasa de 3 a 0 años y la app lo informa; CANAL TENO EN KM. 13.465 pasa de 25 a 10; RIO
CLARO EN TUNCA, de 31 a 19. El QMA solo se grafica (no se ajustan distribuciones), así que este
cambio no afecta cuantiles reportados.

## Hallazgo #7: la tormenta de diseño usaba la PMA diaria como si fuera P24 de 24 h móviles

**Problema.** La PMA de la DGA es una lectura de intervalo fijo (pluviómetro, 08-08 h). Una
tormenta que cruza el horario de lectura queda repartida en dos días, así que el máximo diario es
menor que el máximo de 24 horas consecutivas. El dashboard usaba la PMA diaria directamente como
$P_{24}$ en las curvas IDF, en el hietograma de bloques alternos y en la serie para HEC-HMS.

**Corrección.** $P_{24} = k \cdot P_{diaria}(T)$, con $k = 1.13$ (Weiss, 1964; OMM, *Manual on
Estimation of Probable Maximum Precipitation*). El valor está en
`[tormenta].factor_intervalo_fijo` de `config/settings.toml` y se puede ajustar en la app (rango
1.00-1.20). Con $k = 1.00$ se reproduce el dashboard original.
[SUPUESTO: 1.13 aprobado por el usuario; verificar contra la norma o manual que exija el proyecto.]

**Alcance.** La tabla de cuantiles de la PMA, la prueba KS y la curva de frecuencia **no cambian**:
siguen describiendo la lectura diaria y ahora lo indican en su rótulo. El factor solo se aplica al
construir la tormenta: P24 del recuadro, curvas IDF, hietograma y CSV para HEC-HMS. Todas esas
magnitudes aumentan exactamente un 13 %.

**Efecto sobre los datos reales** (estaciones a <= 30 km, serie con las correcciones #1, #1b y #4,
distribución de menor D en KS, b = 0.33):

| Estación | Distribución | P diaria T=50 / 100 / 500 [mm] | P24 móvil T=50 / 100 / 500 [mm] | Bloque máx. T=100, Δt=15 min [mm] | i(1 h) T=100 [mm/h] |
|---|---|---|---|---|---|
| SAN FERNANDO | LP-III | 158.1 / 170.0 / 193.9 | 178.7 / 192.1 / 219.1 | 37.70 → 42.60 | 59.57 → 67.31 |
| RIO CLARO EN EL VALLE | LP-III | 69.9 / 70.1 / 70.2 | 79.0 / 79.2 / 79.4 | 15.54 → 17.56 | 24.55 → 27.74 |
| CONVENTO VIEJO | LP-III | 110.6 / 115.2 / 123.3 | 125.0 / 130.2 / 139.4 | 25.55 → 28.87 | 40.37 → 45.62 |
| RIO TINGUIRIRICA BAJO LOS BRIONES | Gumbel | 119.2 / 131.8 / 161.2 | 134.6 / 149.0 / 182.1 | 29.23 → 33.03 | 46.19 → 52.20 |
| VIÑA VIEJA | LP-III | 122.3 / 127.9 / 137.3 | 138.2 / 144.5 / 155.1 | 28.36 → 32.04 | 44.81 → 50.63 |
| MILLAHUE | LP-III | 144.0 / 156.4 / 184.8 | 162.7 / 176.7 / 208.9 | 34.68 → 39.19 | 54.80 → 61.93 |
| LA RUFINA | LP-III | 161.0 / 168.0 / 180.8 | 181.9 / 189.8 / 204.3 | 37.25 → 42.10 | 58.86 → 66.52 |
| PANIAHUE | LP-III | 164.4 / 180.8 / 219.0 | 185.8 / 204.3 / 247.5 | 40.10 → 45.31 | 63.36 → 71.59 |

TRANQUE LAS PATAGUAS y TRANQUE MILLAHUE no tienen ajuste (0 años completos).

## Hallazgo #3: Giandotti con el desnivel del cauce en vez de la altitud media sobre la salida

**Problema.** La fórmula de Giandotti, $t_c = (4\sqrt{A} + 1.5L) / (0.8\sqrt{H})$, define $H$ como
la **altitud media de la cuenca menos la cota de la salida** [m]. El dashboard usaba el desnivel
del cauce ($H_{máx} - H_{mín}$), que suele ser mayor que $H$. Como $t_c \propto 1/\sqrt{H}$, el tc
de Giandotti quedaba subestimado.

**Corrección.** El módulo de cuenca pide la altitud media de la cuenca y la cota de la salida
(m s.n.m., desde el DEM o la curva hipsométrica). Los campos parten vacíos: la app no inventa valores, y
Giandotti queda como "pendiente" hasta que se ingresan. Si $\bar z \le z_{salida}$ se muestra un
error, y si $H$ supera el desnivel del cauce, una advertencia. Kirpich y California no cambian. El
control de dispersión (> 3 veces) usa solo las fórmulas disponibles. En código,
`tiempos_concentracion(..., h_giandotti_m=geom.desnivel_m)` reproduce el original.

**Efecto.** No se puede cuantificar sin los datos del DEM de la cuenca. Como sensibilidad, para la
cuenca de ejemplo de la app (A = 15.5 km², L = 8.2 km, desnivel del cauce 369 m; Kirpich y
California = 1.11 h):

| H [m] | H / desnivel | tc Giandotti [h] | vs. original (1.83 h) | Lag SCS = 0.6·tc [min] |
|---|---|---|---|---|
| 100 | 0.27 | 3.51 | +92 % | 126.2 |
| 150 | 0.41 | 2.86 | +57 % | 103.1 |
| 200 | 0.54 | 2.48 | +36 % | 89.2 |
| 250 | 0.68 | 2.22 | +21 % | 79.8 |
| 300 | 0.81 | 2.02 | +11 % | 72.9 |
| 369 | 1.00 | 1.83 | 0 % (original) | 65.7 |

**Alcance en la ficha HEC-HMS.** El tc adoptado por defecto sigue siendo Kirpich, así que la ficha
solo cambia si el usuario adopta el valor de Giandotti.

## Hallazgo #8: el QMA se calcula con caudal medio diario (aviso, sin cambio numérico)

El QMA del módulo de caudales es el máximo anual de los caudales **medios diarios**, que subestima
el caudal máximo instantáneo, es decir, el que controla la cota de inundación. Ahora la pestaña de
crecidas lo advierte. No se aplicó ningún coeficiente de conversión porque depende de la cuenca y
requeriría un supuesto adicional.

## Hallazgo #11: muestras de calidad censuradas graficadas como concentraciones medidas

**Problema (diagnóstico corregido).** En el análisis inicial se supuso que los valores censurados
venían en `VALOR` como texto ("<0.01") y se descartaban. En `calidad_agua_historico.txt`, en
cambio, `VALOR` siempre es numérico y la censura viene en la columna `CALIDAD`:

| Marca `CALIDAD` | Filas | Interpretación |
|---|---|---|
| `=` | 849.765 | valor cuantificado |
| `<` | 441.594 (28.5 %) | bajo el límite de detección: `VALOR` es el límite, no una medición |
| (vacía) | 256.777 | sin marca |
| `>` | 546 | sobre el rango analítico |
| `D`, `?`, `*`, `-`, `E`, `0` | 872 | códigos no documentados |

El dashboard ignoraba la columna `CALIDAD` y graficaba todos los valores como concentraciones
medidas. En la práctica, los límites de detección aparecían como si fueran mediciones.

**Corrección (sin supuestos ni cambios de valores).** Cada muestra se clasifica según su marca
(`core/calidad.clasificar_marca`). La serie temporal muestra cada marca con un símbolo distinto,
y la línea une solo las muestras no censuradas. El box plot separa las marcas, y un aviso y una
tabla informan cuántas muestras son censuradas. No se sustituye ningún valor (LD, LD/2, etc.),
porque esa elección es metodológica y queda a criterio del análisis.

**Efecto sobre los datos reales** (estaciones a <= 60 km de Lo Moscoso: 79.873 muestras, 28.6 %
censuradas). Parámetros con mayor proporción de muestras censuradas (con al menos 50 muestras):

| Parámetro | Muestras | % censuradas |
|---|---|---|
| Selenio disuelto | 1.059 | 99.7 |
| Plata total | 2.005 | 98.5 |
| Cadmio total | 2.099 | 97.4 |
| Cromo hexavalente disuelto | 946 | 94.4 |
| Selenio total | 792 | 93.4 |
| Mercurio total | 2.028 | 92.9 |
| Cobalto total | 1.878 | 92.2 |
| Níquel total | 2.058 | 89.8 |
| Plomo total | 2.081 | 88.4 |
| Fosfato | 140 | 85.0 |

**Implicancia.** Para estos metales, las "series" del dashboard original eran casi enteramente
límites de detección. Una comparación con normas (por ejemplo, NCh 409 o NCh 1333) debe usar solo
valores cuantificados, o tratar explícitamente los censurados. Un límite de detección por sobre la
norma no indica cumplimiento ni incumplimiento.

**Sin cambio:** en los datos revisados, ningún parámetro tiene más de una unidad.

## Hallazgo #12: niveles dinámicos y pozos embancados mezclados con el nivel estático

**Problema.** El módulo de aguas subterráneas ignoraba la columna `OBSERVACION` de la DGA. En
`niveles_estaticos_pozos_historico.txt`:

| Observación | Mediciones | Tratamiento original |
|---|---|---|
| (vacía) | 144.173 | nivel estático (2.305 registran 0 m) |
| Dinamico | 7.740 | **incluida como nivel estático**, aunque es un nivel con bombeo |
| Sin acceso | 7.337 | sin nivel; descartada sin aviso |
| Seco | 4.201 | sin nivel; descartada sin aviso, con lo que se perdía la información de pozo seco |
| Embancado | 3.026 | 2.838 con nivel ≤ 0: **incluidas como nivel 0 m** (el más somero) |
| Surgente | 489 | profundidad negativa (nivel sobre la superficie): válida |

**Corrección.** Cada medición se clasifica según su observación (`core/pozos.clasificar_condicion`).
El nivel estático, es decir la serie, el box plot, el nivel somero, el abatimiento y la amplitud,
usa solo las mediciones **sin observación** y las **surgentes**. Las dinámicas se pueden mostrar
aparte en el gráfico (casilla), los eventos de pozo seco se marcan con líneas verticales y se
listan por año, y un aviso y una tabla informan todas las condiciones. Excluir las mediciones
dinámicas no es un supuesto: por definición no son niveles estáticos. Las mediciones de nivel = 0 m
sin observación se conservan, pero se advierten, porque no se puede saber si son nivel en
superficie o un faltante.

**Efecto sobre los datos reales** (114 pozos a <= 50 km con nivel): **31 pozos cambian**; 56 tienen
mediciones dinámicas, 4 tienen mediciones embancadas y 5 tienen eventos de pozo seco. Mayores
cambios:

| Pozo | Dinámicas | Nivel somero [m] | Abatimiento máx. [m] | Amplitud [m] |
|---|---|---|---|---|
| ASENTAMIENTO LAS GARZAS | 2 | 0.45 → 0.45 | 43.01 → **8.10** | 42.56 → **7.65** |
| POZO ASENTAMIENTO LA PUERTA | 4 | 0.90 → 0.90 | 18.63 → **4.50** | 17.73 → **3.60** |
| A.P. SAN ENRIQUE | 83 | 12.10 → 12.10 | 44.80 → **33.20** | 32.70 → **21.10** |
| APR LOS MAITENES DE TAGUA TAGUA EL INCA | 13 | 2.37 → 2.37 | 15.43 → **4.38** | 13.06 → **2.01** |
| APR IDAHUE SAN VICENTE | 7 | 0.19 → 0.19 | 18.58 → **8.39** | 18.39 → **8.20** |
| FUNDO LA MACARENA | 71 (+1 seco) | 1.50 → **9.00** | 55.55 → **55.06** | 54.05 → **46.06** |
| SAN VICENTE AP 2 | 81 | 0.00 → 0.00 | 16.79 → **10.79** | 16.79 → **10.79** |
| APR PENCAHUE BAJO | 35 | 2.72 → 2.72 | 9.67 → **4.07** | 6.95 → **1.35** |

En la mayoría de los casos el original atribuía al acuífero abatimientos que eran el cono de
bombeo del propio pozo, lo que sobrestimaba la amplitud de fluctuación del nivel freático.

## Hallazgos #5 y #6: agregación diaria de AGROMET

**Problema #5.** AGROMET se sumaba por día calendario (00-24 h), mientras que el pluviómetro DGA
se lee a las 08:00. **Problema #6.** Las horas sin dato se sumaban como 0 mm y los registros
rechazados por QA/QC (> 150 mm/h) se reemplazaban por 0: un día con horas faltantes o con un dato
erróneo se trataba como total y seco.

**Verificación empírica del desfase.** Correlación de Pearson entre la precipitación diaria de DGA
CONVENTO VIEJO (única estación a <= 30 km con registro DGA en 2021-2023) y AGROMET Placilla
Chacarilla, con QA aplicado y solo días AGROMET completos:

| Ventana diaria AGROMET para la fecha D | r | días |
|---|---|---|
| D 00:00 – D+1 00:00 (calendario, original) | 0.806 | 1011 |
| **D 08:00 – D+1 08:00** | **0.916** | 1016 |
| D 16:00 – D+1 16:00 | 0.798 | 1014 |
| D −08:00 – D 16:00 | 0.530 | 1014 |

La DGA asigna a la fecha D la lluvia entre las 08:00 de D y las 08:00 de D+1.

**Corrección.**
- Cada registro horario con marca t acumula la hora (t − 1 h, t], y el día D suma las horas en
  (D 08:00, D+1 08:00] (`[agromet].desfase_horas = 8`).
- Las horas faltantes y las rechazadas por QA quedan como faltantes, y solo se usan días con 24 h
  válidas (`[agromet].horas_min_dia = 24`, sin supuesto de relleno).
- Si una hora se repite entre archivos, se conserva la del primero en orden alfabético.

**Efecto.**

| AGROMET diario | Días | Total [mm] | Máximo diario [mm] |
|---|---|---|---|
| Original | 1094 | 1234.7 | 83.8 |
| Corregido | 1031 | 1200.3 | 82.4 |

Se descartan 64 días incompletos y se anulan 2 registros horarios (344 y 497 mm/h, ambos a las
00:00 de julio de 2023). **Ningún cuantil cambia**: tras las correcciones #1 y #1b, la única
imputación vigente son 15 días aislados en CONVENTO VIEJO (el mismo número que antes), que no
determinan ninguna PMA.

## Hallazgo #2: representatividad de AGROMET (diagnóstico)

El panel de imputación muestra la correlación diaria entre la estación DGA y AGROMET en los días
comunes (mínimo 30 días). **No bloquea la imputación**, porque fijar un umbral sería un supuesto no
aprobado. Con los datos actuales solo CONVENTO VIEJO tiene días comunes (r = 0.92, n = 1016). Las
demás estaciones no tienen registro DGA en 2021-2023, así que la correlación queda "no evaluable",
y de todos modos no se imputan por la regla de cobertura (#1b). La ubicación de la estación AGROMET
no viene en los archivos, por lo que no se usa un criterio de distancia.

## Hallazgo #13: casos borde en la conversión de coordenadas

**Problema.** `dms_a_decimal` trataba como DMS cualquier valor entero, así que −34.0 (grados
decimales) se convertía en 0°0'34'' (−0.0094°). Además, 0 producía una coordenada válida (0°) y no
se validaba que una latitud fuera ≤ 90°.

**Corrección.** Si |v| ≤ 180, el valor es siempre grado decimal: un DMS real de al menos 1° tiene 5
dígitos o más (10000), y un DMS menor que 180 equivaldría a menos de 2', lo que no es una
coordenada plausible. El valor 0 se trata como coordenada faltante (NaN), y una latitud con
|valor| > 90° es inválida.

**Efecto sobre los datos reales.** Ninguno: en los 4 archivos DGA todas las coordenadas convertidas
son idénticas antes y después, porque no hay valores decimales, ceros ni latitudes fuera de rango.
Es una corrección preventiva para archivos de otras fuentes.

**Observación (dato DGA, no corregido).** En `calidad_agua_historico.txt`, la estación "Estero
natales en bocatoma" (XII Región) tiene LATITUD = 50141, es decir 5°01'41'', fuera de Chile.
Probablemente corresponde a 51°41'. No afecta los análisis en torno a Lo Moscoso, que queda a más
de 2.000 km.

## Hallazgo #10: elección de la distribución sin revisar la cola

**Problema.** La tormenta de diseño usaba por defecto la distribución con menor estadístico D de
KS. Con pocos años y una asimetría de log10 negativa fuerte, LP-III puede tener el menor D y aun
así tener una cota superior, $x_{máx} = 10^{\mu - 2\sigma/g}$, que aplana la cola. En ese caso los
cuantiles casi no crecen con T, lo que no es físicamente creíble para extrapolar.

**Corrección (opción 1, sin supuestos estadísticos nuevos).** Para cada distribución se calcula el
crecimiento del cuantil entre T = 50 y T = 500 años. Si es menor al 5 %, la distribución se marca
"con techo" (`[frecuencia].t_cola` y `crecimiento_min_cola`). La tormenta usa por defecto la de
menor D *sin* techo, y la app muestra el aviso, la cota de LP-III y la distribución recomendada.
**Ningún cuantil cambia**: las tablas de cuantiles y de KS siguen iguales, la distribución de
menor D se sigue informando y el usuario puede elegir cualquier distribución en el selector.

**Efecto sobre los datos reales.** Solo RIO CLARO EN EL VALLE (n = 5) cambia de distribución por
defecto. En las otras 7 estaciones con ajuste ninguna distribución tiene techo: todas crecen entre
11 % y 46 % de T=50 a T=500.

| RIO CLARO EN EL VALLE | D de KS | P diaria T=50 / 100 / 500 [mm] | Crecimiento T50→T500 | P24 móvil T=100 [mm] |
|---|---|---|---|---|
| Log-Pearson III (menor D, **con techo**; cota 70.3 mm) | 0.2492 | 69.87 / 70.07 / 70.24 | +0.5 % | 79.18 |
| **Log-Normal (recomendada)** | 0.3848 | 85.02 / 90.05 / 101.15 | +19.0 % | **101.75** |
| Gumbel | 0.4193 | 86.07 / 92.33 / 106.79 | +24.1 % | 104.33 |

La P24 de diseño por defecto para T=100 pasa de 79.18 mm a 101.75 mm (+28.5 %). Con 5 años, las
tres distribuciones pasan la prueba KS (D crítico 0.6082): la prueba no logra discriminar entre
ellas. Para el informe conviene justificar la elección o apoyarse en estaciones vecinas con
registro largo (por ejemplo, SAN FERNANDO, a 6.6 km del punto de control, con 51 años completos).

**Limitación documentada.** En series con coeficiente de variación muy bajo (≈ 5 %), todas las
distribuciones crecen poco y podrían marcarse aunque no tengan cota. No ocurre en las PMA de esta
zona, cuyo CV está entre 20 % y 40 %.

**Corrección de interfaz asociada.** El selector de distribución conservaba la elección de la
estación anterior. Ahora su clave incluye la estación, así que al cambiar de estación se aplica la
distribución recomendada para la nueva.
