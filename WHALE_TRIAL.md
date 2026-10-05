# WHALE DEMO r2 — experimento virtual prospectivo

Perfiles seleccionados por el usuario: [FartmanSacks](https://fomo.family/profile/FartmanSacks)
y [unipcs](https://fomo.family/profile/unipcs). Cada uno tiene su propia cartera
de 100 EUR virtuales y su lector; no se suman. `WHALE_TRADER=unipcs` selecciona
el segundo y escribe `fomo_paper_whale_unipcs.json`. Por defecto se mantiene
FartmanSacks y su estado existente. Se rechaza un estado de otro perfil.
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
liquidez entre los que tienen al menos 10000 USD. Para Robinhood, cuando DEX no
responde o no ofrece un mercado admisible, se consulta GeckoTerminal
(`/networks/robinhood/tokens/{address}/pools`). Se verifica el contrato en la
relación base/quote y se toma el precio de ese lado, no el de WETH. Se conserva
proveedor y liquidez. Máximo 10 consultas/minuto por lector a GeckoTerminal
(20 entre ambos). Si se agota el presupuesto se declara indisponible, sin
insistir ni inventar precio. La conexión y cobertura efectiva de este respaldo
aún se deben verificar en una run nueva. Sin mercado admisible se
descarta, sin inventar precio. No usa los filtros de edad, capitalización o
ranking de EARLY/IMPULSO: es un experimento distinto de seguimiento de señales.
Soporta Robinhood, Solana, Ethereum, BSC y Base; otras cadenas se descartan.

Compra al precio observado al recibir/procesar la alerta, no al precio de la
ballena. Comisión 1% y deslizamiento 2% por lado, multiplicados igual que V10
(compra 1.01*1.02, venta .99*.98); FX fijo USD/EUR 1:1, sin gas
ni MEV. El 50% de cada beneficio realizado pasa a reserva y no se reinvierte;
el patrimonio incluye esa reserva. Se conserva la fórmula anterior en
posiciones antiguas, si las hubiera, y no se recalculan cierres anteriores. Una venta del perfil modela cierre completo de nuestra posición: **no
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


## Contexto de entrada añadido en r2

Las compras cotizadas por GeckoTerminal guardan hasta cinco velas de un minuto
cerradas: OHLCV, cuerpo, mecha superior y edad. Se excluye la vela aún abierta;
se marca stale si la última tiene más de 180 segundos. Un fallo de OHLCV se
registra; no se convierte en un precio ni altera la compra. Estas velas son
**contexto para estudiar**, todavía no un filtro nuevo ni prueba de ventaja.

Se buscan compras del otro perfil del mismo contrato/cadena en una ventana de
180 segundos. Se exige id de usuario distinto y se registra la coincidencia,
incluso si una señal no pudo cotizarse. Ambas siguen siendo alertas de proveedor
no verificadas on-chain: no demuestra comunicación, independencia de wallets,
coordinación privada ni demanda genuina. No modifica las reglas de compra.

Cada alerta imprime cadena, contrato, fuente y motivo concreto del descarte,
además de conservarlos en el estado. El contador `eventos` es el historial
retenido, no el número de operaciones de esa sesión.

Fuentes: https://apiguide.geckoterminal.com/ y
https://apiguide.geckoterminal.com/faq ; esquema de alertas:
https://fomoapi.io/docs .
