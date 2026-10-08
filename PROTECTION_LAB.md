# LAB PROTECCIÓN r1 — prueba virtual prospectiva

## Comparación EARLY + VELAS — 8 octubre 2026

Dos brazos adicionales, `fomo_lab_protect_velas_control_r1.json` y
`fomo_lab_protect_velas_protect_r1.json`, se copian una sola vez de
`fomo_paper_v10_r3.json` cuando su valoración es completa. Conservan saldo,
reservas, posiciones, historial y frenos; no reciben capital nuevo. El marcador
`fomo_lab_protect_velas_fork_r1.json` impide reiniciar una comparación incompleta.
La primera lectura solo bifurca. Ambos brazos usan las mismas reglas EARLY y
el mismo filtro de velas; solo PROTECT activa la salida +12% -> +2% descrita abajo.
El watchdog revisa también ambas copias. Los tres archivos se guardan en el
artefacto y el registro muestra el cambio de patrimonio desde la bifurcación.
No sumar las carteras ni atribuirles ganancias anteriores; las oportunidades
futuras pueden diferir si una salida libera efectivo o cambia los frenos.

BUNBARA en la run 400 alcanzó +12,68% neto observado y salió a -16,63%
en EARLY + VELAS. Es la motivación del experimento, no una demostración de
que la protección habría salido a +2%. Los tests usan una trayectoria sintética,
no reproducen las cotizaciones históricas. La política original se conserva
como referencia y no se reescriben operaciones antiguas.

Fuentes de estudio:
- FINRA, riesgos de órdenes stop: https://syndication.finra.org/content/understanding-order-types-can-save-time-and-money
- CME, riesgo de ajustar un sistema a datos históricos: https://www.cmegroup.com/education/courses/trade-and-risk-management/system-based-vs-discretionary-trading

Estas fuentes no validan los umbrales +12%/+2% para memecoins. Comparar resultados
prospectivos netos, pérdidas, ganancias recortadas y cotizaciones desconocidas
antes de adoptar la política. Las simulaciones mantienen costes supuestos,
FX fijo y ausencia de gas/MEV; no prueban ejecución real.

EARLY e IMPULSO tienen cada uno dos brazos: CONTROL y PROTECT. Ambos se copian una sola vez de la cartera LAB RATIO 60% correspondiente, después de su ciclo; conservan efectivo, reserva, pérdidas, posiciones, tokens ya operados y frenos. No reciben otros 100 EUR ni borran historial. No sumar las copias. Los saldos iniciales pueden ser inferiores a 100 EUR.

El primer ciclo solo guarda la bifurcación; las decisiones empiezan en la siguiente lectura. protection_baseline registra fecha, fuente, patrimonio, realizado, efectivo, reserva y abiertas. Comparar el cambio respecto a esa base y separar posiciones heredadas de nuevas entradas; no atribuir las ganancias antiguas al experimento. Las cuatro carteras se persisten en el artefacto junto al marcador fomo_lab_protect_fork_r1.json. Si faltan carteras después de crear el experimento, se detiene este laboratorio y se pide restaurar el artefacto, sin reiniciar fondos.

Reglas comunes: compras 5m >=60%, EARLY/IMPULSO existentes, capital-r2 (nuevas entradas <=5 EUR, pausa tras dos posiciones completas perdedoras consecutivas en60min), stop neto−15%, parcial de50% al+30% neto, trailing−15%, comisión1% y deslizamiento2% multiplicados por lado, reserva50% del beneficio realizado positivo, FX1:1, sin gas ni MEV.

La única diferencia es PROTECT: una cotización verificable observada desde la activación con resultado neto >=+12% arma protección persistente. Si después el neto observado cae a <=+2%, cierra todo el resto al precio observado. El stop−15% conserva prioridad en una caída mayor; cotizaciones ausentes o sin liquidez suficiente no autorizan venta ni armado. Los máximos anteriores a la bifurcación no arman retroactivamente la protección. Después del parcial también puede proteger el resto.

+12%/+2% son hipótesis de prueba, no valores optimizados. La regla no garantiza cierre a+2%: entre lecturas puede cerrar por debajo o con pérdidas. No reconstruye compras o ventas pasadas. Una salida temprana puede evitar pérdidas o recortar ganadoras; comparar ambos casos, costes y abiertas. Las carteras originales 52/60 y V10 no reciben esta salida, y ballenas conserva su política.

BRAIN_PROTECT_LAB se activa si sus pruebas y las de ratio pasan. Lecturas de aproximadamente un minuto dentro de sesiones, con huecos entre runs. No ejecuta órdenes reales.

