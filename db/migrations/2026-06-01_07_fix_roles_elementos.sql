-- =====================================================================
-- 2026-06-01_07_fix_roles_elementos.sql
-- ---------------------------------------------------------------------
-- Corrige rol/elemento de agentes mal seedeados en `agents`, detectados
-- durante el QA en vivo del 2026-05-31 (parser S18 lee rol/elemento de la
-- PANTALLA = ground truth) y verificados contra fuentes autorizadas
-- (Prydwen.gg / Game8 / ZZZ Fandom) el 2026-06-01 (RNF-02).
--
-- El scoring/recomendador (RF-04/06) lee rol/elemento de la DB, así que esta
-- data incorrecta degradaba las recomendaciones.
--
-- CORRECCIONES DE ROL (6 agentes):
--   id=11 Pulchra      Ataque      -> Aturdimiento   (Physical Stun)
--   id=22 Lucía        Defensa     -> Soporte        (Ether Support, HP-scaling)
--   id=23 Ye Shunguang Disruptivos -> Ataque         (Honed Edge ~Físico, Attack)
--   id=24 Yuzuha       Anomalía    -> Soporte        (Physical Support)
--   id=27 Dialyn       Ataque      -> Aturdimiento   (Physical Stun)
--   id=29 Ju Fufu      Soporte     -> Aturdimiento   (Fire Stun)
--
-- CORRECCIÓN DE ELEMENTO (1 agente, elemento nuevo v2.0):
--   id=31 Yixuan       Éter        -> Tinta áurica   (Auric Ink, ≡Éter p/modifs)
--
-- IMPACTO EN pj_weapon_synergy:
--   La synergy es un template DETERMINISTA por rol (BONUS_MATRIX). Los 6
--   agentes con rol corregido tenían la matriz de su rol ERRÓNEO. Se remapea
--   copiando la matriz canónica del rol destino desde un agente de referencia:
--     Aturdimiento -> ref Lycaon  (id=3):  Pulchra(11), Dialyn(27), Ju Fufu(29)
--     Soporte      -> ref Lucy    (id=9):  Lucía(22), Yuzuha(24)
--     Ataque       -> ref N.º 11  (id=6):  Ye Shunguang(23)
--   Yixuan: rol Disruptivos NO cambia -> synergy intacta.
--
-- IMPACTO EN agent_thresholds: revisado, NO se modifica (RNF-02). Pulchra,
--   Lucía y Ye Shunguang ya tenían thresholds acordes a su rol REAL (impacto /
--   pv / crit+pen respectivamente). Ju Fufu/Yuzuha/Dialyn quedan FLAG para
--   re-derivar contra Prydwen en su próximo QA (no se inventan valores).
--
-- NO incluido (flags pendientes de decisión de DaniBOD):
--   - Nangong Yu (id=26): rol Aturdimiento + elem Éter son CORRECTOS, pero su
--     synergy usa la matriz de Anomalía (es Stun/Anomaly hybrid). ¿Bug o
--     intencional? Se deja intacto hasta confirmar.
--   - Ye Shunguang (id=23): atributo único "Honed Edge" (≈Físico). Sin nombre
--     ES capturado de pantalla -> se conserva 'Físico' + nota tentativa.
-- =====================================================================

BEGIN TRANSACTION;

-- 1) Correcciones de rol --------------------------------------------------
UPDATE agents SET rol = 'Aturdimiento' WHERE id = 11;   -- Pulchra
UPDATE agents SET rol = 'Soporte'      WHERE id = 22;   -- Lucía
UPDATE agents SET rol = 'Ataque'       WHERE id = 23;   -- Ye Shunguang
UPDATE agents SET rol = 'Soporte'      WHERE id = 24;   -- Yuzuha
UPDATE agents SET rol = 'Aturdimiento' WHERE id = 27;   -- Dialyn
UPDATE agents SET rol = 'Aturdimiento' WHERE id = 29;   -- Ju Fufu

-- 2) Corrección de elemento (Auric Ink) -----------------------------------
UPDATE agents SET elemento = 'Tinta áurica' WHERE id = 31;   -- Yixuan

-- 3) Nota tentativa atributo único Ye Shunguang ---------------------------
UPDATE agents
   SET notas = TRIM(COALESCE(notas || ' | ', '')
               || 'attr_unico=Honed_Edge(~Fisico); pending_screen_ES_name (RNF-02)')
 WHERE id = 23;

-- 4) Remap pj_weapon_synergy al BONUS_MATRIX del rol corregido ------------
-- Sources (3=Lycaon Aturdimiento, 9=Lucy Soporte, 6=N.º 11 Ataque) NO están
-- en el set borrado, así que el INSERT...SELECT lee la matriz intacta.
DELETE FROM pj_weapon_synergy WHERE pj_id IN (11, 22, 23, 24, 27, 29);

-- -> Aturdimiento (Pulchra 11, Dialyn 27, Ju Fufu 29) desde Lycaon (3)
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
  SELECT 11, weapon_pasiva_tipo, bonus, razon || ' [remap rol 2026-06-01]', 'manual'
    FROM pj_weapon_synergy WHERE pj_id = 3;
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
  SELECT 27, weapon_pasiva_tipo, bonus, razon || ' [remap rol 2026-06-01]', 'manual'
    FROM pj_weapon_synergy WHERE pj_id = 3;
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
  SELECT 29, weapon_pasiva_tipo, bonus, razon || ' [remap rol 2026-06-01]', 'manual'
    FROM pj_weapon_synergy WHERE pj_id = 3;

-- -> Soporte (Lucía 22, Yuzuha 24) desde Lucy (9)
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
  SELECT 22, weapon_pasiva_tipo, bonus, razon || ' [remap rol 2026-06-01]', 'manual'
    FROM pj_weapon_synergy WHERE pj_id = 9;
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
  SELECT 24, weapon_pasiva_tipo, bonus, razon || ' [remap rol 2026-06-01]', 'manual'
    FROM pj_weapon_synergy WHERE pj_id = 9;

-- -> Ataque (Ye Shunguang 23) desde N.º 11 (6)
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
  SELECT 23, weapon_pasiva_tipo, bonus, razon || ' [remap rol 2026-06-01]', 'manual'
    FROM pj_weapon_synergy WHERE pj_id = 6;

COMMIT;

-- =====================================================================
-- SMOKE CHECKS (cada SELECT debe devolver expected_N = N)
-- =====================================================================
-- 6 agentes con rol corregido
SELECT COUNT(*) AS expected_6 FROM agents
 WHERE (id=11 AND rol='Aturdimiento') OR (id=22 AND rol='Soporte')
    OR (id=23 AND rol='Ataque')       OR (id=24 AND rol='Soporte')
    OR (id=27 AND rol='Aturdimiento') OR (id=29 AND rol='Aturdimiento');
-- Yixuan con elemento nuevo
SELECT COUNT(*) AS expected_1 FROM agents WHERE id=31 AND elemento='Tinta áurica';
-- synergy: 6 agentes × 6 filas = 36 marcados con la procedencia del remap
-- (fuente debe ser 'manual' por CHECK; la procedencia va en razon)
SELECT COUNT(*) AS expected_36 FROM pj_weapon_synergy WHERE razon LIKE '%[remap rol 2026-06-01]%';
-- synergy de Ju Fufu (29) ahora == matriz de Lycaon (3) [Aturdimiento]
SELECT COUNT(*) AS expected_0 FROM (
  SELECT weapon_pasiva_tipo, bonus FROM pj_weapon_synergy WHERE pj_id=29
  EXCEPT
  SELECT weapon_pasiva_tipo, bonus FROM pj_weapon_synergy WHERE pj_id=3
);
-- synergy de Yuzuha (24) ahora == matriz de Lucy (9) [Soporte]
SELECT COUNT(*) AS expected_0 FROM (
  SELECT weapon_pasiva_tipo, bonus FROM pj_weapon_synergy WHERE pj_id=24
  EXCEPT
  SELECT weapon_pasiva_tipo, bonus FROM pj_weapon_synergy WHERE pj_id=9
);
