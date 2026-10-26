# Fomo-Brain

Sistema experimental para analizar datos de mercado de FOMO y estudiar patrones de entrada, salida, volumen, liquidez, holders y movimiento de tokens.

## Objetivos

- Recopilar datos de mercado.

- Analizar evolución de precio y volumen.

- Detectar cambios relevantes en holders y liquidez.

- Registrar operaciones de aprendizaje.

- Generar señales basadas en reglas cuantificables.

- Mantener inicialmente todo en modo simulación/paper trading.

## Gestión del riesgo

El sistema no ejecutará operaciones reales inicialmente.

Toda estrategia deberá probarse primero con datos históricos y paper trading antes de considerar cualquier ejecución real.

## Monitorización e integraciones (26-10-2026)

- [Auditoría de fuentes, límites y arquitectura 24/7](docs/FOMO_INTEGRATIONS_2026-10-26.md).
- Diagnóstico offline de salud de proveedores: `python -m unittest -v test_source_health.py` y `python source_health.py`.
- No extraer datos de FOMO mediante bots o scraping sin permiso escrito; el prototipo utiliza datos públicos de proveedores independientes.
- Las carteras continúan exclusivamente en modo PAPER. La salud de una API no equivale a rentabilidad ni a una salida ejecutable.
