# Salidas escalonadas: experimento virtual r1

Dos carteras nuevas, CONTROL y STAGED, de 100 EUR virtuales cada una, creadas una sola vez. No sumarlas ni confundirlas con el historial anterior. Cada entrada usa hasta 5 EUR y las reglas EARLY + VELAS actuales, edad 2–60 minutos. No heredan M4 ni borran las pérdidas de las otras carteras.

CONTROL conserva la política actual: stop neto -15%, vender 50% al +30%, trailing -15% desde el pico posterior y plazo 24 horas. STAGED usa stop neto -15%, vende 50% del original al +15%, 25% al +30% y el restante al +45%; tras TP1 cierra el resto si el retorno neto de su coste asignado cae a +2% o menos. Conserva el plazo 24 horas. Son umbrales de prueba elegidos para este experimento, no reglas verificadas de F-INVEST.

Cada venta aplica el modelo existente de 1% de comisión y 2% de deslizamiento por lado, FX 1:1, sin gas/MEV. Reserva 50% de beneficios positivos de cada venta. Los saltos de precio se venden al precio observado, nunca al objetivo histórico; si se cruzan TP1 y TP2 de golpe se vende 75% una sola vez. +2% es un disparador, no una garantía de ejecución.

Mismas reglas de entrada y ranking, pero no entradas o precios idénticos garantizados: pueden divergir por cotizaciones, efectivo, posiciones y frenos. La comparación de carteras mide el conjunto; para atribuir un efecto solo a las salidas, comparar posiciones coincidentes por contrato y momento de entrada. Guardar también entradas exclusivas de cada brazo. No presentar TP1 o cada venta parcial como una posición ganadora; agrupar todas las ventas hasta el cierre completo.

Se publican patrimonio, cambio desde 100, realizado, posiciones completas, ganadoras, abiertas y valoraciones desconocidas. Si faltan cotizaciones, patrimonio y ventaja quedan desconocidos. Acumular una muestra de posiciones completas y revisar pérdidas, costes y estabilidad antes de adoptar. Vigilancia durante las runs, sin continuidad garantizada entre ellas. No hay órdenes reales.

Los tres archivos targets se recuperan y guardan en fomo-memory. Si desaparece solo una cartera o el marcador se rechaza el reinicio; restaurar el estado. La variante solo puede activarse en su archivo autorizado. Pruebas offline verifican contabilidad, huecos, cotizaciones ausentes e aislamiento; no demuestran rentabilidad futura.
