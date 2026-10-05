# WHALE DEMO r1 — experimento virtual prospectivo

Perfil seleccionado por el usuario: [FartmanSacks](https://fomo.family/profile/FartmanSacks).
Fuente: [FomoAPI, proveedor independiente y no oficial](https://fomoapi.io/docs),
WebSocket público `/ws/alerts?trader=FartmanSacks`, sin clave ni suscripción.
Según su documentación, la demo tiene 60 segundos de retraso; se registra el
retraso observado y el `welcome` cuando existe. La conexión efectiva se debe
confirmar en los logs: instalar el lector no demuestra que haya señales.

## Qué mide

Cartera separada de 100 EUR virtuales; entradas fijas de 10 EUR, máximo tres
posiciones. No se suma con EARLY/IMPULSO, que conservan sus reglas.
Solo alertas BUY/SELL posteriores al inicio de la sesión y con antigüedad
máxima 180 segundos. Se excluyen transferencias, tesis, otras cuentas, eventos
sin ids/contrato/cadena y replay histórico. Se deduplica por `eventId`; se fija
el primer `userId` y se rechaza otro id aunque tenga el mismo nombre.
No se reconstruye el beneficio de la captura ni se compra retrospectivamente.
La atribución al perfil depende del proveedor: **no hay recibo de transacción
ni wallet verificada**, y no se incorpora a la confluencia verificada del Brain.

Se cotiza por contrato y cadena exactos en DEX Screener, usando el par de mayor
liquidez entre los que tienen al menos 10000 USD. Sin mercado admisible se
descarta, sin inventar precio. No usa los filtros de edad, capitalización o
ranking de EARLY/IMPULSO: es un experimento distinto de seguimiento de señales.
Soporta Robinhood, Solana, Ethereum, BSC y Base; otras cadenas se descartan.

Compra al precio observado al recibir/procesar la alerta, no al precio de la
ballena. Comisión 1% y deslizamiento 2% por lado; FX fijo USD/EUR 1:1, sin gas
ni MEV. Una venta del perfil modela cierre completo de nuestra posición: **no
sabemos si la ballena vendió todo o solo una parte**. Stop neto -15% y trailing
-15% del máximo tras observar +30% neto, evaluados en lecturas de ~60 segundos.
Los stops no garantizan ese precio. Sin cotización, permanece abierta, la
valoración se declara incompleta y se pausan entradas nuevas.

El lector corre en paralelo durante cada sesión del workflow y termina con
el Brain. Hay huecos entre runs; no es vigilancia continua ni captura todos
los swaps. El proveedor señala que el feed de la app puede omitir operaciones
pequeñas. La demo retrasada no equivale al stream on-chain de pago.

## Persistencia y diagnóstico

Estado en `fomo_paper_whale.json`, guardado junto a las memorias existentes.
Se conservan como máximo 1000 alertas, 1000 cierres y 10000 ids de deduplicación;
caja y realizado acumulado no se reinician al recortar el historial.
Logs `WHALE FEED`, `WHALE ALERTA`, `WHALE DESCARTE`, `WHALE VIRTUAL` y resumen
con patrimonio contable, realizado, posiciones y valoración verificable.
Cero alertas con feed inaccesible no significa que el trader no haya operado.

Pruebas sin red: `python -m unittest test_whale_paper.py test_fomo_v8.py`.
No hay claves de wallet, firmas, órdenes reales ni endpoints de trading.
Evaluar múltiples operaciones después de costes y retrasos; esta prueba no
implica que seguir al número uno de un día mejore el resultado.
