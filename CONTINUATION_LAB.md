# Prueba prospectiva de continuación — 12 octubre 2026

## Consultas agrupadas de confirmación

Antes de evaluar los brazos de continuación, el motor consulta hasta 20
candidatos, agrupados por cadena y en lotes de hasta 10 pares exactos; máximo
dos peticiones de precarga por ciclo. La API de
DEX Screener admite uno o varios pares. Solo se precargan respuestas que coincidan
en cadena, pool y contrato base, con precio positivo, liquidez mínima y recepción
local verificable de menos de 3s. Duplicados contradictorios no se precargan.
Se conserva la hora y reloj monotónico de la respuesta original, sin inventar
una nueva recepción. El TTL original de 3s y las cachés por hilo se mantienen.

La precarga utiliza callbacks y cachés del motor en ejecución (también cuando
se lanza como __main__), no una segunda instancia importada. No cambia los
filtros de entrada ni el requisito de dos lecturas en 30–90s. Tras las consultas
de seguridad se invalida la cotización individual y se pide de nuevo, igual que
antes. Respuestas parciales, errores HTTP, expiración o falta de coincidencia
conservan la consulta individual como respaldo. El watchdog de salidas no recibe
datos de la caché del hilo de entradas. No se conecta la API CoinGecko ni se
calcula flujo por importe con datos de número de operaciones.

El log ENTRADAS BATCH permite medir peticiones, pares precargados, errores y
latencia. La reducción de llamadas está validada con datos sintéticos; verificar
en las siguientes runs tanto coste de precarga como tiempo total y motivos de
renovación. No se presupone menor latencia en todas las condiciones ni mejora
de rentabilidad. Fuente: https://docs.dexscreener.com/api/reference.

## Diagnóstico de confirmación

Se registra `confirmation_audit` (máximo 150 muestras por cartera) con motivo
exacto de renovación: IDENTITY_CHANGED, REFERENCE_EXPIRED_OR_INVALID,
PRICE_DRIFT_GT_5PCT o PRICE_DRIFT_UNKNOWN. También distingue FIRST_READ,
INVALID_FRESH_RECEIPT y REFERENCE_AVAILABLE. Este último solo significa que
existe referencia, no que la confirmación temporal o la entrada haya pasado.
Registrar antigüedad de recepción de ambas lecturas, distancia temporal y
variación de precio; provider_market_age sigue desconocido. El registro no
cambia ninguna decisión ni amplía la ventana de 30–90s o el límite del 5%.

La documentación oficial de DEX Screener permite consulta de uno o varios
pares (https://docs.dexscreener.com/api/reference); podría reducir llamadas
duplicadas. La documentación de GeckoTerminal declara caché de un minuto
(https://api.geckoterminal.com/docs/index.html). Ninguna permite deducir que dos
peticiones rápidas son dos precios nuevos del proveedor. Antes de acortar el
intervalo o integrar consultas agrupadas, medir qué proporción de renovaciones
proviene de caducidad, cambio de par o drift real. Las edades del ranking en los
logs no son edades de las cotizaciones frescas usadas para confirmar.

## Corrección de solapamiento r2

La revisión adicional por fotogramas de ALON (11 octubre 15:47:21) y SpaceXSI
(11 octubre 15:51:20) muestra caídas y recuperaciones que motivan revisar cómo
se evalúan los patrones. No confirma su rentabilidad ni reconstruye OHLCV exacto.

Se encontró un error reproducible: el clasificador descriptivo da prioridad a
BREAKOUT_WITH_VOLUME frente a PULLBACK_RECLAIM_WITH_VOLUME. Una recuperación
válida que cierre sobre todos los máximos anteriores recibe la primera etiqueta,
y el guard antiguo la descarta. El guard r2 comprueba directamente los mismos
predicados originales de retroceso (1–20%, vela previa roja, recuperación sobre
su máximo, soporte, impulso previo, volumen y mecha), con independencia de esa
etiqueta descriptiva. Si no los cumple, solo el brazo adicional puede evaluar
la ruptura tras pausa. No se cambian los umbrales para conseguir el nuevo pase.

Todos los brazos de continuación que usan ese guard reciben la corrección;
el control EARLY al 75% conserva su lógica. El registro data_policy_history pasa
a continuation-quote-r2 con candle_guard_version pullback-overlap-r2, preservando
hora, caja y posiciones del cambio. Los sufijos de entrada identifican r2.
Las memorias, salidas y presupuestos se conservan; no se reinician saldos.
Pruebas sintéticas verifican el solapamiento y los rechazos por soporte perdido,
retroceso excesivo, volumen insuficiente, mecha y velas antiguas; no prueban
resultados de mercado. Separar las observaciones antes/después de esta versión.

## Comparación adicional de patrones: ruptura tras pausa

Se añaden `pattern_pullback` y `pattern_breakout`, dos carteras PAPER de 100 EUR
desde el mismo instante. Las tres carteras anteriores conservan todo su estado.
Ambas nuevas usan ratio por número de compras del 50%, la misma confirmación,
liquidez, seguridad, importe máximo de 5 EUR y salidas. La primera usa el patrón
de retroceso existente; la segunda permite también una ruptura tras pausa.
No sumar saldos. Comparar únicamente estas dos desde su marcador común.

Hipótesis visual procedente de cuatro grabaciones revisadas por fotogramas:
CLAWHUNTER (11 octubre 16:16:57), CAESAR (12 octubre 08:35:50), WORMPAD
(12 octubre 12:10:20) y OVERDRIVE (12 octubre 13:28:03). CAESAR y CLAWHUNTER
muestran impulso seguido de pausa y nuevos intentos de subida. WORMPAD cae
mientras mantiene un porcentaje 1h muy positivo. OVERDRIVE pasa de una posición
visible de 8.08 USD a 6.85 USD dentro de la grabación. Estos casos están elegidos
por el usuario y no proporcionan prueba estadística, costes ejecutables ni OHLCV
exacto. No se reconstruyen velas ni volumen numérico a partir de los píxeles.

La alternativa requiere cinco velas 1m cerradas consecutivas, recientes y del
pool verificado. Impulso entre los dos primeros cierres del 2–20%, mínimo no
decreciente; las dos velas siguientes forman una pausa de amplitud <=8%, con
soporte por encima del primer cierre y volumen de la última pausa <=volumen de
la vela impulsiva. La ruptura cierra por encima de todos los máximos anteriores,
mantiene soporte, tiene volumen >=1.2x media de las tres primeras velas y mecha
superior <=40%. El precio nuevo debe seguir sobre el nivel roto y <=5% por encima
del cierre. Los números son parámetros experimentales, no medidas extraídas
de los vídeos ni umbrales de rentabilidad conocidos.

Inicializar ambas juntas; empezar decisiones en el ciclo siguiente. Si falta
parte de su memoria, fallar sin reiniciar. El watchdog incluye sus posiciones;
el workflow conserva sus tres archivos. No se amplía la API GMGN ni se resuelve
con este cambio el HTTPError del descubridor. Sin OHLCV válido, no comprar.

Fuente técnica para el formato OHLCV y la caché de datos (no para validar la
hipótesis): https://api.geckoterminal.com/docs/index.html. La API pública declara
caché de un minuto; una recepción reciente no acredita precio ejecutable.

Tres carteras virtuales independientes de 100 EUR desde el mismo instante: control EARLY al 75%, continuación al 50% y continuación al 60%. Nunca sumar sus saldos. RECOVERY, sus posiciones y M4 no se reinician ni se modifican por este laboratorio.

## Problema observado
CAESAR fue detectada en run 794: ratio de compras 54–61%, subida 1h >150%, después momentum 5m negativo. Bajar solo el ratio no permite entrar. Blue también estaba por encima del techo de momentum, y mostraba ventas por importe superiores a compras. Son casos elegidos después de su subida, no evidencia de ventaja estadística.

## Política nueva
Solo en las carteras CONTINUATION: sin veto de subida 1h ni requisito momentum5m 2–60%; edad del par 2–1440m, liquidez >=20000 USD y >=40 operaciones/5m. Ratio por número >=50% o >=60%. No se atribuye flujo monetario a este ratio: la fuente de Brain no separa importes de compras y ventas.

Exigir cinco velas consecutivas de un minuto cerradas y recientes del mismo contrato/pool, impulso previo, retroceso 1–20%, vela de recuperación que cierre por encima del máximo de la vela roja precedente sin perder su mínimo, volumen >=1.2x media previa y >=volumen de la vela roja, mecha superior <=40%. El patrón BREAKOUT aislado no basta. El precio recién leído debe conservar el máximo recuperado y no superar en >5% el cierre de recuperación.

Primera observación no compra; confirmar con lectura independiente del mismo contrato/pool en 30–90s. Cambios >5% renuevan la referencia y esperan. Mantener liquidez >=95% de la referencia. Comprobaciones de seguridad, comisión, precio tras seguridad y freno de cartera siguen activas. Una entrada máxima de 5 EUR, máximo tres posiciones, mismos stops/parciales y reparto de beneficios; sin reentradas. Precio, FX, deslizamiento y costes son los supuestos del motor de paper trading, no órdenes ni rendimiento ejecutable.

## Interpretación
50 vs 60 cambia solo el ratio. Control vs continuación cambia varias condiciones y permite comparar estrategias completas, no atribuir causalidad a un solo filtro. Registrar descartes, posiciones, salidas, patrimonio, cotizaciones desconocidas y timestamps. Sin velas verificables no hay entrada. El reloj de salidas tiene un objetivo, no garantiza periodicidad ni ejecución. Sin datos separados por importe no se asegura flujo comprador positivo.

Blue se añade a la cobertura por contrato junto con CAESAR, MissBean, NOCKAI y Grok Bot. Esto no conecta la API personal GMGN; continúa pendiente.

El workflow restaura y guarda las cuatro memorias del laboratorio. Si falta solo parte del estado, no reiniciar. Inicializar las tres carteras y empezar decisiones en el ciclo siguiente. Validación offline con escenarios sintéticos verifica comportamiento, no beneficios futuros. Evaluar prospectivamente también casos perdedores y ausencias de datos antes de adoptar la estrategia en RECOVERY.

