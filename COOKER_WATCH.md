# Cooker wallet observer

Observa exclusivamente la cartera pública Solana `8deJ9xeUvXSJwicYptA9mHsU2rN2pDx37KWzkDkEXhU6` usando RPC oficial, sin depender de sesiones de GMGN o FOMO. No se ha verificado un perfil FOMO para esta cartera.

Workflow independiente cada 15 minutos (GitHub puede retrasarlo). Primera lectura fija cursor, sin convertir historia en operaciones propias. Las siguientes recuperan hasta 100 firmas finalizadas; si no encuentran el cursor declaran hueco y no lo avanzan. En fallos RPC conservan cursor para reintentar. Deduplicación por firma, orden cronológico y estado persistido en artefacto `cooker-tracking` por 30 días. Si se pierde memoria se crea nueva línea base: no se reconstruye continuidad ficticia.

Registra cambios de tokens de la cartera y si firmó. Un cambio firmado es candidato pendiente de verificar como swap; transferencias, creación de tokens y repartos no se interpretan como compras. El lector todavía NO clasifica compras/ventas definitivas, ni calcula su beneficio o ejecuta simulación. No contiene firmas, claves privadas ni órdenes reales. El saldo de 100 EUR y las entradas de 10 EUR de la propuesta anterior no se activan con este lector.

Salud: `BASELINE_SET`, `SYNCED`, `HISTORY_GAP_CURSOR_RETAINED`, `UNAVAILABLE_RETRY_NEXT_RUN`. Una run verde puede contener fuente no disponible: revisar estado y artefacto. `new_events` mide transacciones, no trades.

Pruebas: `python -m unittest -v test_cooker_watch.py`.
Fuentes: https://solana.com/docs/rpc/http/getsignaturesforaddress y https://solana.com/docs/rpc/http/gettransaction .
