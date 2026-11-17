# Kronos: prueba prospectiva aislada, PAPER ONLY

BTC/USDT, velas cerradas de una hora, horizonte de 24 velas. Cada observación simula 10 EUR independientes, sin tocar PAPER1/PAPER2 ni sus saldos. Las observaciones se solapan: no deben sumarse como rentabilidad de una cartera.

Se conserva el pronóstico original, hora de publicación, precio observado al publicarlo, huella del histórico y resultado posterior. Una muestra por pronóstico, semilla 42; no se anuncia una probabilidad ni un porcentaje de aciertos esperado. LONG solo si la subida prevista supera 40 puntos básicos de costes totales simulados; en otro caso CASH. Comparación con comprar y mantener bajo los mismos costes y periodo. Esos costes son una hipótesis para BTC, no una estimación para memes.

Código upstream fijado a 67b630e67f6a18c9e9be918d9b4337c960db1e9a. Modelo pequeño oficial: NeoQuasar/Kronos-small. Pesos fijados: modelo 901c26c1332695a2a8f243eb2f37243a37bea320; tokenizer 0e0117387f39004a9016484a186a908917e22426. La primera predicción local se conserva en experiments/kronos/initial-ledger.json y sirve de estado inicial.

El workflow restaura el ledger de la rama main, ejecuta y publica artefactos aun si falla. Si falla la restauración de un estado existente, debe detenerse. En una rama de PR la ejecución es de validación; la recogida diaria automática requiere incorporar este workflow a main. Una primera predicción no demuestra rentabilidad. Evaluar al menos 30 días con métricas de dirección, retorno neto y comparación con baseline antes de considerar uso como filtro. No integra señales en las decisiones de Brain ni activa operaciones reales.

Fuentes: https://github.com/shiyu-coder/Kronos y https://arxiv.org/abs/2508.02739 .

## Comparación histórica adicional

Cada pronóstico nuevo adjunta `historical_analogs`: hasta 10 ventanas parecidas de 24 velas horarias, comparando trayectoria de cierre y perfil de volumen. Los casos deben tener su resultado de 24 velas completo antes de empezar la ventana actual. Sus periodos de resultado no se solapan entre sí; sus ventanas de entrada pueden hacerlo. Se exige un mínimo de 8 casos y una distancia máxima de 0,05 según la fórmula publicada en historical_analogs.py. Esos parámetros son hipótesis fijas, no una estrategia validada.

Con menos casos se publica INSUFFICIENT_DATA, sin porcentaje de éxito. Con suficientes casos se muestran los casos concretos, fechas, distancias y retornos históricos netos con 40 bps de costes hipotéticos. La fracción histórica positiva no es una probabilidad calibrada ni una estimación de rentabilidad futura. La muestra procede de las 512 velas disponibles, aproximadamente tres semanas: no representa todos los regímenes de mercado. No se imita una terminal Bloomberg ni se anuncia una máquina del tiempo.

El módulo es una implementación local de comparación descriptiva; no instala el paquete externo ni su broker. Referencia conceptual revisada: https://github.com/Jakeschincariol/day-trader-skill . Solo se adjunta a pronósticos nuevos, sin reescribir el primer pronóstico ni backfilling de resultados. No cambia LONG/CASH ni las decisiones de PAPER1/PAPER2. Las próximas observaciones permitirán estudiar prospectivamente si esta información añade valor.
