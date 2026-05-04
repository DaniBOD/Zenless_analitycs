-- =============================================================================
-- Migración 08 — Corregir mains_4/5/6 en disc_archetypes
-- Problema: mains_5 usaba "Bono Daño" (no canónico) y mains_6 incluía
--           "Daño Crítico" que no es main válido para slot 6.
-- Corrige los 6 arquetipos usando nombres canónicos de stats_vocab.
-- =============================================================================

BEGIN TRANSACTION;

-- ATK_DPS: slot 5 expande "Bono Daño" a todos los tipos, slot 6 solo ATK%
UPDATE disc_archetypes SET
    mains_5 = '["Bono Daño Físico","Bono Daño Fuego","Bono Daño Hielo","Bono Daño Eléctrico","Bono Daño Éter","ATK%"]',
    mains_6 = '["ATK%"]'
WHERE code = 'ATK_DPS';

-- HP_DISRUPT: slot 5 expande, slot 6 quita "Daño Crítico" (inválido)
UPDATE disc_archetypes SET
    mains_5 = '["Bono Daño Físico","Bono Daño Fuego","Bono Daño Hielo","Bono Daño Eléctrico","Bono Daño Éter","HP%"]',
    mains_6 = '["HP%"]'
WHERE code = 'HP_DISRUPT';

-- ANOMALY: slot 5 expande "Bono Daño" a todos los tipos
UPDATE disc_archetypes SET
    mains_5 = '["Bono Daño Físico","Bono Daño Fuego","Bono Daño Hielo","Bono Daño Eléctrico","Bono Daño Éter","ATK%"]'
WHERE code = 'ANOMALY';

-- STUN: slot 5 agrega elemental damage como alternativa válida
UPDATE disc_archetypes SET
    mains_5 = '["Bono Daño Físico","Bono Daño Fuego","Bono Daño Hielo","Bono Daño Eléctrico","Bono Daño Éter","ATK%"]'
WHERE code = 'STUN';

-- SUPPORT_ER: slot 5 expande "Bono Daño"
UPDATE disc_archetypes SET
    mains_5 = '["ATK%","Bono Daño Físico","Bono Daño Fuego","Bono Daño Hielo","Bono Daño Eléctrico","Bono Daño Éter"]'
WHERE code = 'SUPPORT_ER';

-- DEFENSE: slot 5 ya es correcto (DEF%/HP%), sin cambio

COMMIT;

PRAGMA foreign_key_check;
PRAGMA integrity_check;

SELECT code, mains_5, mains_6 FROM disc_archetypes;
