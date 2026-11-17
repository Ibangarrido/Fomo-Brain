# Kronos: prueba prospectiva aislada, PAPER ONLY

BTC/USDT, velas cerradas de una hora, horizonte de 24 velas. Cada observación simula 10 EUR independientes, sin tocar PAPER1/PAPER2 ni sus saldos. Las observaciones se solapan: no deben sumarse como rentabilidad de una cartera.

Se conserva el pronóstico original, hora de publicación, precio observado al publicarlo, huella del histórico y resultado posterior. Una muestra por pronóstico, semilla 42; no se anuncia una probabilidad ni un porcentaje de aciertos esperado. LONG solo si la subida prevista supera 40 puntos básicos de costes totales simulados; en otro caso CASH. Comparación con comprar y mantener bajo los mismos costes y periodo. Esos costes son una hipótesis para BTC, no una estimación para memes.

Código upstream fijado a 67b630e67f6a18c9e9be918d9b4337c960db1e9a. Modelo pequeño oficial: NeoQuasar/Kronos-small. Pesos fijados: modelo 901c26c1332695a2a8f243eb2f37243a37bea320; tokenizer 0e0117387f39004a9016484a186a908917e22426. La primera predicción local se conserva en experiments/kronos/initial-ledger.json y sirve de estado inicial.

El workflow restaura el ledger de la rama main, ejecuta y publica artefactos aun si falla. Si falla la restauración de un estado existente, debe detenerse. En una rama de PR la ejecución es de validación; la recogida diaria automática requiere incorporar este workflow a main. Una primera predicción no demuestra rentabilidad. Evaluar al menos 30 días con métricas de dirección, retorno neto y comparación con baseline antes de considerar uso como filtro. No integra señales en las decisiones de Brain ni activa operaciones reales.

Fuentes: https://github.com/shiyu-coder/Kronos y https://arxiv.org/abs/2508.02739 .
