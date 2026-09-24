-- =============================================================================
-- Prioridad de buildeo por PJ · 2026-09-24 · migración 42
-- =============================================================================
-- Fase A, etapa 1. Corrido sobre el inventario real, el motor mandaba 32 de 108 movimientos a
-- Piper, sacándole discos a PJs que Daniel sí usa. Daniel (2026-09-23): "piper no la uso casi nada
-- mientras que claret la quiero mejorar ahora". El sistema no puede saber a quién quiere mejorar:
-- lo declara él. Decisiones suyas (2026-09-24):
--
--   niveles → alta / normal / baja. Todo PJ arranca en normal.
--   efecto  → BLOQUEA: nunca se sugiere sacarle un disco a un PJ para dárselo a otro de prioridad
--             más baja. Entre iguales sigue "el que lo tiene no pierde". Los libres van primero a
--             los de alta.
--   dónde   → se edita en la app (Roster + modal de PJ; brief de Claude Design
--             `BRIEF_prioridad_de_buildeo.md`), no por chat.
--
-- Es un AJUSTE del usuario, de la misma capa que la migración 40: una tabla propia, no una columna
-- de `agents`. `agents` se reescribe desde la captura (S18, el censo); un dato que sólo pone Daniel
-- no puede vivir ahí.
--
-- ## "normal" no se guarda
--
-- Normal es la AUSENCIA de fila. Una sola forma de decir "normal" (B1): si también pudiera ser una
-- fila con 'normal', habría dos, y un lector que sólo mira una de las dos se equivoca. Volver un PJ
-- a normal es borrar su fila, igual que borrar un ajuste de la mig 40 devuelve el default.
--
-- ## Sin datos iniciales
--
-- La tabla nace vacía (los 52 en normal): Daniel las declara en la app. Nada de esta migración
-- cambia una sugerencia hasta que haya una fila.
-- =============================================================================

BEGIN TRANSACTION;

CREATE TABLE ajustes_usuario_prioridad (
    agente_id   INTEGER PRIMARY KEY REFERENCES agents(id),
    prioridad   TEXT    NOT NULL CHECK (prioridad IN ('alta', 'baja')),
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP
);

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;
SELECT COUNT(*) AS expected_0 FROM ajustes_usuario_prioridad;
