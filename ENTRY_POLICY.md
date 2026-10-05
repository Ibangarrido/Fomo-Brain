# V10: ajuste EARLY r2

Cambio experimental prospectivo tras las runs 128 y 129. Los resultados históricos no se recalculan ni las carteras se reinician. Las posiciones abiertas mantienen las salidas existentes; las nuevas entradas EARLY llevan entry_policy_version=early-r2. El patrimonio acumulado combina entradas de distintas versiones: no atribuir todo el resultado a r2.

EARLY mantiene edad del par de 2–60 minutos y cambio de precio 5m de 2–60%. Ahora exige al menos 20.000 USD de liquidez, 40 operaciones en 5m y 60% de compras por número de operaciones. La lectura previa del mismo par debe tener 0,5–5 minutos, momentum 5m también de 2–60%, precio entre lecturas +1–12%, liquidez al menos 95% de la previa y volumen 5m no decreciente. Antes aceptaba volumen de hasta 60% de la lectura anterior.

IMPULSO conserva su política de impulso y su cartera independiente. Ambas carteras rechazan entradas cuando la cotización fresca difiere más del 5% (en cualquier dirección) del precio de la señal. Cada nueva posición guarda los indicadores de la cotización fresca, precio de señal, desviación y versión de entrada; los logs muestran esos indicadores principales.

No se suman carteras. Todo es simulación con comisión y deslizamiento estimados; no hay órdenes reales ni garantía de ejecución. El stop se evalúa en cada lectura, no limita pérdidas a 15% si el precio salta entre lecturas o runs. Los conteos de compras no prueban flujo monetario neto ni compradores únicos. Holders no intervienen porque no hay una fuente verificada conectada.

Validación: 18 tests, incluidos rechazos por volumen decreciente, rebote desde momentum negativo, salto entre lecturas y desviación de la cotización, más persistencia, separación de carteras, salidas y costes. Esto valida comportamiento del código; falta medir el rendimiento de las próximas entradas tras costes.
