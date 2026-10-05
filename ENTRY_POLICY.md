# V10: entradas EARLY r3 e IMPULSO r2

## Alcance

Ajuste experimental prospectivo tras las runs 128–130. No se recalculan resultados ni se reinician carteras. Las posiciones abiertas conservan las salidas existentes. Cada entrada nueva lleva su version de reglas (early-r3 o impulse-r2), indicadores de la cotizacion fresca, precio de la señal, desviacion y la lectura previa exacta usada para confirmar. El patrimonio acumulado mezcla versiones: no atribuir todo el resultado a la ultima revision.

## Entradas

Ambas carteras requieren compras >=60% por numero de operaciones y una lectura previa del mismo contrato, cadena y par de entre 30 y 90 segundos. Antes IMPULSO permitia 55% y la antiguedad de la lectura podia llegar a 5 minutos. Ambas rechazan cotizaciones que difieran mas del 5% del precio de la señal, en cualquier direccion.

EARLY conserva las reglas de r2: edad del par 2–60 minutos; liquidez >=20.000 USD; 40 operaciones en 5m; momentum 5m 2–60% en ambas lecturas; precio entre lecturas +1–12%; liquidez >=95% de la previa; volumen 5m no decreciente. La subida horaria es aviso, no bloqueo.

IMPULSO no exige edad del par. Conserva 20 operaciones en 5m, liquidez >=10.000 USD, momentum 5m 2–60%, precio entre lecturas +1–20%, volumen 5m +10% minimo y liquidez >=95% de la previa.

## Vigilancia

El workflow pide 15 lecturas con intervalo objetivo de 60 segundos: aproximadamente 14 minutos del primer al ultimo punto. La ventana de sesion esta limitada a 900 segundos. Sustituye las 12 lecturas efectivas anteriores, que dejaban mas tiempo sin cotizar hasta la siguiente run. El cron y la concurrencia no cambian. Esto reduce huecos si las runs siguen llegando cada 15 minutos; no garantiza continuidad, ni que GitHub ejecute schedule. Los datos siguen siendo lecturas de la API, no ticks en tiempo real.

## Evidencia y limites

La entrada de ore en run 130 tenia 58,6% de compras. Gang reaparecio para entrar usando una referencia de aproximadamente dos minutos antes. Los nuevos filtros rechazan esos indicadores retrospectivos, pero no constituyen un backtest completo ni prueban rentabilidad futura.

Validacion: 21 tests sin red; incluye limites 30/90 segundos en ambas carteras, reproduccion de los indicadores de esas dos entradas, almacenamiento de la lectura previa, 15 lecturas durante 14 minutos, limite de sesion, persistencia, separacion de carteras, salidas y costes.

No se suman carteras. Todo es simulacion con comision y deslizamiento estimados; no se firman ni envian ordenes reales. Los stops se evaluan en cada lectura y una caida entre lecturas o runs puede superar el 15%. El numero de compras no demuestra flujo monetario neto ni compradores unicos. No hay fuente verificada de holders conectada.
