# FOMO Brain — auditoría de integraciones y plan 24/7 (2026-10-26)

## Alcance y autorización

Proyecto de investigación de mercados y PAPER trading. **No usar bots, scraping, endpoints internos ni sesiones autenticadas de FOMO**: sus términos restringen la extracción y la interacción automatizadas sin permiso escrito. Si se pretende acceder a datos propios de FOMO, solicitar una licencia o API oficial por escrito; de lo contrario usar proveedores de datos on-chain independientes y autorizados. No habilitar swaps, claves privadas ni operaciones con dinero real.

## Diagnóstico verificado el 26-10-2026

- GitHub Actions: el evento `workflow_dispatch` no equivale a `schedule`. En los 100 runs recientes consultados había 55 manuales, 37 `push` y 8 `schedule`; varias ejecuciones manuales figuraban pendientes. No interpretar un run `success` como evidencia de datos de mercado válidos.
- Run programado `40273457356` (26-10-2026): los tres jobs terminaron en `success`, pero el log de `analyze` registró `DISCOVERY WATCH UNAVAILABLE:HTTPError 0 pools`, y tres observaciones de velas quedaron sin datos por HTTP 429. El job GMGN registró `MISSING_API_KEY` y cartera virtual de 100 EUR sin entradas. En `cooker_watch`, run `40274005850`: `HISTORY_GAP_CURSOR_RETAINED`, cero eventos nuevos; no significa ausencia de transacciones.
- La clasificación de salud por fuente se implementa en `source_health.py`, con pruebas offline en `test_source_health.py`. Los workflows publican artefactos de diagnóstico por fuente. Esta instrumentación **no repara la fuente**, no genera señales ni cambia las carteras.
- Las métricas de resultados de estrategia y de cotizaciones ejecutables siguen sin validar; no atribuir rentabilidad a patrones o precios indicativos.

## Fuentes oficiales y prioridad

| Prioridad | Fuente | Qué aporta | Requisitos / riesgo |
| --- | --- | --- | --- |
| P0 | DEX Screener API | Descubrimiento, pares Solana/BSC, precio, volumen y liquidez; ya integrado en V13 | Endpoint de búsqueda y pares: 300 req/min; perfiles y promociones: 60 req/min. Un boost pagado NO equivale a demanda orgánica. Dedupe por cadena + pool + token y vigilar cambios de esquema. |
| P0 | GeckoTerminal API | Nuevos pools, series y reevaluación de descartes | API beta gratuita: 30 req/min (2 oct 2026). Ya hay fallos HTTP en producción; respetar Retry-After, backoff y fuente alternativa. No imputar cero si falla. |
| P1 | PumpPortal Data API | WebSocket de creación de tokens y migraciones de Pump.fun/PumpSwap | `subscribeNewToken` y `subscribeMigration` anunciados gratis; una sola conexión WS. El seguimiento de operaciones por token/wallet requiere API key y wallet con >=0.02 SOL; 0.01 SOL / 10.000 mensajes. Para PAPER evitar flujos de pago hasta presupuestarlos. Solo cubre parte del ecosistema. |
| P1 | GMGN Agent OpenAPI y gmgn-skills | Velas 1m-1d, seguridad, holders, wallets, ranking | API key legítima y validación de schema, unidad, timestamp, identidad de mint y coste. Bloqueado hoy por `MISSING_API_KEY`. No instalar herramientas de swap ni exponer llaves. Hay incidencias públicas sobre HTTP 429. |
| P2 | Helius Standard/Enhanced WSS | Eventos on-chain Solana, wallets y transacciones | Clave del proveedor, coste de créditos y filtrado; WSS estándar en Free, enhanced txSubscribe en Developer según actualización 31-03-2026. No captura BSC. |
| P2 | Birdeye Smart Money | Lista de tokens seguidos por smart money en Solana | Validar cobertura, precio del plan, rate limits y semántica; no asumir que copiar whales sea rentable. |

Fuentes:
- https://docs.dexscreener.com/api/reference
- https://support.coingecko.com/articles/6867086195-does-geckoterminal-have-an-api
- https://pumpportal.fun/data-api/real-time/
- https://docs.gmgn.ai/index/gmgn-agent-api
- https://github.com/GMGNAI/gmgn-skills
- https://github.com/GMGNAI/gmgn-skills/issues/224
- https://www.helius.dev/blog/laserstream-websockets
- https://docs.birdeye.so/changelog/20260206-release-megaeth-support-smart-money-api
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://production.fomo.family/terms

## Arquitectura propuesta

1. **Captura 24/7**: un worker persistente de solo lectura en VPS/servicio administrado (no un cron de GitHub) con un único WebSocket, reconexión con backoff y jitter, heartbeat, límites de costes, y persistencia de cursor/último evento. No desplegado aún.
2. **Normalización**: `chain_id`, mint, pool, dex, source, provider_time, received_at, payload_hash y error; no mezclar precios de distintas piscinas ni tratar una respuesta HTTP 200 como dato válido sin verificar schema.
3. **Almacenamiento**: SQLite WAL para prototipo o Postgres en producción, con claves únicas de evento, retención, backups y reanudación tras caída. Deduplicación y comprobación de gaps.
4. **Salud**: distinguir `HEALTHY`, `STALE`, `DEGRADED`, `UNAVAILABLE`, `AUTH_REQUIRED`, `NOT_OBSERVED` y `UNVALIDATED`. Alertar si el proveedor no entrega datos, incluso cuando el workflow finaliza `success`. `source_health.py` es una primera instrumentación offline, no un monitor autónomo.
5. **Señales prospectivas**: registrar todos los descartes y candidatos; medir cambios a 5/15/30/60 min con observaciones posteriores, latencia, liquidez, drawdown, rug pulls, concentración, spread y rutas de salida. Comparar cohortes sin sesgo de supervivencia.
6. **PAPER**: mantener cartera separada de 100 EUR, <=10 EUR por operación virtual, coste/slippage simulados, marca explícita de salida no verificable y sin órdenes reales. Comparar control vs experimental y exigir suficiente muestra fuera de entrenamiento antes de cambiar filtros.
7. **GitHub Actions**: mantener tests, auditoría y artefactos; no usarlo como streaming continuo. Reducir dispatches superpuestos; distinguir manuales y programados. Las ejecuciones programadas pueden retrasarse u omitirse.

## Nuevo módulo de salud

`python -m unittest -v test_source_health.py`

`python source_health.py --source geckoterminal --output source_health_gecko.json`

`python source_health.py --source gmgn --output source_health_gmgn.json`

`python source_health.py --source v13 --output source_health_v13.json`

`python source_health.py --source cooker --output source_health_cooker.json`

Los archivos de salud se generan a partir de reportes **locales**, sin conexión externa ni operaciones. Un estado `HEALTHY` confirma solo frescura y estructura del reporte de la fuente, no rentabilidad ni liquidez ejecutable. `--strict` permite usar exit code 2 en un monitor separado, pero por ahora los workflows conservan ejecución no bloqueante.

## Próximo hito recomendado

**P0: reparar los HTTP 429/HTTPError y validar continuidad del historial** antes de optimizar señales. Comprobar qué proveedor, código HTTP, Retry-After y tasa efectiva originan el fallo, sin imprimir credenciales; aplicar caché y backoff. P1: prototipo 24/7 PumpPortal **solo `subscribeNewToken` y `subscribeMigration`**, con almacenamiento persistente y comparación contra DEX Screener/GeckoTerminal durante siete días. No pagar por trades streaming ni habilitar swaps hasta demostrar cobertura, coste y fiabilidad. Después medir resultados PAPER netos y drawdowns, no solo máximos teóricos.
