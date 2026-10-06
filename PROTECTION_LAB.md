# LAB PROTECCIÓN r1 — prueba virtual prospectiva

EARLY e IMPULSO tienen cada uno dos brazos: CONTROL y PROTECT. Ambos se copian una sola vez de la cartera LAB RATIO 60% correspondiente, después de su ciclo; conservan efectivo, reserva, pérdidas, posiciones, tokens ya operados y frenos. No reciben otros 100 EUR ni borran historial. No sumar las copias. Los saldos iniciales pueden ser inferiores a 100 EUR.

El primer ciclo solo guarda la bifurcación; las decisiones empiezan en la siguiente lectura. protection_baseline registra fecha, fuente, patrimonio, realizado, efectivo, reserva y abiertas. Comparar el cambio respecto a esa base y separar posiciones heredadas de nuevas entradas; no atribuir las ganancias antiguas al experimento. Las cuatro carteras se persisten en el artefacto junto al marcador fomo_lab_protect_fork_r1.json. Si faltan carteras después de crear el experimento, se detiene este laboratorio y se pide restaurar el artefacto, sin reiniciar fondos.

Reglas comunes: compras 5m >=60%, EARLY/IMPULSO existentes, capital-r2 (nuevas entradas <=5 EUR, pausa tras dos posiciones completas perdedoras consecutivas en60min), stop neto−15%, parcial de50% al+30% neto, trailing−15%, comisión1% y deslizamiento2% multiplicados por lado, reserva50% del beneficio realizado positivo, FX1:1, sin gas ni MEV.

La única diferencia es PROTECT: una cotización verificable observada desde la activación con resultado neto >=+12% arma protección persistente. Si después el neto observado cae a <=+2%, cierra todo el resto al precio observado. El stop−15% conserva prioridad en una caída mayor; cotizaciones ausentes o sin liquidez suficiente no autorizan venta ni armado. Los máximos anteriores a la bifurcación no arman retroactivamente la protección. Después del parcial también puede proteger el resto.

+12%/+2% son hipótesis de prueba, no valores optimizados. La regla no garantiza cierre a+2%: entre lecturas puede cerrar por debajo o con pérdidas. No reconstruye compras o ventas pasadas. Una salida temprana puede evitar pérdidas o recortar ganadoras; comparar ambos casos, costes y abiertas. Las carteras originales 52/60 y V10 no reciben esta salida, y ballenas conserva su política.

BRAIN_PROTECT_LAB se activa si sus pruebas y las de ratio pasan. Lecturas de aproximadamente un minuto dentro de sesiones, con huecos entre runs. No ejecuta órdenes reales.
