# V12: seguimiento prospectivo y resultados netos de simulación

V12 instrumenta las carteras aisladas V11 CONTROL y NET. No es una estrategia
nueva ni relaja sus filtros, fuerza entradas o modifica carteras históricas.

Con `BRAIN_V12_OBSERVABILITY=1`, cada cartera registra sus descartes con cadena,
contrato, par, motivo, precio de referencia y hora de recepción. Los intentos
repetidos cuentan como evaluaciones; se abre como máximo un caso por brazo/par
cada 62 minutos. No deben confundirse evaluaciones con tokens únicos.

Los casos se conservan en `fomo_v12_observations_r1.json`. Durante cada ciclo,
V12 consulta los pares que vencen a 5, 15, 30 y 60 minutos, incluso si el token
ya salió del ranking. Acepta una observación dentro de los 120 segundos
posteriores al horizonte y una recepción de como máximo 30 segundos. Valida
cadena, contrato y par exactos; rechaza migraciones. Hasta 20 pares por ciclo,
con solicitudes compartidas entre brazos y prioridad por vencimiento. Guarda
hasta 500 casos y declara los descartados por capacidad. Los resultados
completos se agregan y retiran después de 24 horas.

Si falta una cotización, la medición queda pendiente hasta vencer y después
`unknown`; nunca se rellena con una lectura posterior. El seguimiento solo
ocurre mientras corre GitHub Actions. Un intervalo sin ejecuciones puede
perder horizontes. Las horas de recepción no prueban la frescura de las
operaciones del proveedor. Los cambios de precio no equivalen a beneficios
que se hubieran podido obtener.

`paper_observability_status.json` incluye cobertura por horizonte, motivos,
valoración de ambas carteras y conciliación de ventas parciales/completas.
El beneficio modelado utiliza cantidad vendida, coste asignado y producto de
venta del registro real de la simulación. Desglosa fricción de entrada y
salida y comprueba que coincide con el beneficio registrado. Evidencia
incompleta o discrepante permanece desconocida. No suma marcas históricas de
posiciones sin precio al patrimonio conocido.

Los importes del modelo usan USD/EUR=1, comisión 1% y deslizamiento 2% por lado.
Gas, MEV, ejecución real y conversión de divisas no están verificados. Por ello
el resultado neto con todos los costes queda desconocido cuando hay ventas;
`integrated_modeled_only` significa cálculo integrado, no ejecución demostrada.

La memoria se recupera explícitamente de la misma rama. La cola también está
separada por rama; el cron nativo de GitHub solo se ejecuta desde la rama por
defecto. Lanzar esta rama manualmente no activa una programación continua.

Validación: `python -m unittest discover -v` incluye pruebas de reinicio,
ventanas, fallos de red, identidad, cotizaciones antiguas/futuras, límites,
ventas parciales y conexión al simulador.
