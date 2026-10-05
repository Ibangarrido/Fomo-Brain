# Revisión del Brain — 5 de octubre de 2026

## Evidencia verificable

- Run 140: FartmanSacks emitió una venta de ANYR y compras de IMD y V4.
  ANYR no tenía posición propia; IMD/V4 quedaron sin cotización admisible.
- Run 141: tres alertas BUY de CLAUS, todas descartadas por cotización.
- Runs 141–144: ambos lectores conectados; demo declara 60 s de retraso.
- Run 143: IMPULSO compró HODLUP con +45.71%/5m; cerró dos minutos después
  con -2.60 EUR. Un caso no valida por sí solo el límite experimental 25%.
- Run 144: último cierre EARLY 70.74 EUR, realizado -29.26 EUR;
  IMPULSO 56.21 EUR, realizado -42.39 EUR. No sumar carteras.
- Run 145: el test defectuoso bloqueó análisis/lectores. Corregido en e9acbdc;
  ninguna operación de esa run puede atribuirse a la estrategia nueva.

Runs: https://github.com/Ibangarrido/Fomo-Brain/actions/runs/37350779609
https://github.com/Ibangarrido/Fomo-Brain/actions/runs/37352718078
https://github.com/Ibangarrido/Fomo-Brain/actions/runs/37356461472
https://github.com/Ibangarrido/Fomo-Brain/actions/runs/37358331136
https://github.com/Ibangarrido/Fomo-Brain/actions/runs/37360265819

## Mercado, velas y flujo: qué sabemos y qué falta

Una vela contiene apertura, máximo, mínimo, cierre y volumen en un intervalo.
Una subida porcentual de cinco minutos de DEX Screener no contiene esos cuatro
precios: no permite afirmar mecha de rechazo, ruptura o retesteo. Desde r2 se
recogen velas OHLCV cerradas de un minuto para las compras de ballenas cotizadas
por GeckoTerminal. Son contexto; no se añade un filtro sin evaluarlo.

Una proporción del 60% de compras cuenta transacciones. No demuestra el 60%
del dinero comprador: una venta grande puede pesar más que muchas compras
pequeñas. Tampoco un holder equivale necesariamente a una persona independiente.
DEX Screener en los endpoints usados no aporta serie de holders ni flujo USD
separado por lado. No se fingen esos datos ni se aplica un umbral de holders.

La hipótesis a evaluar es entrada tras confirmación con liquidez estable y
volumen sostenido, sin perseguir una extensión ya consumida. Un rechazo con
mecha superior o pérdida de mínimos requiere velas reales; el ranking agregado
no sirve para demostrarlo. Comprobar pérdida de impulso y protección de
beneficios requiere una secuencia de cotizaciones, no un screenshot ganador.

## Ballenas: confluencia frente a coordinación

FOMO facilita perfiles, posiciones, alertas y tesis públicas. Una compra común
puede deberse a información compartida, copia, una tendencia o coordinación;
los datos actuales no permiten escoger esa causa ni leer conversaciones privadas.
En r2 se registra coincidencia BUY de FartmanSacks/unipcs sobre el contrato y
cadena exactos en <=180 s. Se conserva que ambas son alertas no verificadas por
recibo on-chain. Una transferencia o airdrop no se considera compra.

Las alertas llegan tarde y el feed de la app puede omitir pequeñas operaciones.
Un historial ganador del líder no reconstruye nuestros precios de entrada ni
nuestro resultado. Estudiar solo los éxitos del top sería sesgo de selección.

## Cambios aplicados en WHALE DEMO r2

1. Respaldo GeckoTerminal para Robinhood cuando DEX no cotiza; identidad exacta,
   precio del lado correcto del pool y liquidez >=10000 USD. Datos con fuente y
   motivo explícito de cada descarte. No repetir compras históricas descartadas.
2. Contexto OHLCV 1m cerrado para entradas del respaldo, con edad/stale y hasta
   cinco velas; no modifica la regla de entrada ni supone velas disponibles.
3. Coincidencia temporal observada de los dos perfiles, sin añadir compras ni
   sumar carteras ni marcar las señales como transacciones verificadas.
4. Costes multiplicados igual que V10 y reserva del 50% de beneficio realizado.
   Con 1% comisión y 2% slippage por lado, el break-even bruto es aproximadamente
   +6.18%; una ida y vuelta a precio plano pierde aproximadamente 5.82%.

EARLY/IMPULSO mantienen su código y estados. No se rebajan costes para fabricar
beneficios ni se reinicia capital. El respaldo nuevo está probado sin red;
conexión/cobertura real deben confirmarse en una run con este cambio.

## Cómo juzgar el siguiente tramo

Registrar entradas/cierres netos, cobertura de cotización, retrasos, velas,
coincidencias y descartes. Separar cada cartera, versión de entrada y huecos
entre runs. No afirmar que un ajuste funciona con una operación ganadora.
La prioridad inmediata es cobertura y continuidad, antes de optimizar umbrales.
No hay garantía de beneficio ni órdenes reales.

Fuentes primarias:
- https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/dashboard-overview
- https://docs.dexscreener.com/api/reference
- https://apiguide.geckoterminal.com/ y https://apiguide.geckoterminal.com/faq
- https://fomo.family/blog/learn/what-is-copy-trading
- https://fomoapi.io/docs
