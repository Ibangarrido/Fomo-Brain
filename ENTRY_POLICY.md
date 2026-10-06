# V10: entradas EARLY r4 e IMPULSO r3

## Alcance

Ajuste experimental prospectivo tras las runs 128–133. No se recalculan resultados ni se reinician carteras. Las posiciones abiertas conservan las salidas existentes. Cada entrada nueva lleva su version de reglas (early-r4 o impulse-r3), indicadores de la cotizacion fresca, precio de la señal, desviacion y la lectura previa exacta usada para confirmar. El patrimonio acumulado mezcla versiones: no atribuir todo el resultado a la ultima revision.

## Entradas

EARLY r4 e IMPULSO r3 amplian la memoria a TODOS los candidatos del ranking filtrado. Antes las carteras evaluaban todo el ranking, pero guardar_memoria solo persistia el TOP 10, dejando candidatos posteriores sin referencia reciente. TOP 10 sigue siendo solo el resumen de pantalla. Se conserva el limite de 10.000 lecturas y se informa de la cobertura en cada ciclo. Los umbrales de entrada, las salidas, los importes y las 15 lecturas no cambian; la ampliacion permite confirmar candidatos en el siguiente ciclo, no garantiza mas compras ni beneficios.

Ambas carteras requieren compras >=60% por numero de operaciones y una lectura previa del mismo contrato, cadena y par de entre 30 y 90 segundos. Antes IMPULSO permitia 55% y la antiguedad de la lectura podia llegar a 5 minutos. Ambas rechazan cotizaciones que difieran mas del 5% del precio de la señal, en cualquier direccion.

EARLY conserva las reglas de r2: edad del par 2–60 minutos; liquidez >=20.000 USD; 40 operaciones en 5m; momentum 5m 2–60% en ambas lecturas; precio entre lecturas +1–12%; liquidez >=95% de la previa; volumen 5m no decreciente. La subida horaria es aviso, no bloqueo.

IMPULSO no exige edad del par. Conserva 20 operaciones en 5m, liquidez >=10.000 USD, momentum 5m 2–60%, precio entre lecturas +1–20%, volumen 5m +10% minimo y liquidez >=95% de la previa.

## Vigilancia

El workflow pide 15 lecturas con intervalo objetivo de 60 segundos: aproximadamente 14 minutos del primer al ultimo punto. La ventana de sesion esta limitada a 900 segundos. Sustituye las 12 lecturas efectivas anteriores, que dejaban mas tiempo sin cotizar hasta la siguiente run. El cron y la concurrencia no cambian. Esto reduce huecos si las runs siguen llegando cada 15 minutos; no garantiza continuidad, ni que GitHub ejecute schedule. Los datos siguen siendo lecturas de la API, no ticks en tiempo real.

## Precios indicativos con liquidez baja

Cuando el par exacto del mismo contrato y cadena conserva precio valido pero su liquidez cae por debajo de 10.000 USD, la posicion guarda un precio, valor neto y resultado INDICATIVOS con fecha separada. No sustituyen el ultimo mark_net admitido, no representan efectivo, no autorizan parciales/cierres y no vuelven completa la valoracion. Se mantienen las entradas pausadas mientras haya posiciones no verificables.

Si todas las posiciones tienen precio actual (admitido o indicativo), las observaciones pueden incluir indicative_only_equity, rotulado expresamente como no liquidable ni patrimonio verificable. Si una consulta posterior no ofrece precio, se eliminan los indicadores de la lectura anterior para no presentarlos como actuales. Un fallo del endpoint de respaldo conserva el precio indicativo valido del par exacto. Al recuperar una cotizacion admitida se reevalúan las salidas existentes.

Dos pruebas adicionales comprueban precio indicativo sin venta/efectivo/entrada nueva, desaparicion del indicador si falta precio, salida solo al recuperar cotizacion admitida, fallo de respaldo e identidad de contrato. Este cambio es diagnostico; no altera filtros de entrada, costes ni reglas de salida.

## Evidencia y limites

La entrada de ore en run 130 tenia 58,6% de compras. Gang reaparecio para entrar usando una referencia de aproximadamente dos minutos antes. Los nuevos filtros rechazan esos indicadores retrospectivos, pero no constituyen un backtest completo ni prueban rentabilidad futura.

Validacion: 25 tests sin red; incluye entrada confirmada fuera del TOP 10 en ambas carteras y limite de memoria de 10.000 lecturas; incluye limites 30/90 segundos en ambas carteras, reproduccion de los indicadores de esas dos entradas, almacenamiento de la lectura previa, 15 lecturas durante 14 minutos, limite de sesion, persistencia, separacion de carteras, salidas y costes.

No se suman carteras. Todo es simulacion con comision y deslizamiento estimados; no se firman ni envian ordenes reales. Los stops se evaluan en cada lectura y una caida entre lecturas o runs puede superar el 15%. El numero de compras no demuestra flujo monetario neto ni compradores unicos. No hay fuente verificada de holders conectada.


## Protección de capital V10 — capital-r1 (6 octubre 2026)

Los filtros EARLY r4/IMPULSO r4 y sus costes se mantienen. Se añade un control
independiente por cartera, antes de nuevas entradas:

- Patrimonio completo (caja + reserva + posiciones cotizadas) <=75 EUR:
  bloqueo persistente de nuevas compras hasta revisión explícita. Referencia:
  100 EUR iniciales; pérdida total máxima configurada 25%. No se recalcula una
  referencia más baja ni se desbloquea al cambiar de día/run. No promete que
  una caída rápida no atraviese el umbral entre lecturas.
- Tres posiciones completas consecutivas con resultado neto negativo,
  cerradas dentro de los últimos 60 minutos: pausa hasta 60 minutos después
  del último cierre. El vencimiento no se prolonga en cada lectura.
- Se suman los resultados de parcial y cierre final por contrato/cadena/hora
  de entrada: una posición globalmente ganadora no cuenta como pérdida por
  vender su resto con pérdida. Un parcial solo no es una posición terminada.
- El bloqueo no ejecuta liquidaciones forzadas ni suspende cotizaciones o
  salidas; el stop y el trailing actuales siguen funcionando. Cotizaciones
  incompletas no disparan el umbral usando un valor antiguo como si fuera actual.
- Se persiste `risk_control` y se imprime `FRENO V10`, con razón y vencimiento
  o necesidad de revisión. Carteras, capital, reserva e historial no se reinician.

Las carteras existentes EARLY (~47.17 EUR) e IMPULSO (~49.91 EUR) ya están por
debajo del umbral: la siguiente lectura válida con este código bloqueará sus
compras. El radar y el experimento WHALE DEMO continúan por separado. Es un
freno de pérdidas, no una mejora de rentabilidad demostrada ni un reinicio.

Evidencia: runs exitosas 148–170. EARLY: 9 stops suman -23.57 EUR, peor -4.41.
IMPULSO: 13 stops suman -27.26 EUR, peor -3.71; las ventas positivas compensan
parte del total. La etiqueta STOP -15% es un disparador en una cotización,
no una orden alojada en el mercado. Lecturas de ~60 s y colas/fallos entre
runs pueden producir cierres peores; la baja liquidez también impide cotizar.
No se garantiza recuperar pérdidas ni se simulan ventas al umbral histórico.

Ejemplos verificables: Sirius EARLY -4.41 (run155), CWC IMPULSO -3.71 (run157),
phubber ambas -2.43 y SI EARLY -2.32 (run169). No se modifica un umbral de entrada
por un único token ni se atribuye el beneficio de NFTM al freno recién añadido.
