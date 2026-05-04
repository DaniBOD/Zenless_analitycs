# Onboarding de PJ nuevo — flujo end-to-end

**Última actualización:** 2026-04-26
**Owner:** DaniBOD
**Trigger típico:** cada patch del juego (~6 semanas) trae 1-2 personajes nuevos.
**Documentos relacionados:** RF-04 (captura), RF-11 (UI wizard), RF-12 (catalogación IA), RF-13 (lategame), RF-14 (armas).

Este documento define cómo el sistema absorbe un personaje nuevo de un patch sin que se rompa nada y sin perder información histórica. Es la materialización operativa del **RNF-05 (extensibilidad por versiones del juego)**.

---

## §1 — Origen y motivación

ZZZ tiene ciclo de patches ~6 semanas y agrega típicamente 1-2 PJs nuevos por patch. Cada PJ nuevo afecta a múltiples capas del sistema:

- **Roster** (`agents` + thresholds + awakenings)
- **Sinergias de equipo** (44 pares nuevos en `team_synergies`)
- **Tier list personal** (cuando Daniel haga runs con él)
- **Optimizador de armas** (6 filas en `pj_weapon_synergy` + Prydwen recommendations)
- **Splash arts** (descarga del nuevo asset)

Sin un flujo claro, agregar un PJ se vuelve un proceso ad-hoc propenso a olvidar pasos (ej. "olvidé poblar `pj_weapon_synergy` para Lyra y RF-14 le da scores neutros").

## §2 — Detección del PJ nuevo

Tres caminos posibles:

| Trigger | Cuándo | Cómo |
|---------|--------|------|
| **Manual desde wizard UI** | Daniel sabe que salió Lyra, abre el wizard | Botón "Agregar PJ nuevo" en pestaña Configuración → wizard 4 pasos |
| **Automático desde RF-04** | RF-04 captura un screenshot con un PJ que no está en `agents` | Diálogo modal: "¿Detectado PJ nuevo: 'Lyra'. ¿Iniciar onboarding?" |
| **Scraping Prydwen** | Job semanal detecta PJ nuevo en `prydwen_tier_snapshots` | Notificación en panel: "Prydwen agregó 'Lyra' — agregalo al roster" |

El **wizard manual** es el flujo canónico; los otros dos disparan el wizard pre-rellenando datos.

## §3 — Paso 1: Carga de datos base (`agents`)

INSERT en `agents` con stats efectivos del PJ. Los stats vienen de:
- **HoYoLAB screenshot** (ideal — datos reales del jugador con su build actual)
- **Prydwen "M0 standard"** (fallback — si Daniel todavía no tiene al PJ)

```sql
INSERT INTO agents (
    nombre, rango, nivel, mindscape, elemento, rol, faccion,
    pv, ataque, defensa, impacto,
    prob_critico, dano_critico,
    tasa_anomalia, maestria_anomalia,
    tasa_perforacion, perforacion,
    rec_energia, bono_dano_elemento,
    weapon_id, weapon_nivel, weapon_rango,
    set_4p_id, set_2p_id, disco6_main, notas
) VALUES (
    'Lyra', 'S', 60, 0, 'Hielo', 'Ataque', 'Section 6',
    8500, 1850, 720, 95,
    5.0, 50.0,
    8.0, 95,
    0.0, 0,
    1.2, 0,
    NULL, NULL, NULL,         -- weapon a definir cuando equipe
    NULL, NULL, 'CRIT Rate',  -- set + main slot 6 a definir
    'Datos M0 standard de Prydwen — actualizar al obtener'
);
```

**Validación:** `PRAGMA foreign_key_check; PRAGMA integrity_check;`

## §4 — Paso 2: Thresholds + Awakenings + Score thresholds

```sql
-- agent_thresholds (basado en arquetipo del rol del PJ)
INSERT INTO agent_thresholds (agente_id, stat, valor_minimo, valor_optimo, valor_maximo, descripcion, fuente)
VALUES
  ((SELECT id FROM agents WHERE nombre='Lyra'), 'prob_critico', 60.0, 75.0, NULL,
   'CRIT estándar Ataque DPS', 'prydwen_default'),
  ((SELECT id FROM agents WHERE nombre='Lyra'), 'dano_critico', 150.0, 200.0, NULL,
   'CDmg estándar Ataque DPS', 'prydwen_default');

-- agent_score_thresholds (defaults)
INSERT INTO agent_score_thresholds (agente_id, threshold_equip, threshold_upgrade, fuente)
SELECT id, 0.75, 0.50, 'default' FROM agents WHERE nombre='Lyra';

-- agent_awakenings (placeholder hasta que tengas el texto in-game)
INSERT INTO agent_awakenings (agente_id, nivel, nombre, descripcion, tipo_efecto, activo, version_juego)
SELECT id, 0, 'Sin awakening', 'Awakening no desbloqueado todavía', 'placeholder', 0, 'v2.9'
FROM agents WHERE nombre='Lyra';
```

## §5 — Paso 3: Determinar arquetipo

**No hay una tabla `agent_archetype` directa** — el arquetipo se infiere del rol + elemento + kit del PJ.

**Reglas heurísticas:**
- `rol='Ataque'` → `ATK_DPS` por default; `HP_DISRUPT` si su kit escala con HP (ej. Manato)
- `rol='Anomalía'` → `ANOMALY`
- `rol='Aturdimiento'` → `STUN`
- `rol='Soporte'` → `SUPPORT_ER`
- `rol='Defensa'` → `DEFENSE`
- `rol='Disruptivos'` → caso por caso (revisar kit)

**Override manual** disponible cuando el rol "engaña" — ej. Manato es Ataque pero escala con HP, así que su arquetipo es `HP_DISRUPT`. El wizard pregunta explícitamente *"¿Su daño escala con HP en lugar de ATK?"*.

El arquetipo se propaga implícitamente a través de `pj_weapon_synergy` (paso siguiente) y de las búsquedas en `disc_set_archetype` durante RF-06 scoring.

## §6 — Paso 4: Seed `pj_weapon_synergy` (6 filas)

Para cada uno de los 6 tipos de pasiva relevantes, insertar una fila con el bonus correspondiente al rol del PJ:

```python
# Ejemplo Python (similar al seed inicial que ya hicimos):
BONUS_MATRIX = {
    "Ataque":      {"dmg_boost": 1.0, "crit": 1.5, "atk_boost": 1.0,
                    "anomaly_proficiency": 0.3, "energy_regen": 0.4, "pen_ratio": 0.8},
    "Anomalía":    {"dmg_boost": 0.7, "crit": 0.4, "atk_boost": 0.6,
                    "anomaly_proficiency": 1.5, "energy_regen": 1.2, "pen_ratio": 0.4},
    # ... resto idéntico al seed inicial
}

pj_id = ...   # id del PJ recién insertado
for tipo, bonus in BONUS_MATRIX[rol_del_pj].items():
    cursor.execute("""
        INSERT INTO pj_weapon_synergy (pj_id, weapon_pasiva_tipo, bonus, razon, fuente)
        VALUES (?, ?, ?, ?, 'manual')
    """, (pj_id, tipo, bonus, RAZONES.get((rol, tipo), "default por rol")))
```

## §7 — Paso 5: Scraping Prydwen para weapons

Disparar `app/scripts/scrape_prydwen_weapons.py` con argumento del slug del PJ nuevo:

```bash
python scrape_prydwen_weapons.py --pj lyra
```

Esto inserta en `prydwen_weapon_recommendations_snapshots` la lista top-N de armas recomendadas para el PJ desde Prydwen.

**Si el PJ es muy nuevo y Prydwen aún no lo tiene** (las primeras 24-48 h post-release), saltear este paso y reintentar en el job semanal.

## §8 — Paso 6: Catalogación IA RF-12 (los 44 pares nuevos)

El PJ nuevo agrega **44 pares nuevos** a la matriz de sinergias (1 contra cada PJ existente del roster de 45). Esto se encola automáticamente cuando RF-04 detecta el PJ nuevo (ver RF-12 §6.1).

**Costo estimado:** ~$0.5 (44 pares × ~$0.012 con Claude sonnet + prompt caching).

```python
# Encolado automático (lo hace el sistema, no manual)
from app.core.ai_catalog import enqueue_recatalog_for_new_pj
enqueue_recatalog_for_new_pj(pj_id_nuevo)
```

El job de catalogación corre en background y poblará `team_synergies` durante las próximas horas. La UI muestra progreso ("Catalogando 12/44 pares para Lyra...").

**Si hay cap de costo mensual excedido** (RF-12 §6.3), se pausa el batch y se notifica al usuario para que aumente el cap o autorice este lote en particular.

## §9 — Paso 7: Splash art

Editar `Documentacion/Interfaz/splash_arts/descargar_splash_arts.py` y agregar la fila del PJ nuevo a `ROSTER`:

```python
(46, "Lyra",  "lyra",  None),   # nuevo en v2.9
```

Re-ejecutar el script:

```bash
python descargar_splash_arts.py
```

El script es idempotente — solo descargará el archivo nuevo (`46_Lyra.png`), los anteriores los saltea.

**Ubicación final:** `Documentacion/Interfaz/splash_arts/46_Lyra.png` (~1-3 MB, fondo transparente).

La pestaña Roster (RF-11) lo levanta automáticamente porque busca por convención `{id:02d}_{nombre}.png`.

## §10 — Paso 8: Notificación UI

Cuando el onboarding está completo, el sistema emite un toast resumen:

```
✅ PJ agregado al sistema
Lyra (S · Hielo · Ataque) — v2.9

Estado:
  • Stats base cargados
  • 44/44 pares catalogados con IA ($0.48)
  • Splash art descargado
  • Top weapons de Prydwen capturadas

Próximo paso: equipa a Lyra in-game para
que RF-04 capture su build real.
```

## §11 — Wizard de Onboarding (UI — RF-11)

El wizard vive en la pestaña **Configuración → Agregar PJ nuevo**. Es modal 600×500 px con 4 pasos:

1. **Datos básicos** — nombre, rango, elemento, rol, facción, mindscape, versión del juego.
2. **Stats efectivos** — formulario con todos los campos numéricos. Botón "Importar desde HoYoLAB screenshot" que dispara captura + OCR (RF-09) sobre la pantalla de stats del agente.
3. **Override de arquetipo** (opcional) — checkbox *"¿Su daño escala con HP?"* + dropdown manual si el usuario quiere forzar otro arquetipo.
4. **Confirmación** — preview del estado, botones [Cancelar] [Confirmar y catalogar].

Al confirmar, dispara los 8 pasos en orden y muestra progress bar:

```
[████████░░░░░░] 4/8 — Catalogando sinergias IA (12/44 pares)...
```

## §12 — Validación post-onboarding

Tras completar los 8 pasos, ejecutar checklist automático:

```sql
-- 1. PJ existe y está completo
SELECT COUNT(*) = 1 FROM agents WHERE nombre = ?;

-- 2. Tiene al menos 1 threshold
SELECT COUNT(*) >= 1 FROM agent_thresholds WHERE agente_id = ?;

-- 3. Tiene score_threshold
SELECT COUNT(*) = 1 FROM agent_score_thresholds WHERE agente_id = ?;

-- 4. Tiene los 6 pj_weapon_synergy
SELECT COUNT(*) = 6 FROM pj_weapon_synergy WHERE pj_id = ?;

-- 5. Tiene 44 pares en team_synergies (puede tomar horas)
SELECT COUNT(*) = 44 FROM team_synergies
  WHERE pj_a_id = ? OR pj_b_id = ?;

-- 6. Integridad
PRAGMA foreign_key_check;
PRAGMA integrity_check;
```

Si alguno falla, el wizard marca el PJ como **"Onboarding parcial"** y bloquea su uso en rankings hasta que se resuelva.

---

## §13 — Checklist operativo "TL;DR por patch"

Cuando salga un patch nuevo de ZZZ con 1-2 PJs:

```
□ 1. Esperar a que Prydwen publique data del PJ nuevo (~24-48 h post-release)
□ 2. Abrir wizard "Agregar PJ nuevo" en Configuración
□ 3. Cargar datos básicos (nombre, rol, elemento, M0 default si no lo tenés)
□ 4. Cargar stats: pegar screenshot HoYoLAB o ingresar manualmente
□ 5. Confirmar arquetipo (default por rol o override si escala con HP)
□ 6. Click "Confirmar y catalogar" → esperar ~5-10 min para los 44 pares IA
□ 7. Verificar splash art descargado en splash_arts/{id}_{nombre}.png
□ 8. (Cuando lo desbloquees in-game) Capturar su build real con RF-04
□ 9. (Cuando consigas su awakening) Reemplazar placeholder con texto real
□ 10. (Cuando hagas runs) RF-13 lo agrega automáticamente a tier list personal
```

Tiempo total esperado por PJ nuevo: **5-15 minutos** (la mayoría es esperar a la catalogación IA).
Costo IA esperado por PJ nuevo: **~$0.50** (incluido en el cap mensual default de $5).

---

## §14 — Decisiones cerradas (log)

| Fecha | Decisión | Justificación |
|-------|----------|---------------|
| 2026-04-26 | **Wizard manual como flujo canónico** | RF-04 puede detectar el PJ nuevo, pero el usuario debe confirmar antes de gastar IA + descargar splash art. Auto-onboarding sin confirmación = riesgo de contaminar DB con OCR ambiguo. |
| 2026-04-26 | **Stats M0 standard de Prydwen como fallback** | Permite onboardear el PJ antes de tenerlo (planificación de roster). Cuando el usuario lo equipe, RF-04 actualiza con stats reales. |
| 2026-04-26 | **Arquetipo inferido por rol con override manual** | 90% de los casos cae en la regla por rol; el 10% restante (Manato HP_DISRUPT, Disruptivos ambiguos) requiere checkbox explícito. |
| 2026-04-26 | **44 pares IA encolados automáticamente, no on-demand** | El usuario no debería tener que disparar manualmente la catalogación — es transparente. Solo se interrumpe si excede cap de costo. |
| 2026-04-26 | **Convención splash arts `{id:02d}_{nombre}.png`** | Mantiene orden cronológico de incorporación al roster. RF-11 resuelve la ruta sin lookup adicional. |
| 2026-04-26 | **Awakening como placeholder al inicio** | El texto del awakening solo se obtiene comprando siluetas en la tienda Silueta Potencial — puede tomar semanas. Placeholder permite operar el sistema sin él. |
| 2026-04-26 | **Validación bloqueante post-onboarding** | Si los 6 checks no pasan, el PJ queda en estado "parcial" y no participa en rankings. Evita resultados incorrectos por data incompleta. |
