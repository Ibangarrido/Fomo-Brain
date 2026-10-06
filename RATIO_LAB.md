# LAB RATIO r1 — simulación prospectiva
Compara exclusivamente compras/(compras+ventas) en cinco minutos: mínimo 60% frente a 52%.
Cuatro carteras nuevas y separadas, 100 EUR ficticios cada una:
- fomo_lab_ratio_early_60_r1.json
- fomo_lab_ratio_early_52_r1.json
- fomo_lab_ratio_impulse_60_r1.json
- fomo_lab_ratio_impulse_52_r1.json

No sumar carteras. No reinicia V10 histórica ni LAB VELAS r1. No ejecuta órdenes reales.
Las dos variantes usan las reglas EARLY/IMPULSO existentes, confirmación 30–90s, límites de momentum, precio, volumen y liquidez, score y descubrimiento existentes; no añaden el filtro OHLCV.
Costes: comisión 1% y deslizamiento 2% multiplicados por lado; sin gas ni MEV; cambio EUR/USD fijo 1:1. Máximo 10 EUR, tres posiciones, misma gestión de pérdidas, parcial y reserva.
52% es una hipótesis inicial, no un valor optimizado ni una garantía de beneficios.
El score mantiene su cálculo histórico: bajar el umbral de entrada no rebaja el mínimo de score. Son reglas comunes a ambos brazos.
Se registran umbral, versión y modo por cartera y posición, además de precio, ratio observado, confirmación, rechazos y patrimonio. No permite reutilizar una cartera con otro umbral.
Cada cartera toma decisiones independientemente; capacidad, efectivo y tokens ya operados pueden divergir. Comparar identidad y hora de señales, operaciones cerradas tras costes, drawdown y abiertas por separado; incluir fallos, no solo UP.
Usa el radar compartido y cotizaciones cacheadas dentro de cada ciclo. Las lecturas de 1 minuto tienen huecos entre runs; los precios/fills son estimados.
BRAIN_RATIO_LAB activa la prueba solo si pasan sus tests. Un fallo desactiva este laboratorio y se informa sin borrar el historial.
No atribuir operaciones anteriores a este cambio. Las runs ya creadas conservan su commit anterior.

## Gestión de riesgo capital-r2
Desde el primer ciclo con esta política, nuevas entradas de hasta 5 EUR y pausa de 60 minutos tras dos posiciones completas consecutivas perdedoras en la última hora. Se aplica igual a ambos porcentajes y a LAB VELAS/V10; ballenas conserva su política DEMO. Las posiciones existentes conservan cantidad e importe; no se reinicia ninguna cartera. El stop neto −15%, parcial +30%, trailing y costes siguen iguales. Reducir importe reduce exposición, no mejora por sí solo la ventaja de las señales. El stop puede excederse entre lecturas; se registra resultado neto, máximo neto observado, intervalo desde la cotización anterior y exceso sobre −15%.

Las carteras registran risk_policy_history con fecha y saldo/realizado de transición, y cada entrada/salida y observación etiqueta su política. Separar resultados anteriores y posteriores; las operaciones heredadas conservan entry_risk_policy_version ausente o anterior. No atribuirlas al ajuste. No comparar importes brutos de periodos con tamaño de operación distinto como si fuese una mejora de rentabilidad.
