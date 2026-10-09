# Revisión de investigación de Brain — 9 octubre 2026

Revisión independiente por un agente de IA con enfoque cuantitativo, contrastada
con código, artefactos y fuentes primarias. No es una consulta a una IA externa,
una acreditación profesional ni una clasificación del mejor modelo para bolsa.
Brain estudia tokens y rutas Solana: no trasladamos directamente la ejecución
de acciones ni resultados de Ethereum a esos mercados.

## Diagnóstico

Hemos mejorado observación, seguridad y diagnóstico. Eso no acredita una ventaja
de inversión. La prioridad propuesta es evaluar experimentos de forma comparable
antes de añadir otro filtro. Una semana con muchas recepciones de precios no
equivale a una muestra grande de posiciones independientes.

Evidencia: artefacto `fomo-memory` de run548, GitHub run37984090214, código
21c285b1af58dcbfccf5f6d3dd42f469bb8e4fbc. Es una fotografía anterior a las
correcciones de recepción de ccf70aa; no mide sus efectos. Las cantidades son
del modelo virtual EUR/USD=1, con comisión/deslizamiento supuestos.

| Experimento desde su propia bifurcación | Control | Variante | Diferencia variante-control | Posiciones nuevas completas control/variante |
|---|---:|---:|---:|---:|
| Volumen IMPULSO | -5,4454 | -1,4864 | +3,9590 | 5 / 4 |
| PROTECT con velas | -3,0811 | -3,0811 | 0 | 6 / 6 |
| M4 recuperación | Desconocido | Desconocido | Desconocida | 0 / 6 |

Volumen conserva más capital en esta muestra, pero ambos brazos pierden. No
declaramos rentabilidad, significación ni un ganador. PROTECT con velas no aporta
ventaja observada y mezcla versiones de entrada. M4 impide valorar el patrimonio
total: no sustituimos esa posición por cero, por su marca antigua o por USDC
cotizados. Los seis cierres nuevos de recuperación suman -3,2821 del modelo;
eso tampoco completa la valoración de su posición heredada desconocida.

En todo el historial V10-r3, 21 ventas son 17 posiciones terminadas: 4 ganadoras
y 13 perdedoras. Ese historial mezcla early-r4 y early-r5 y no es una muestra
homogénea de la última versión. Los parciales y cierres finales cuentan juntos.

## Cambio incorporado

`research_metrics.py` ofrece un lector común sin escritura de carteras ni red.
Ejemplo, sobre un artefacto descargado:

```sh
python3 research_metrics.py fomo_lab_volume_impulse_control_r1.json fomo_lab_volume_impulse_volume_r1.json --baseline volume_baseline
```

Para PROTECT usar `protection_baseline`; para M4, `m4_baseline`. Para rebote,
usar `rebound_baseline`, no la base M4 heredada. No comparar dos archivos con
bases distintas; el lector los rechaza. No sumar carteras ni muestras replicadas.

El informe agrupa `(chain, address, opened_at)`, suma parcial y final y cuenta
como terminada solo una posición con cierre final y que ya no está abierta.
La cohorte nueva exige entrada desde la bifurcación. Los cierres heredados
posteriores aparecen aparte con resultado de toda su vida, no como resultado
generado desde la bifurcación. Las ventas parciales abiertas quedan fuera del
conteo de ganadores completos. Se muestran versiones de entrada/riesgo y sus
ausencias. Otras diferencias de configuración deben revisarse en las carteras.

La diferencia patrimonial requiere una base total y una valoración completa,
además de que no haya posiciones abiertas sin cotización admitida. Se exponen
horas y separación de snapshots: los brazos no se consideran cotizados al mismo
instante. Las cotizaciones admitidas siguen siendo estimaciones de simulación.
El informe no selecciona ganador ni calcula significación estadística.

Pruebas: parcial positiva seguida de final que convierte el resultado total en
pérdida; parcial aún abierta; posición heredada; reglas mezcladas; M4 desconocido;
ventaja relativa con pérdida en ambos brazos; bases incompatibles; datos inválidos;
ausencia de mutaciones. No se cambian decisiones, costes, saldos o umbrales.

## Siguiente experimento recomendado, todavía no activado

Mantener una hipótesis principal y su control con presupuesto y reglas iguales.
Volumen es una candidata para seguimiento porque ya hay control, no porque esta
muestra la valide. Antes de recoger la siguiente ventana, registrar versión,
fecha inicial/final, universo, abstenciones, costes, métrica principal y criterio
de revisión. No retocar el umbral usando las pérdidas de esa misma ventana.

Separar beneficio absoluto, diferencia frente al control, exposición, número
de posiciones terminadas, pérdidas extremas y cotizaciones desconocidas. Si una
corrección técnica cambia la comparabilidad, registrar un nuevo periodo de
análisis sin reiniciar saldos ni borrar pérdidas. No promover con muestra pequeña,
valoración incompleta o reglas mezcladas. Ningún tamaño fijo acredita por sí solo
significación: no se ha realizado aquí un cálculo de potencia o independencia.

También falta separar rechazo técnico de abstención por fallo/cobertura OHLCV.
Comprar menos porque falta una fuente puede conservar capital sin demostrar que
el patrón de velas sea útil. Antes de cambiar filtros, medir esa cobertura.
Las ejecuciones reales, gas, MEV, costes netos y efectos de tamaño siguen fuera
de la evidencia; no se activa dinero real ni se fabrica una salida de M4.

## Fuentes originales

Bailey, Borwein, López de Prado y Zhu, *The Probability of Backtest Overfitting*:
https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
El trabajo trata el riesgo de selección al evaluar estrategias históricas; no
calculamos su PBO para Brain. Su advertencia fundamenta la cautela metodológica,
no demuestra que estos laboratorios ya estén sobreajustados.

SEC, *Stop, Stop-Limit, and Trailing Stop Orders — Investor Bulletin*:
https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15
En acciones, el precio disparador no garantiza el precio de ejecución. Es una
distinción conceptual útil, no una estimación de deslizamiento para Solana.
En Brain, además, el stop es una regla evaluada por lecturas virtuales.
