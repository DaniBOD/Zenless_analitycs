-- =============================================================================
-- Onboarding Aria (PARCIAL) · 2026-08-16
-- =============================================================================
-- Aria: S · Éter · Anomalía · Angels of Delusion · M0 (CINEMA 0/6) · Nivel 40/40.
--
-- FUENTE ÚNICA (RNF-02): la captura del propio juego
--   Documentacion/Screenshots_Triggers/Triggers_Generales/Perfil_agente/
--   atributos_base_ejemplo_16.png  (S18 · pestaña "Atributos base")
-- Cruzada con el parser del propio sistema: `parse_agent_stats` devolvió los 11
-- atributos con confianza_global 0.973, coincidiendo exactamente con la lectura
-- visual. Nada de acá viene de Prydwen ni de estimación.
--
-- A DIFERENCIA de los tres onboardings anteriores, Aria NO trae vocabulario
-- nuevo: elemento, rol, facción y rango ya existen en la DB. No hace falta
-- tocar CHECKs, mapas de pantalla ni logos.
--   · elemento = 'Éter'.     La pantalla dice "Etéreo"; `_ELEMENTO_SCREEN_MAP`
--                            ya lo resuelve (mismo caso que Pyrois).
--   · rol      = 'Anomalía'. La pantalla dice "Anómalo"; `_ROL_SCREEN_MAP` ya lo
--                            resuelve.
--   · faccion  = 'Angels of Delusion'. YA EXISTE en la tabla (Sunna id 21,
--                            Nangong Yu id 26). La pantalla ES dice "Ángeles de
--                            la Delusión" y el logo "ANGELS OF DELUSION": se
--                            respeta el valor que la tabla ya usa.
--   · rango    = 'S', leído del badge dorado del header (el sol con la "S"),
--                            que es donde vive la rareza — verificado contra el
--                            ∞ de Pyrois.
--
-- STATS: son EFECTIVOS (con arma y discos equipados), que es lo que la columna
--   declara. Aria está en Nivel 40 con los 6 discos a 15/15 y su W-Engine a
--   30/30 (Ejemplo_11.png). Se nota en que prob_critico (12.2) y
--   tasa_perforacion (24.0) están por encima de los valores base. Son REALES y
--   no provisorios como los de Remielle (Nv1 sin discos), pero cambian si sube
--   de nivel o rearma la build → RECAPTURAR entonces.
--   Unidades: los porcentajes van en enteros (24.0, no 0.24), como el resto de
--   la tabla.
--
-- NO expuestos en esta pantalla → NULL (RNF-02, no inventar):
--   perforacion (plana), bono_dano_elemento, weapon_*, set_*, disco6_main.
--   Los sets y el arma SE VEN en Ejemplo_11.png, pero identificarlos por el logo
--   a ojo es exactamente lo que envenenó el catálogo en julio: los llena la
--   cosecha en vivo, que lee el nombre escrito en pantalla.
-- agent_thresholds → NO se cargan: son objetivos de build por PJ y requieren
--   Prydwen. Mismo tratamiento que Velina, Pyrois y Remielle Dan.
-- agent_awakenings.version_juego → NULL: el patch de release de Aria no está
--   confirmado por ninguna fuente del repo, y no se inventa. Es un UPDATE de una
--   línea cuando se sepa.
--
-- Lo que SÍ habilita esta migración: que las tres superficies de badges puedan
--   APRENDER a Aria. `badge_surface.learn` canoniza la etiqueta contra el roster
--   y descarta en silencio lo que no está en `agents` — sin esta fila, cosechar
--   no guarda nada.
--
-- ⚠️ Antes de ejecutar: BACKUP db/danibod_zzz_v2.db (RNF-01). App cerrada o en
--    READONLY. Runner: python app/scripts/qa/apply_migration.py <este archivo>
-- =============================================================================

BEGIN TRANSACTION;

-- 1. agents (core + stats efectivos de Nivel 40 / M0 con discos y W-Engine)
INSERT INTO agents (
    nombre, rango, nivel, mindscape, elemento, rol, faccion,
    pv, ataque, defensa, impacto,
    prob_critico, dano_critico,
    tasa_anomalia, maestria_anomalia,
    tasa_perforacion, perforacion,
    rec_energia, bono_dano_elemento,
    weapon_id, weapon_nivel, weapon_rango,
    set_4p_id, set_2p_id, disco6_main,
    protected_build, notas
) VALUES (
    'Aria', 'S', 40, 0, 'Éter', 'Anomalía', 'Angels of Delusion',
    8812, 1591, 699, 87,
    12.2, 74.0,
    175, 289,
    24.0, NULL,
    1.2, NULL,
    NULL, NULL, NULL,
    NULL, NULL, NULL,
    0,
    'Onboarding PARCIAL 2026-08-16. PJ del banner actual, M0 (CINEMA 0/6). '
    || 'Sin vocabulario nuevo: elemento Eter (pantalla "Etereo"), rol Anomalia '
    || '(pantalla "Anomalo") y faccion Angels of Delusion ya existian en la DB. '
    || 'Stats EFECTIVOS de Nivel 40/40 con los 6 discos 15/15 + W-Engine 30/30 '
    || '(atributos_base_ejemplo_16 + Ejemplo_11): reales, RECAPTURAR si sube de '
    || 'nivel o rearma. perforacion plana + bono_dano_elemento no expuestos -> '
    || 'NULL. weapon_* y set_* -> NULL a proposito: se ven en la captura pero se '
    || 'llenan por cosecha, no por lectura de logo a ojo. agent_thresholds '
    || 'pending (Prydwen). Patch de release SIN CONFIRMAR. Falta splash art '
    || 'registrado en descargar_splash_arts (los .webp Aria_ico/Aria_extend YA '
    || 'estan) + IA (49 pares). Sin awakening. Cargada para habilitar la COSECHA '
    || 'de sus badges en las 3 superficies.'
);

-- 2. agent_score_thresholds (defaults del proyecto: equip 0.75 / upgrade 0.50)
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre = 'Aria';

-- 3. agent_awakenings — placeholder. version_juego NULL: no se inventa el patch.
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0, 'Sin awakening',
       'Aria: awakening no capturado todavia. Capturar in-game al comprar la silueta.',
       'placeholder', 0, NULL
FROM agents WHERE nombre = 'Aria';

-- 4. pj_weapon_synergy — las 6 filas del rol Anomalía.
--    NO es una estimación: son exactamente los mismos valores y razones que ya
--    tienen los otros 8 agentes de rol Anomalía (Alice, Burnice, Grace, Jane,
--    Miyabi, Piper, Remielle Dan, Vivian, Yanagi). Es la matriz por rol del
--    Onboarding_Nuevo_PJ.md §6 aplicada, no un juicio nuevo sobre Aria.
INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
SELECT id, 'dmg_boost',           0.7, 'DMG genérico ayuda pero no es prioritario.',            'manual' FROM agents WHERE nombre = 'Aria'
UNION ALL
SELECT id, 'crit',                0.4, 'Las anomalías no critean; bonus bajo.',                 'manual' FROM agents WHERE nombre = 'Aria'
UNION ALL
SELECT id, 'atk_boost',           0.6, 'ATK escala daño aplicado por anomalías.',               'manual' FROM agents WHERE nombre = 'Aria'
UNION ALL
SELECT id, 'anomaly_proficiency', 1.5, 'Anomalía escala directamente con AP; máxima sinergia.', 'manual' FROM agents WHERE nombre = 'Aria'
UNION ALL
SELECT id, 'energy_regen',        1.2, 'Off-field rotation depende de EX/Ult constantes.',      'manual' FROM agents WHERE nombre = 'Aria'
UNION ALL
SELECT id, 'pen_ratio',           0.4, 'PEN ayuda contra DEF en componente de daño directo.',   'manual' FROM agents WHERE nombre = 'Aria';

COMMIT;

-- =============================================================================
-- Validación (RNF-01)
-- =============================================================================
PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke checks: cada `expected_N` tiene que valer exactamente N.
SELECT COUNT(*) AS expected_1 FROM agents WHERE nombre = 'Aria';

SELECT COUNT(*) AS expected_1 FROM agents
 WHERE nombre = 'Aria' AND rango = 'S' AND nivel = 40 AND mindscape = 0
   AND elemento = 'Éter' AND rol = 'Anomalía' AND faccion = 'Angels of Delusion';

SELECT COUNT(*) AS expected_1 FROM agents
 WHERE nombre = 'Aria' AND pv = 8812 AND ataque = 1591 AND defensa = 699
   AND impacto = 87 AND prob_critico = 12.2 AND dano_critico = 74.0
   AND tasa_anomalia = 175 AND maestria_anomalia = 289
   AND tasa_perforacion = 24.0 AND rec_energia = 1.2;

-- Lo NO confirmado quedó NULL, no en cero (RNF-02).
SELECT COUNT(*) AS expected_1 FROM agents
 WHERE nombre = 'Aria' AND perforacion IS NULL AND bono_dano_elemento IS NULL
   AND weapon_id IS NULL AND set_4p_id IS NULL AND set_2p_id IS NULL
   AND disco6_main IS NULL;

SELECT COUNT(*) AS expected_1 FROM agent_score_thresholds
 WHERE agente_id = (SELECT id FROM agents WHERE nombre = 'Aria');

SELECT COUNT(*) AS expected_1 FROM agent_awakenings
 WHERE agente_id = (SELECT id FROM agents WHERE nombre = 'Aria');

SELECT COUNT(*) AS expected_6 FROM pj_weapon_synergy
 WHERE pj_id = (SELECT id FROM agents WHERE nombre = 'Aria');

-- La facción NO es nueva: Aria se suma a las dos que ya estaban.
SELECT COUNT(*) AS expected_3 FROM agents WHERE faccion = 'Angels of Delusion';

-- Totales de la tabla después de la migración.
SELECT COUNT(*) AS expected_51 FROM agents;
SELECT COUNT(*) AS expected_51 FROM agent_score_thresholds;
SELECT COUNT(*) AS expected_294 FROM pj_weapon_synergy;
