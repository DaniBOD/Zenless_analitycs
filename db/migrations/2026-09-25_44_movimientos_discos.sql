-- =============================================================================
-- Historial de movimientos de discos · 2026-09-25 · migración 44
-- =============================================================================
-- Daniel aplicó en el juego dos sugerencias del motor (#85 Anby → Dialyn, #188 Astra Yao → Ju
-- Fufu, cada una con su reposición) y pidió: "sobre los swaps que hice realizalos en la db para
-- que tenga trazabilidad". `inventory_discs` guarda sólo el estado ACTUAL: después de un
-- movimiento no queda rastro de quién llevaba el disco, ni por qué cambió.
--
-- Una fila por disco que cambia de lugar en una tanda:
--   motivo 'equipa'     → el disco pasa a `hacia_agente_id` (desde otro PJ o desde libre);
--   motivo 'desplazado' → el disco que ocupaba ese slot queda LIBRE (hacia NULL): el juego no
--                         recuerda quién lo llevaba (invariante de Daniel, 2026-07-22: el
--                         desplazado pierde equipado Y dueño).
-- `lote` agrupa lo aplicado junto; `fuente` dice quién lo afirma ('declarado_usuario': lo contó
-- Daniel; la captura en vivo podrá registrar los suyos); `referencia`, de dónde salió (el reporte
-- de sugerencias y la sugerencia).
--
-- Rebuild: VACIAR. Las filas cuelgan de `inventory_discs`, que se re-censa con ids nuevos; un
-- historial de ids que ya no existen no se puede leer.
-- =============================================================================

BEGIN TRANSACTION;

CREATE TABLE movimientos_discos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lote            TEXT    NOT NULL,
    disc_id         INTEGER NOT NULL REFERENCES inventory_discs(id),
    slot            INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 6),
    desde_agente_id INTEGER REFERENCES agents(id),
    hacia_agente_id INTEGER REFERENCES agents(id),
    motivo          TEXT    NOT NULL CHECK (motivo IN ('equipa', 'desplazado')),
    fuente          TEXT    NOT NULL,
    referencia      TEXT,
    CHECK (motivo <> 'equipa' OR hacia_agente_id IS NOT NULL),
    CHECK (motivo <> 'desplazado' OR (hacia_agente_id IS NULL AND desde_agente_id IS NOT NULL))
);

CREATE INDEX idx_movimientos_discos_disc ON movimientos_discos(disc_id);

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;
SELECT COUNT(*) AS expected_0 FROM movimientos_discos;
