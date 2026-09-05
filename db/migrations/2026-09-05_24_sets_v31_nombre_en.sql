-- =============================================================================
-- 2026-09-05_24 · disc_sets: nombre_en de los dos sets de la v3.1
-- =============================================================================
-- `Hado emplumado` (54) y `Rosa espinosa` (55) entraron con `nombre_en` en NULL.
-- Eso los deja fuera de todo lo que resuelve por nombre inglés — en particular el
-- catálogo de nodos de farmeo (`app/resources/farm_nodes.toml`), que mapea el
-- título del nodo S13 a sus 2 sets usando `sets_en`. Con el campo en NULL, el
-- nodo nuevo no se puede cargar aunque se escriba la entrada.
--
-- ## Cómo se determinó el mapeo (RNF-02)
--
-- Los renders oficiales de los packages viven en
-- `Documentacion/Interfaz/Set-Discos_Package_Logo/` y traen el nombre EN en el
-- propio archivo. Ahí hay 30 nombres y la DB tenía 28: los dos que faltaban son
-- exactamente `Feathered Fate` y `Thorned Rose`.
--
-- La regla del proyecto para ES↔EN (migración `_13`, para no repetir el pecado
-- original del catálogo, que fue emparejar por parecido):
--     · traducción PALABRA POR PALABRA  ⇒ se aplica.
--     · parecido semántico solamente    ⇒ NO se aplica.
--
-- Los dos pares son palabra por palabra:
--     feathered = emplumado ·  fate = hado   ⇒ Feathered Fate = Hado emplumado
--     thorned   = espinosa  ·  rose = rosa   ⇒ Thorned Rose   = Rosa espinosa
--
-- Y NO se apoya sólo en el texto: el matcher de logos de la app
-- (`SetBadgeMatcher`, 90 refs de 30 sets) identificó los dos íconos del nodo S13
-- nuevo ("Espina veloz y garra desgarradora") contra las 30 clases ABIERTAS —sin
-- restringir a candidatos— y los dos ganaron primeros:
--
--     logo izquierdo -> Feathered Fate   conf 0.602   margen 0.138 al 2º
--     logo derecho   -> Thorned Rose     conf 0.456   margen 0.154 al 2º
--
-- Las confianzas son modestas porque las refs son renders de package y los del
-- nodo son íconos circulares in-game (riesgo documentado en §8.1 del propio
-- módulo); lo que vale es el ranking, y el segundo candidato quedó a 1,3-1,5×.
-- Además la imagen corrobora la traducción: el asset `Feathered Fate` dibuja
-- plumas y el `Thorned Rose` dibuja una rosa.
--
-- Backup previo: db/danibod_zzz_v2.backup_premig_<TS>.db  (RNF-01)
-- =============================================================================

SELECT 'ANTES' AS momento, id, nombre, nombre_en
  FROM disc_sets WHERE nombre_en IS NULL ORDER BY id;

BEGIN TRANSACTION;

-- Guarda: sólo escribe si el campo sigue en NULL (no pisa nada ya curado).
UPDATE disc_sets SET nombre_en = 'Feathered Fate'
 WHERE id = 54 AND nombre = 'Hado emplumado' AND nombre_en IS NULL;

UPDATE disc_sets SET nombre_en = 'Thorned Rose'
 WHERE id = 55 AND nombre = 'Rosa espinosa' AND nombre_en IS NULL;

COMMIT;

-- Smoke checks: cada expected_N tiene que valer exactamente N.
SELECT COUNT(*) AS expected_0 FROM disc_sets WHERE nombre_en IS NULL;
SELECT COUNT(*) AS expected_30 FROM disc_sets;
SELECT COUNT(*) AS expected_1 FROM disc_sets WHERE id = 54 AND nombre_en = 'Feathered Fate';
SELECT COUNT(*) AS expected_1 FROM disc_sets WHERE id = 55 AND nombre_en = 'Thorned Rose';
-- Ningún nombre_en repetido: si dos sets comparten el ingles, el catálogo de
-- nodos resolvería dos entradas al mismo set_id sin avisar.
SELECT COUNT(*) AS expected_0 FROM (
    SELECT nombre_en FROM disc_sets WHERE nombre_en IS NOT NULL
     GROUP BY nombre_en HAVING COUNT(*) > 1);

PRAGMA foreign_key_check;
PRAGMA integrity_check;
