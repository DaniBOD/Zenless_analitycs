-- 2026-06-20 — Velina: carga de stats efectivos capturados in-game (RNF-02)
--
-- Fuente: lectura en vivo del panel de stats de agente (app.log 2026-06-20 02:43:21,
--   conf=0.97, missing=[]). Onboarding parcial previo: commit 067997e (id=48).
--
-- Captura: Velina (Anomalía/Viento) Nv=50 PV=9937 ATK=1571 DEF=783 IMP=86
--          CR=24.2% CD=112.4% TA=112 MA=266 TP=0.0% ER=1.2
--
-- RNF-02 — NO se inventa lo no observado:
--   * nivel: 60 (placeholder onboarding) -> 50 (nivel real capturado).
--   * perforacion (PEN plana): el lector de stats NO la expone -> queda NULL.
--   * bono_dano_elemento (Bono daño Viento): no está en el panel leído -> queda NULL.
--   * agent_thresholds / weapon_synergy / splash / IA: siguen pendientes (otra fase).

BEGIN TRANSACTION;

UPDATE agents
SET
    nivel             = 50,
    pv                = 9937,
    ataque            = 1571,
    defensa           = 783,
    impacto           = 86,
    prob_critico      = 24.2,
    dano_critico      = 112.4,
    tasa_anomalia     = 112,
    maestria_anomalia = 266,
    tasa_perforacion  = 0.0,
    rec_energia       = 1.2,
    notas             = 'Onboarding PARCIAL 2026-06-19 (patch v3.x). ELEMENTO VIENTO = nuevo en el roster -> revisar impacto en sets/scoring de Viento. Stats efectivos CAPTURADOS in-game 2026-06-20 (Nv50, conf 0.97). PENDIENTE: perforacion plana + bono_dano_elemento (Bono dano Viento) no expuestos por el lector -> NULL. agent_thresholds pending (Prydwen Velina). Falta pj_weapon_synergy + splash + IA. Sin awakening. Faccion "External Strategy Department" (del icono) -> confirmar nombre canonico.'
WHERE nombre = 'Velina' AND id = 48;

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

-- Smoke check: debe mostrar la fila con los stats cargados (expected_stats = 1 fila).
SELECT 1 AS expected_stats, id, nombre, nivel, pv, ataque, defensa, impacto,
       prob_critico, dano_critico, tasa_anomalia, maestria_anomalia,
       tasa_perforacion, rec_energia
FROM agents WHERE nombre = 'Velina';
