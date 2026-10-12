# Prueba prospectiva de continuación — 12 octubre 2026

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

