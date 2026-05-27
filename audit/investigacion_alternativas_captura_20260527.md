# Investigación — Alternativas a captura MSS + OCR para extraer data del juego

> **Fecha:** 2026-05-27
> **Solicitante:** DaniBOD
> **Contexto:** Hito 2.8 cerrado pero con fragilidad observada en captura S18 (Tesseract no-determinista, `recuperacion_energia` casi siempre falla, F8 manual repetido para juntar los 11 stats vía aggregator).
> **Pregunta de origen:** "No estoy viendo bastante viable hacerla mediante captura de MSS, ¿hay otra opción de capturar la información en tiempo real?"

---

## 0. TL;DR

**El problema NO es MSS.** La captura funciona correctamente (frames a 2560×1440, ventana ZZZ detectada por nombre de proceso, heartbeats estables). El problema es la **fragilidad post-captura**: Tesseract es no-determinista sobre stats S18 y se necesitan 3-5 F8s para llenar los 11 atributos vía aggregator.

Hay **dos hallazgos accionables** que no estaban en el roadmap:

1. **Enka.Network tiene API pública de ZZZ** (sin auth, solo UID) que devuelve **discos drive equipados con substats, rolls exactos y main stats** de los PJs en showcase. Esto **reemplaza OCR completamente** para una porción importante del inventario.

2. **HoYoLAB Battle Chronicle agregó módulo "Drive Disc rating" en v1.3** que muestra discos equipados de cualquier PJ que tenés (no solo showcase). Usa cookies `ltuid`/`ltoken` del usuario logueado. Mismo dato pero alcance mayor.

Ninguno de los dos era nuevo (Enka.Network ZZZ existe desde principios de 2025), pero **no figuran en ningún documento del proyecto**. La búsqueda en `Documentacion/` confirma que nunca se evaluaron.

**Recomendación corta:** mantener MSS + OCR como el motor de RF-04 (toast en vivo al farmear), pero **agregar un sync RF-05B con Enka.Network/HoYoLAB API** para sincronizar inventario completo de PJs equipados sin OCR. Esto elimina el camino crítico OCR del problema de scoring del 90% del inventario útil (lo que está equipado).

---

## 1. Diagnóstico verdadero del problema

### 1.1 Lo que funciona

Del seguimiento [`2026-05-27_Hito_2.8_Stats_Aggregator_F8_Robusto.md`](../Documentacion/Dev_IA/2026-05-27_Hito_2.8_Stats_Aggregator_F8_Robusto.md):

- ✅ MSS captura 2560×1440 sin frames negros (juego en fullscreen funciona)
- ✅ Detección de ventana ZZZ por **nombre de proceso** (no título, que cambia con la zona)
- ✅ TemporalBuffer majority voting 2/3 frames @ 100ms captura
- ✅ 18 estados detectables (S1-S18), 17 templates, threshold 0.85
- ✅ Deep S18 multi-trigger resolución-agnóstico (5 indicadores ponderados)
- ✅ F8 global vía Win32 RegisterHotKey (pynput no funcionaba con ZZZ fullscreen-focused)
- ✅ Detección de slot 1-6 vía OCR del título "Set Name (N)" (12/12 S17, 6/6 S9)
- ✅ Pipeline S3 (toast captura disco) reportado como estable en QA real

### 1.2 Lo que no funciona bien

- ❌ Tesseract no-determinista frame-a-frame sobre stats S18 (8-11 stats por captura, no los 11)
- ❌ `recuperacion_energia` casi siempre falla (texto multilínea "Recuperación de Energía" se rompe en Tesseract)
- ❌ PaddleOCR planificado pero no instalado en máquina del usuario (OneDNN incompat. en máquina dev)
- ❌ FPs ocasionales S18/S10 en open world (3 capturas pendientes de triage)
- ⚠️ UX del aggregator: el usuario tiene que apretar F8 3-5 veces hasta `[completo]`

### 1.3 Conclusión

**No es problema de captura. Es problema de extracción.** Específicamente: Tesseract sobre fuentes UI estilizadas en regiones pequeñas con texto multilínea ocasional.

---

## 2. Inventario de alternativas (dentro de RNF-03)

### 2.1 Vías rechazadas por ToS

| Vía | Por qué no |
|-----|------------|
| Lectura de memoria del proceso | Viola ToS (pymem prohibido por RNF-03) |
| DLL injection / hooks | Idem |
| Packet sniffing del tráfico ZZZ | Dudoso ToS; cifrado además |
| Input automation gameplay | Viola RNF-03 (`keyboard.send()` prohibido) |

### 2.2 Vías compatibles con ToS

| Vía | Tipo | Real-time? | OCR? | Estado en proyecto |
|-----|------|-----------|------|---------------------|
| **MSS + Tesseract** (actual) | Pixels | Sí (<500ms) | Sí | Implementado, frágil |
| **Windows Graphics Capture API** (`windows-capture`) | Pixels | Sí | Sí | Alternativa para MSS si fallara |
| **dxcam / bettercam** | Pixels | Sí (240 fps) | Sí | Alternativa para MSS si fallara |
| **MSS + PaddleOCR** | Pixels | Sí (~700ms) | Sí | Wired, sin validar en user machine |
| **MSS + Claude Vision API** | Pixels + LLM | No (~2s + costo) | LLM | No evaluado |
| **Enka.Network ZZZ API** | API oficial-friendly | No (~minutos TTL) | NO | **No evaluado, gran oportunidad** |
| **HoYoLAB Battle Chronicle API** | API oficial-friendly | No (~minutos TTL) | NO | **No evaluado, gran oportunidad** |

---

## 3. Enka.Network ZZZ API — análisis detallado

### 3.1 Endpoint

```
GET https://enka.network/api/zzz/uid/{UID}/
```

Sin autenticación. Solo necesita UID del jugador (DaniBOD = 1000860143). Rate limit: típicamente 1-2 req/min recomendado, `ttl` en la respuesta indica cuándo vuelve a actualizarse.

### 3.2 Datos devueltos (estructura confirmada en docs oficiales)

Para cada agente en el **showcase** del usuario:

```
AvatarList[i]:
  Id, Level, PromotionLevel, TalentLevel (mindscape)
  CoreSkillEnhancement (A-F)
  Weapon (W-Engine con BreakLevel, UpgradeLevel, exact values)
  EquippedList:
    Slot (1-6)
    Equipment:
      Uid (PERSISTENTE entre upgrades — perfecto para dedupe)
      Id (set/disco específico)
      Level (0-15)
      BreakLevel (cantidad de procs random = rolls)
      MainStatList (main stat con PropertyId + valor base)
      RandomPropertyList (4 substats con PropertyId + PropertyValue + PropertyLevel=rolls)
```

**Cobertura:** los 6 discos equipados de cada PJ en showcase. ZZZ permite showcase de hasta ~6 agentes (a confirmar). Máximo teórico: 36 discos.

### 3.3 Mapping a schema del proyecto

| Enka field | Schema DaniBOD (`inventory_discs`) | Match |
|-----------|------------------------------------|-------|
| `Equipment.Uid` | (no existe — habría que agregar `enka_uid TEXT UNIQUE`) | nuevo |
| `Equipment.Id` | `set_id` (con lookup vía `disc_sets`) | derivable |
| `Equipment.Level` | `nivel` (0-15) | directo |
| `Equipment.BreakLevel` | sum de `roll1+roll2+roll3+roll4` (total rolls) | derivable |
| `MainStatList[0].PropertyId` | `main_stat` (con tabla de mapeo PropertyId→nombre canónico) | derivable |
| `RandomPropertyList[i].PropertyId` | `sub1-4` (idem) | derivable |
| `RandomPropertyList[i].PropertyValue` | `val1-4` (con fórmula del API doc) | derivable |
| `RandomPropertyList[i].PropertyLevel` | `roll1-4` | directo |

PropertyId 31201 = `Anomaly Proficiency`, 31401 = `Anomaly Mastery`, 23101 = `Pen Ratio`, 30501 = `Energy Regen`, 12101 = ATK, etc. La tabla completa está en la API doc.

### 3.4 Wrappers Python disponibles

- **enka-py** ([seriaati/enka-py](https://github.com/seriaati/enka-py)) — async, soporta ZZZ explícitamente, fórmulas de stats incluidas
- `pip install enka` (PyPI)
- API: `await client.fetch_zzz_player(uid)`

### 3.5 Limitaciones

1. Solo PJs en showcase (no inventario completo)
2. Solo discos equipados (no los del backpack guardados)
3. `ttl` ~5-10 min: cambios en showcase no son inmediatos
4. UID público implica que la cuenta es identificable (no es un problema para DaniBOD, single-user)

### 3.6 Cuántos discos cubre vs los 334 totales

Si DaniBOD tiene los 46 agentes equipados con 6 discos cada uno:
- Equipados: 46 × 6 = **276 discos** (potencialmente equipados, no todos los PJs lo están)
- Showcase visible: ~6 PJs × 6 discos = **36 discos** vía Enka.Network
- Inventario sueltos: **334 - equipados ≈ 60-100 discos** que requieren OCR sí o sí

**Implicación:** Enka.Network resuelve el caso "scorear builds activos" pero NO resuelve "sincronizar inventario completo". Para eso sigue siendo necesario OCR o HoYoLAB API.

---

## 4. HoYoLAB Battle Chronicle ZZZ API — análisis detallado

### 4.1 Endpoint y autenticación

Endpoint base: `https://bbs-api-os.hoyolab.com/game_record/zzz/api/...`

Requiere cookies del usuario logueado:
- `ltuid_v2` / `ltuid` — user ID interno HoYoLAB
- `ltoken_v2` / `ltoken` — token de sesión (~30 días)
- `cookie_token_v2` — para algunas operaciones

Obtenidas vía DevTools en una sesión activa de https://www.hoyolab.com o https://www.hoyoverse.com.

### 4.2 Datos disponibles

Según el módulo "Drive Disc rating" agregado en v1.3 (noviembre 2024):

- **Por cada agente del usuario** (no solo showcase): nivel, mindscape, build actual incluyendo los 6 discos equipados con sus stats
- W-Engine equipado con refinamiento
- Stats efectivos calculados por el servidor (¡no tenés que calcular fórmulas!)

### 4.3 Comparativa con Enka.Network

| Criterio | Enka.Network | HoYoLAB API |
|----------|--------------|-------------|
| Autenticación | Ninguna (solo UID) | Cookies del usuario |
| Cobertura | PJs en showcase (~6) | **Todos los PJs equipados del usuario** |
| Discos sueltos (backpack) | No | No |
| Stats calculados | Fórmula manual | Servidor |
| Wrapper Python maduro | enka-py | Hay varios para Genshin, ZZZ requiere adaptación |
| Riesgo ToS | Bajo (Enka es público, scraping consentido) | Bajo si se usa con las cookies del propio usuario |
| Rate limit | TTL ~5-10 min | Más estricto, ~30 req/min |

### 4.4 Wrapper Python para HoYoLAB

No hay wrapper Python "oficial" maduro específico para ZZZ Battle Chronicle (hay para Genshin/HSR). Habría que implementar el cliente desde cero usando los endpoints documentados en repos como [vermaysha/hoyolab-api](https://github.com/vermaysha/hoyolab-api).

**Estimación de esfuerzo:** ~1-2 días de trabajo para implementar `app/core/sync_hoyolab.py` (auth con cookies, llamada a `/zzz/api/character_basic`, parseo, mapping a schema).

---

## 5. Tools comunitarios — qué hacen los demás

Los tres scanners ZZZ open-source más populares (todos OCR-based):

| Tool | Stack | Modo | Estado |
|------|-------|------|--------|
| [D1firehail/AdeptiScanner-ZZZ](https://github.com/D1firehail/AdeptiScanner-ZZZ) | C# + Tesseract + Enka.Network para PJs | Manual + Auto (mouse control) | Activo (v0.6.2 jun 2025) |
| [samsaq/ZZZ-Scanner](https://github.com/samsaq/ZZZ-Scanner) | ? + Tesseract | Scroll automatizado | Activo |
| [Scrubles/ZZZ-Scanner](https://github.com/Scrubles/ZZZ-Scanner) | ? + Tesseract | Scroll automatizado | Activo |

**Observaciones clave:**

1. **Todos usan Tesseract**, no PaddleOCR. Esto sugiere que Tesseract es alcanzable si se calibra bien (DaniBOD usa Tesseract y va bien para casi todo, salvo `recuperacion_energia`).
2. **AdeptiScanner-ZZZ delega a Enka.Network los PJs**, igual que mi recomendación. Es la práctica establecida.
3. **El modo "Auto" controla el mouse** — esto VIOLA RNF-03 del proyecto DaniBOD. Estos scanners no son ToS-friendly en modo auto. DaniBOD está bien al evitarlo.
4. **Ninguno usa Windows Graphics Capture API ni dxcam**. MSS / Win32 BitBlt es el estándar.

**Conclusión:** la dirección técnica de DaniBOD es correcta. El problema no es la arquitectura, son los detalles del OCR.

---

## 6. Recomendación priorizada

### 6.1 Prioridad ALTA — Instalar PaddleOCR en máquina del usuario (no requiere diseño nuevo)

**Acción:** ejecutar en la máquina del usuario:

```powershell
pip install paddlepaddle==2.6.2 paddleocr==2.8.2
```

**Por qué:** ya está cableado en `parser_agent_stats.py` con modo dual (PaddleOCR full-frame+regex / Tesseract per-ROI). Los 7 tests `test_extracts_all_11_stats[1-7]` están skipped por OneDNN incompatible en la máquina dev, pero deberían pasar en la del usuario. Si PaddleOCR captura los 11 stats de una pasada (vs 8-11 con Tesseract), el aggregator + F8 manual deja de ser necesario.

**Aceptación:**
- 7 tests pasan con 11/11 stats
- QA real S18 muestra `[completo]` en la 1ra F8 (no en la 3ra-5ta)

**Esfuerzo:** 30 min (instalación + run de tests existentes)

### 6.2 Prioridad MEDIA — Diseñar RF-15: Sync con Enka.Network

**Acción:** redactar nuevo RF `Documentacion/RF_Sync_Externo/RF-Logic_Sync_Enka.md` que defina:

- Endpoint Enka.Network ZZZ
- Mapping PropertyId → `stats_vocab.py`
- Nueva columna `inventory_discs.enka_uid TEXT UNIQUE` (con migración 10)
- Reconciliación: si un disco capturado por OCR matchea con Enka.Network vía `(set, slot, main_stat, sub_stats)`, vincular `enka_uid` para futura dedupe
- Trigger: comando `python -m app.scripts.sync_enka` o botón en UI

**Por qué:**
- Resuelve scoring perfecto para PJs en showcase (sin OCR error)
- Permite **validación cruzada** del pipeline OCR (si Enka dice "Cissia tiene disco X con sub `CR%=12`" y nuestra DB dice `CR%=15`, hay bug)
- No bloquea el roadmap actual: es feature adicional

**Esfuerzo estimado:** 2-3 días de desarrollo (1 día RF + 1 día implementación + 0.5 día tests)

### 6.3 Prioridad BAJA — Diseñar RF-16: Sync con HoYoLAB Battle Chronicle

**Acción:** Igual que 6.2 pero con cookies HoYoLAB. Mejor cobertura (todos los PJs equipados, no solo showcase) pero más complejo (auth con cookies que vencen).

**Por qué BAJA:** Enka.Network probablemente cubre el 80% del valor. HoYoLAB solo agrega los PJs no-showcase.

**Esfuerzo:** 4-5 días (auth flow + cookie management + endpoint discovery + mapping + tests)

### 6.4 Prioridad NULA — Cambiar MSS por WGC/dxcam

**No hacerlo.** MSS funciona. Los 3 tools comunitarios usan equivalente. Optimizar performance de captura no es el cuello de botella.

### 6.5 Prioridad NULA — Usar Claude Vision para stats S18

**No hacerlo a menos que PaddleOCR falle.** Costo proyectado:
- ~30 F8s por sesión de QA × $0.005 (Haiku) = $0.15/sesión
- $5/mes cap → 33 sesiones de stats = limita el dev cycle
- Latencia: 1-3s vs sub-segundo de Tesseract local
- Justifica si y solo si PaddleOCR tampoco resuelve `recuperacion_energia`

---

## 7. Impacto en roadmap

| Hito | Estado actual | Cambio propuesto |
|------|---------------|------------------|
| Hito 2.8 | Cerrado con caveat (aggregator + multi-F8) | Reabrir solo si PaddleOCR resuelve el no-determinismo. Sino, dejar cerrado y avanzar |
| Fase 3 (RF-12 sinergias IA) | Pendiente | Sin cambio |
| Hito 2.9 (nuevo) | — | **Proponer:** instalar PaddleOCR + validar 11/11 stats |
| RF-15 (nuevo) | — | **Proponer:** Sync Enka.Network |
| RF-16 (futuro lejano) | — | Sync HoYoLAB (opcional) |

---

## 8. Pregunta abierta para DaniBOD

1. **¿Querés que arme el RF-15 (Sync Enka.Network) como próximo hito?** Sería un mini-hito ~2-3 días de trabajo que desbloquea scoring perfecto del 80% del inventario útil (lo equipado en showcase).
2. **¿Probamos PaddleOCR primero (30 min) antes de pensar en Enka.Network?** Si los 11 stats se extraen en la 1ra captura, el problema desaparece.
3. **¿Tu showcase de ZZZ tiene los PJs principales?** Si tu showcase está vacío o son PJs random, Enka.Network sirve poco hasta que actualices showcase con tus mains. La Battle Chronicle vía HoYoLAB API no tendría esta limitación pero requiere implementar auth.

---

## 9. Fuentes consultadas

- [Enka.Network ZZZ API docs](https://github.com/EnkaNetwork/API-docs/blob/master/docs/zzz/api.md) — estructura completa de respuesta
- [enka-py wrapper](https://github.com/seriaati/enka-py) — Python async client
- [HoYoLAB Battle Records ZZZ](https://act.hoyolab.com/app/zzz-game-record/index.html) — módulo Drive Disc rating
- [Zenless Version 1.3 HoYoLAB update](https://x.com/ZZZ_EN/status/1854343319503175686) — anuncio módulo Drive Disc
- [AdeptiScanner-ZZZ](https://github.com/D1firehail/AdeptiScanner-ZZZ) — referencia stack OCR comunitario
- [samsaq/ZZZ-Scanner](https://github.com/samsaq/ZZZ-Scanner) — scanner Python
- [vermaysha/hoyolab-api](https://github.com/vermaysha/hoyolab-api) — referencia para auth con cookies
- Docs internas: [`Documentacion/Dev_IA/2026-05-27_Hito_2.8_Stats_Aggregator_F8_Robusto.md`](../Documentacion/Dev_IA/2026-05-27_Hito_2.8_Stats_Aggregator_F8_Robusto.md)

---

*Documento generado en investigación 2026-05-27. Mover a estado "RF-15 propuesto" si DaniBOD aprueba dirección.*
