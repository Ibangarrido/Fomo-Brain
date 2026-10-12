# Estudio de entradas en memes — 12 de octubre de 2026

## Conclusión

El primer bloqueo comprobado es la cobertura. MissBean, NOCKAI, Grok Bot y CAESAR no aparecieron en los logs ni en los 41 archivos de las ejecuciones 792 y 793 (datos hasta 08:42 Europe/Madrid). Antes de atribuir oportunidades perdidas al 75%, hay que distinguir monedas no descubiertas, descartes de mercado, falta de velas, seguridad, confirmación y restricciones de cartera.

## Casos observados

| Caso | Evidencia observada | Implicación |
|---|---|---|
| MissBean, Solana | Vídeo 07:55–07:59: MC aproximada 125.2k →102.5k →130.6k →121k. GMGN alrededor de 08:04 mostraba caída 5m cercana a 26%, con más dinero vendido que comprado. | Un rebote verde aislado no confirma recuperación. |
| NOCKAI, Robinhood | Capturas: MC145.5k →222.6k. Vídeo posterior de 83.7s:236.1k →150.8k. Una lectura5m:48 compras/55 ventas, pero11.8k USD comprado/6.1k vendido. | Cantidad de operaciones e importe dan señales distintas. La caída posterior ronda36%; no atribuir53% visible a una estrategia. |
| Grok Bot, BSC | GMGN08:34:135 compras/56 ventas (~70.7%), +14%5m/+176%1h;3% impuesto mostrado por lado; pool contra SPCXB. | Continuación posible como hipótesis, pero incumple75% y150%; falta cotización ejecutable de salida y costes completos. |
| CAESAR, Solana | Vídeo08:36–08:37:1015 compras/816 ventas (~55.4%), liquidez mostrada18.8k USD; sucesivos retrocesos y máximos. GMGN08:40:flujo casi equilibrado,5m terminó negativo. | La liquidez también bloquea lecturas tempranas. No retirar el filtro de subida para perseguir un pico. |

Datos retrospectivos, fuentes y ventanas diferentes. No son historial íntegro OHLCV ni prueba de rentabilidad. MC es capitalización, no dinero recuperable.

## Código comprobado

La búsqueda usa términos genéricos y perfiles recientes de DEX Screener. No cubre todos los lanzamientos. La sesión tiene15 ciclos y ventana de15 minutos; puede haber cola, demora o huecos entre ejecuciones. EARLY confirmado exige, entre otros, ratio configurado75% en RECOVERY, liquidez20k USD,40 operaciones5m, edad de par2–60min, cambio5m2–60%, subida1h<=150%, crecimiento entre lecturas1–12% y confirmación30–90s. El filtro de velas actual exige dos velas verdes cerradas; el diagnóstico de patrones no cambia ese filtro.

DEX Screener aporta conteos y volumen total. Es imposible calcular importes separados de compras/ventas a partir de esos campos. Acceso de navegador a GMGN no es ingestión API. Su preflight seguía MISSING_API_KEY.

## Cambio ejecutado: cobertura y diagnóstico independiente

Añadidos los cuatro contratos exactos al seguimiento manual existente. La consulta por contrato ocurre aunque la moneda no aparezca por búsqueda genérica. Si falta cotización, se registra NO_QUOTE_THIS_CYCLE; no se inventa un precio o un descarte de entrada.

Por ciclo se registra cobertura de los cuatro. El estudio de velas rota un contrato por minuto como máximo, después de las decisiones de cartera, con el presupuesto OHLCV compartido existente. Usa el mismo contrato, cadena y pool con verificación en candle_lab. Los patrones se observan aunque liquidez o ratio bloqueen la entrada. Error, hueco o proveedor no disponible se conserva como SIN DATOS.

Comparación informativa del ratio50/60/75 sobre la misma lectura; no indica elegibilidad completa. Importes comprador/vendedor quedan UNKNOWN hasta disponer de fuente válida. Últimos120 registros persistidos en el artefacto de oportunidades existente. No se altera efectivo, histórico, tamaño, stops ni la política75% de RECOVERY. Casos enviados tras la subida continúan separados de la cohorte automática.

## Siguientes mejoras, por orden

1. Medir cobertura y demora: primer dato recibido, primer patrón válido, cada bloqueo independiente y tiempo hasta decisión. Consultar contratos no garantiza respuesta del proveedor.
2. Integrar la API de solo lectura o una fuente autorizada de transacciones: importes5m, concentración, holders, costes y reservas. Validar identidad, ventana temporal, unidades, duplicados y frescura; no usar paneles del navegador como feed de trading.
3. Probar una cartera virtual separada de CONTINUACIÓN junto a CONTROL. Hipótesis: retroceso ordenado, recuperación de su máximo con vela cerrada y volumen mayor, flujo monetario positivo y liquidez estable. Comparar50/60/75 y exigir los demás controles. No modificar a la vez ratio, edad, límite de subida y salidas: impediría atribuir resultados.
4. Comparar salida por pérdida de mínimo reciente frente al trailing actual, con cotización posterior a la señal. Un stop solicitado no garantiza precio, especialmente con caídas36%/80s.
5. Evaluar todas las señales prospectivas, incluidas pérdidas y casos sin salida verificable. Registrar máximo avance/retroceso, retornos1/3/5min, costes, demoras y cobertura. Las ganancias de vídeos seleccionados no bastan.

## Validación

195 pruebas offline superadas. Regresiones nuevas: contratos consultables sin cotización previa, patrones de tokens descartados, rotación limitada y resultados desconocidos ante fallo, dirección EVM con distinta capitalización sin mezclar cadenas. No hay órdenes reales ni rentabilidad garantizada.

Referencia oficial GMGN:
https://docs.gmgn.ai/index/gmgn-agent-api
