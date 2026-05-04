# QA-03 — OCR y Captura (RF-04 / RF-05 / RF-09)

**Capa:** L2 (unit con imágenes fixture) + L3 (integration con DB) + L4 (real con ZZZ corriendo)
**RFs cubiertos:** RF-04 (sync equipo), RF-05 (sync upgrade), RF-09 (OCR híbrido).
**Cuándo consultar:** al implementar `ocr_backend.py`, `ocr_tesseract.py`, `ocr_paddle.py`, `sync_equip.py`, `sync_upgrade.py`, `detector.py`.

> **Principio:** RNF-02 prohíbe inventar valores. Si el OCR no está seguro, el campo se marca `requires_review=1` en lugar de devolver una alucinación. Mejor pedir a Daniel que valide manualmente que mover datos basura a la DB.

---

## 1. Anatomía del pipeline a validar

```
[ZZZ frame] → detector.py (template match) → capturer.py (ROI crop)
            → ocr_tesseract (texto: set name, slot, stat names)
            → ocr_paddle    (números: valores, +N rolls)
            → analyzer.py (parser → estructura disco)
            → diff vs DB   (RF-04 cambio equipo  /  RF-05 upgrade)
            → scoring.py
            → recommender.py → toast
```

Cada nodo tiene su propio nivel de QA.

---

## 2. Templates del detector (RF-04 / RF-05)

`detector.py` usa template matching de OpenCV sobre regiones fijas. Templates viven en `app/resources/templates/`.

### 2.1 Templates esperados (mapeados desde `Screenshots_Triggers/Discos_Triggers/`)

| Carpeta fuente | Template | Trigger detectado |
|----------------|----------|-------------------|
| `01_Pantalla_Resultado_Desafio` | `result_disc_modal.png` | Modal de resultado tras desafío con disco |
| `02_Detalle_Disco_Desde_Resultado` | `result_disc_detail.png` | Vista detalle del disco recién obtenido |
| `03_Pantalla_Agente_Discos_Equipados` | `agent_discs_grid.png` | Grid de 6 slots de un PJ |
| `04_Inventario_Disco_Vista_Individual` | `inv_disc_solo.png` | Disco individual visto desde Inventario |
| `05_Upgrade_PRE_nivel0` | `upgrade_pre_lv0.png` | Pantalla pre-upgrade desde nivel 0 |
| `06_Upgrade_PRE_nivel3_6_9_12` | `upgrade_pre_lvN.png` | Pre-upgrade desde nivel ≥3 |
| `07_Upgrade_POST_animacion_confirmacion` | `upgrade_post.png` | Pantalla post-upgrade con confirmación |
| `08_Pantallas_Menu_Transicion` | `menu_transition.png` | Pantalla de transición (pausar polling) |
| `11_Tienda_Musica_Afinacion` | `music_shop.png` | Tienda Música (origen alternativo de upgrade) |

### 2.2 Test L2 del detector
```python
# app/tests/unit/test_detector.py
import pytest
from app.core.detector import detect_screen

@pytest.mark.parametrize('image,expected_screen', [
    ('fixtures/screens/result_disc_modal.png',  'result_disc_modal'),
    ('fixtures/screens/result_disc_detail.png', 'result_disc_detail'),
    ('fixtures/screens/agent_discs_grid.png',   'agent_discs_grid'),
    ('fixtures/screens/menu_transition.png',    'menu_transition'),
    ('fixtures/screens/random_combat.png',      None),                # debe NO matchear
])
def test_detector(image, expected_screen):
    assert detect_screen(image, threshold=0.85) == expected_screen
```

**Falsos positivos** (matchear `result_disc_modal` cuando estoy en combate): el threshold debe estar calibrado para que cero frames de combate disparen capturas. Test L4 obligatorio: 5 minutos de gameplay puro sin abrir menú no deben generar **ninguna** entrada en `inventory_disc_evaluations`.

### 2.3 Resoluciones soportadas
Cada template debe tener variantes por resolución del usuario:

| Resolución | Frecuencia (DaniBOD) | Estado template |
|------------|----------------------|-----------------|
| 1920x1080 | principal | obligatoria v1 |
| 2560x1440 | secundaria | obligatoria v1 |
| 3840x2160 | post-v1 | nice-to-have |
| Ultra-wide 3440x1440 | post-v1 | nice-to-have |

`Screenshots_Triggers/Discos_Triggers/10_Variantes_Resolucion/` debe contener al menos un disco capturado en cada resolución soportada.

---

## 3. OCR — golden set de capturas

`app/tests/fixtures/ocr_golden/` contendrá 50+ capturas reales con su **transcripción esperada** en `.json` adyacente.

### 3.1 Estructura
```
fixtures/ocr_golden/
  001_polar_metal_slot4_atk30_4subs.png
  001_polar_metal_slot4_atk30_4subs.json
  002_jazz_caotico_slot5_anomaly_mastery_3rolls.png
  002_jazz_caotico_slot5_anomaly_mastery_3rolls.json
  ...
```

JSON esperado:
```json
{
  "set_name_es": "Polar Metal",
  "set_name_en": "Polar Metal",
  "slot": 4,
  "main_stat": "ATK%",
  "main_valor": 30.0,
  "substats": [
    {"stat": "crit_rate", "valor": 9.6, "rolls": 4},
    {"stat": "crit_dmg",  "valor": 19.2,"rolls": 4},
    {"stat": "atk_pct",   "valor": 9.6, "rolls": 4},
    {"stat": "pen_pct",   "valor": 4.8, "rolls": 1}
  ],
  "nivel": 15,
  "fuente_captura": "agent_view",
  "resolucion": "1920x1080"
}
```

### 3.2 Métricas de precisión esperadas
Sobre el golden set:

| Campo | Backend | Precisión objetivo | Falla si |
|-------|---------|--------------------|---------|
| `set_name_es` | Tesseract | ≥ 98% exact match | < 95% |
| `slot` | regla determinística (posición del disco) | 100% | cualquier error |
| `main_stat` | Tesseract | ≥ 97% | < 95% |
| `main_valor` | PaddleOCR | ≥ 99% (es número grande) | < 97% |
| `substat_name` | Tesseract | ≥ 95% | < 90% |
| `substat_valor` | PaddleOCR | ≥ 95% (decimales) | < 90% |
| `rolls` (+N) | PaddleOCR + regex | ≥ 98% | < 95% |
| `nivel` | PaddleOCR | ≥ 99% | < 97% |

### 3.3 Test L2 sobre golden set
```python
# app/tests/unit/test_ocr.py
import pytest, json
from pathlib import Path
from app.core.analyzer import analyze_disc

def collect_golden():
    base = Path('fixtures/ocr_golden')
    return [(p, p.with_suffix('.json')) for p in base.glob('*.png')]

@pytest.mark.parametrize('img_path,json_path', collect_golden())
def test_ocr_golden(img_path, json_path):
    expected = json.loads(json_path.read_text())
    actual   = analyze_disc(img_path)

    assert actual.set_name_es  == expected['set_name_es']
    assert actual.slot         == expected['slot']
    assert actual.main_stat    == expected['main_stat']
    assert abs(actual.main_valor - expected['main_valor']) < 0.5
    assert actual.nivel        == expected['nivel']

    for got, exp in zip(actual.substats, expected['substats']):
        assert got.stat  == exp['stat']
        assert abs(got.valor - exp['valor']) < 0.3
        assert got.rolls == exp['rolls']
```

### 3.4 Métrica agregada
```python
def test_ocr_overall_precision():
    results = run_ocr_over_golden()
    precision = sum(r.exact_match for r in results) / len(results)
    assert precision >= 0.95   # criterio aceptación global RF-09
```

---

## 4. Edge cases visuales

### 4.1 Iluminación / fondos animados
ZZZ tiene fondos con animación. El template matching puede fallar si el fondo cambia entre frames. **Mitigación:** templates capturan solo la región estática del modal (no el fondo). Test L2: animar fondo sintéticamente sobre el frame del disco y verificar que `detect_screen` y `analyze_disc` siguen acertando.

### 4.2 Idiomas y fuentes
DaniBOD juega en español. La DB guarda nombres en español. El OCR debe:
- Reconocer caracteres acentuados (á, é, í, ó, ú, ñ).
- Manejar variantes Unicode (`a` vs `á`).
- Caer a `nombre_en` como fallback si Tesseract no logra texto en español.

```python
def test_ocr_acentos():
    img = 'fixtures/ocr_golden/099_armonia_umbria.png'
    assert analyze_disc(img).set_name_es == 'Armonía umbría'
```

Si el usuario en el futuro juega en inglés u otro idioma, el OCR debe permitir override en `user_config.toml::ocr.idioma_juego`.

### 4.3 Disco con substats no visibles (sub4 todavía bloqueado)
Niveles 0-9 pueden tener `sub4` no desbloqueado todavía. El parser debe:
- Detectar el placeholder visual (línea de puntos / "?" / casilla vacía).
- Devolver `sub4=None, val4=None, rolls4=0`.
- NO inventar un sub4.

### 4.4 Números con coma como decimal
ZZZ en español puede mostrar `9,6%` en vez de `9.6%`. PaddleOCR + parser deben normalizar a punto.

### 4.5 Rolls badge `+N`
El badge `+N` (1-4 rolls) está en la esquina del substat. Test L2:
```python
@pytest.mark.parametrize('img,expected_rolls', [
    ('fixtures/rolls/sub_no_badge.png',  0),
    ('fixtures/rolls/sub_plus1.png',     1),
    ('fixtures/rolls/sub_plus4.png',     4),
])
def test_rolls_detection(img, expected_rolls):
    assert detect_rolls(img) == expected_rolls
```

### 4.6 Disco con set duplicado en juego (post-patch)
Si HoYoverse renombra un set y el OCR lee el nuevo nombre antes de que `disc_sets` se actualice, debe:
- Loguear `WARN: set_name='X' no encontrado en disc_sets`.
- Ofrecer al usuario opción "agregar al catálogo" via wizard de Onboarding_Nuevos_Assets.md.
- NO insertar el disco silenciosamente con `set_id=NULL` que rompería FK.

---

## 5. Diff PRE/POST en RF-05 (upgrade)

`sync_upgrade.py` recibe dos snapshots OCR (PRE upgrade y POST upgrade) y debe identificar exactamente qué cambió.

### 5.1 3 salidas posibles según RF-Logic_Captura_Discos
| Salida | Condición |
|--------|-----------|
| `sub_unlocked` | PRE tenía `sub4=None`; POST tiene `sub4=X` |
| `sub_rolled` | mismo set de substats; uno tiene `valor` mayor en POST con `rolls+1` |
| `multi_rolls` | múltiples substats incrementaron simultáneamente (raro pero posible si subió 2+ niveles) |

### 5.2 Test L2 del diff
```python
def test_diff_sub_unlocked():
    pre  = load('fixtures/upgrade/lv9_3subs_pre.json')
    post = load('fixtures/upgrade/lv12_4subs_post.json')
    diff = compute_diff(pre, post)
    assert diff.tipo == 'sub_unlocked'
    assert diff.sub_added.stat == post.substats[3].stat

def test_diff_sub_rolled():
    pre  = load('fixtures/upgrade/lv6_4subs_pre.json')
    post = load('fixtures/upgrade/lv9_4subs_post.json')
    diff = compute_diff(pre, post)
    assert diff.tipo == 'sub_rolled'
    assert diff.sub_changed.rolls_delta == 1

def test_diff_no_change_alert():
    same = load('fixtures/upgrade/lv9_pre.json')
    diff = compute_diff(same, same)
    assert diff.tipo == 'no_change'
    assert diff.alert == 'OCR puede haber fallado: no detectó cambio'
```

### 5.3 Edge case: upgrade de 0→3 con `sub_unlocked` pero PRE no tenía sub4 visible
RF-Logic_Captura_Discos resuelve esto con la decisión "¿sub4 ya estaba desbloqueada al PRE?". Test:
```python
def test_diff_sub4_was_unlocked_pre():
    pre = {... 'sub4': 'crit_rate', 'val4': 2.4, 'rolls4': 0, 'nivel': 9}
    post = {... 'sub4': 'crit_rate', 'val4': 4.8, 'rolls4': 1, 'nivel': 12}
    diff = compute_diff(pre, post)
    assert diff.tipo == 'sub_rolled'        # NO sub_unlocked
    assert diff.sub_changed.stat == 'crit_rate'
```

---

## 6. Confidence threshold y `requires_review`

OCR retorna confianza por campo. Política:

```python
THRESHOLDS = {
    'set_name': 0.85,
    'main_stat': 0.85,
    'main_valor': 0.90,
    'substat_name': 0.80,
    'substat_valor': 0.85,
    'rolls': 0.90,
    'nivel': 0.95
}

def evaluate(field, value, confidence):
    if confidence < THRESHOLDS[field]:
        return ReviewMarker(field=field, ocr_value=value, confidence=confidence)
    return value
```

**Política frente a un disco con cualquier `requires_review`:**
- NO insertar en `inventory_discs` automáticamente.
- Mostrar al usuario el disco capturado side-by-side con la transcripción OCR.
- Permitir corrección manual antes de insertar.
- Loguear en `inventory_disc_evaluations.notas`: `"requires_review: campos=[set_name(0.72), substat_2_valor(0.78)]"`.

---

## 7. Pruebas reales en juego (L4)

Daniel valida el pipeline completo:

| Caso L4 | Pasos | Resultado esperado |
|---------|-------|---------------------|
| 5 min combate puro | gameplay sin abrir menús | 0 capturas en `inventory_disc_evaluations` |
| Equipar disco S-rank de inventario | abrir Inventario → equipar disco | toast verde <500 ms con score visible |
| Subir disco 0→3 | abrir disco → upgrade | toast con tipo=sub_unlocked + delta score |
| Subir disco 9→12 | upgrade | toast con tipo=sub_unlocked si era 3 subs, sub_rolled si era 4 |
| Borrar un disco basura | trash desde Inventario | NO debe quedar fila en `inventory_discs` |
| Cambiar resolución de pantalla | jugar 30 min | sin falsos positivos del detector |
| ZZZ minimizado | otra app en foreground | captura pausada (`monitor.py` detecta) |

Daniel registra en `Documentacion/QA/evidencia/RF-09/<fecha>_<caso>.md`:
- Screenshot del frame original.
- JSON de salida del OCR.
- Anotación humana de cada divergencia (`set_name correcto pero substat 3 mal: era pen_pct, OCR dijo def_pct`).

---

## 8. Mitigación: cuando el OCR falla repetidamente

Si en un mes Daniel registra >5 frames donde el OCR alucina:

1. Capturar los frames como **nuevos golden cases**.
2. Investigar si es:
   - Tesseract config (idioma, modelo).
   - PaddleOCR modelo (chino genérico vs detect_text fine-tuned).
   - Preprocessing (contraste, escala, denoising).
   - Backend abstracto inadecuado → migrar a Claude/GPT-4o vision (RF-09 ya tiene la interfaz preparada).
3. Documentar fix en `audit/ocr_iteration_<n>.md`.
4. Re-correr `test_ocr_overall_precision`; sólo merge si vuelve a ≥0.95.

---

## 9. Latencia OCR — presupuesto

RNF-06 + RF-11: presupuesto interno 180 ms para OCR. Test:

```python
import time
def test_ocr_latency():
    img = 'fixtures/ocr_golden/001_polar_metal.png'
    times = []
    for _ in range(100):
        t = time.perf_counter()
        analyze_disc(img)
        times.append((time.perf_counter() - t) * 1000)
    p50 = sorted(times)[50]
    p99 = sorted(times)[99]
    assert p50 < 120          # margen al budget
    assert p99 < 200          # tope absoluto
```

Si Tesseract es el cuello de botella (suele serlo), considerar:
- Crop más agresivo (regiones de texto más pequeñas).
- Cache de modelos (cargar 1 vez al inicio, no por llamada).
- Paralelizar Tesseract + PaddleOCR (corren sobre regiones distintas, son independientes).

---

## 10. Cobertura mínima antes de cerrar Fase 2

- [ ] Templates capturados para cada pantalla del catálogo (§2.1) en al menos 1920x1080 y 2560x1440.
- [ ] 50+ golden cases en `fixtures/ocr_golden/` con JSON adyacente.
- [ ] `test_ocr_overall_precision ≥ 0.95`.
- [ ] `test_detector` con 0 falsos positivos sobre fixtures de combate.
- [ ] Latencia OCR p99 < 200 ms.
- [ ] L4 Daniel: 5 sesiones de gameplay (≥30 min cada una) sin captura indebida.
- [ ] L4 Daniel: 30+ discos equipados/borrados/subidos con OCR validado.

---

*RF-09 explícitamente dejó la interfaz abstracta para poder cambiar de backend si Tesseract+Paddle no alcanzan. Ese fallback (a Claude/GPT-4o vision) está documentado pero no requerido en v1; sólo si la métrica de precisión queda <0.95 tras 3 iteraciones de tuning.*
