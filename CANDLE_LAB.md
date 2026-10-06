# LAB VELAS r1 — 6 octubre 2026

Prueba prospectiva exclusivamente virtual. No modifica los balances, posiciones,
reservas, historial ni bloqueo capital-r1 de V10 EARLY/IMPULSO históricas.
WHALE DEMO permanece separado. No hay órdenes reales.

## Comparación

Cuatro libros nuevos, cada uno con 100 EUR FICTICIOS, sin trasladar dinero ni
reiniciar los libros históricos:
- LAB EARLY CONTROL: EARLY r4 actual.
- LAB EARLY VELAS: EARLY r4 + candle-r1.
- LAB IMPULSE CONTROL: IMPULSO r4 actual.
- LAB IMPULSE VELAS: IMPULSO r4 + candle-r1.

Todos reutilizan el mismo simulador: hasta 10 EUR/entrada, 3 abiertas, costes
multiplicativos 1% comisión + 2% deslizamiento por lado, FX fijo 1:1,
reserva 50% de beneficios realizados, mismos stops/parciales/trailing/24h y
freno capital-r1. Ningún libro se suma a otro. Las nuevas referencias de 100 EUR
son experimentos distintos; no recuperan ni borran pérdidas históricas.

Cada lectura usa el mismo ranking y caché de precios. El guard adicional se
evalúa solamente después de superar las reglas actuales y antes de comprar.
Los contextos OHLCV se comparten por contrato/cadena/par durante esa lectura.
Las limitaciones de efectivo, posiciones y tokens ya operados hacen que los
brazos puedan comprar tokens distintos: comparar carteras y, además, señales
con la misma identidad/hora; no atribuir toda diferencia al filtro.

## Hipótesis candle-r1

GeckoTerminal OHLCV del PAR EXACTO, validando antes cadena, contrato y par.
Solana conserva mayúsculas; EVM compara direcciones sin distinción de caso.
Se pide el token exacto y USD; nunca se usa el precio del activo contraparte.
Fuentes: https://apiguide.geckoterminal.com/faq y
https://api.geckoterminal.com/docs/index.html .

Se requieren cinco velas de un minuto cerradas, consecutivas, OHLC válidos,
sin anticipar una vela aún abierta. Última vela terminada hace <=90 segundos.
Las últimas dos deben ser verdes, con cierre más alto en la segunda;
su volumen medio debe superar al menos 10% la media de las tres anteriores,
con volumen positivo en ambas. La mecha superior de la última no puede
superar 40% del rango. Son umbrales experimentales, no rentabilidad demostrada.
Se comparan intervalos de volumen distintos, sin confundirlo con flujo neto comprador.

Sin velas, errores, 429, cadena no soportada, pool distinto o datos antiguos:
VELAS rechaza; CONTROL mantiene reglas actuales y registra la falta de cobertura.
Así, menos operaciones por falta de API no se presenta como mejor selección.
Tope global del laboratorio: 6 solicitudes en 60 segundos, timeout 5s cada una.
No se fuerza una consulta fuera del presupuesto. Con dos lectores WHALE de
hasta 10/min cada uno, se reserva margen sobre las 30/min publicadas.
La cobertura es parcial y favorece los primeros candidatos elegibles del ranking;
no se afirma revisar todas las velas del mercado.

## Auditoría y revisión

Cada entrada guarda entry_candle_context, entry_experiment y sufijo de política.
LAB OHLCV registra fuente, identidad, velas utilizadas, medias, mecha y descarte.
fomo_lab_candle_audit_r1.json conserva las últimas 1000 decisiones de entrada;
LAB COBERTURA resume PASA/RECHAZA/SIN DATOS (evaluaciones, no tokens únicos).
Los cuatro libros y auditoría se guardan con la memoria entre runs.
Las salidas se ejecutan aunque el libro esté bloqueado o falten velas nuevas.
No se recalculan operaciones antiguas ni se promete recuperar pérdidas.

Revisar por libro: operaciones completas (sumar parcial y cierre por posición),
beneficio neto, drawdown, stops y ganancias omitidas con datos disponibles;
separar ausencia de cobertura de rechazo por vela. Unos pocos trades o ausencia
de compras no prueban mejora. La pausa de V10 históricas no se levanta aquí.

## Validación

12 tests sin red añadidos: exclusión de vela abierta, huecos/frescura, volumen,
mechas, OHLC inválido, identidad de pool/contrato/case Solana, token de consulta,
caché por lectura, errores y presupuesto, guard con datos ausentes,
persistencia/costes/separación de cuatro libros y salidas con bloqueo.
El workflow ejecuta estos tests antes del laboratorio. Solo habilita
BRAIN_CANDLE_LAB si pasan; su fallo deja el laboratorio deshabilitado y permite
continuar las V10 históricas y WHALE. Tests V10 y WHALE existentes se mantienen.
En la preparación el entorno Python local estaba indisponible: no afirmar
tests aprobados hasta verificar el resultado de GitHub Actions.
