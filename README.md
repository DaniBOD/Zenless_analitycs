# ZZZ Analytics — analizador de cuenta para Zenless Zone Zero

Sistema de escritorio que **mira la pantalla del juego** y lleva la contabilidad de una cuenta de
Zenless Zone Zero: discos, personajes, armas y las decisiones que hay que tomar con cada drop.

No lee la memoria del proceso, no simula clicks, no automatiza gameplay. Sólo pixels y OCR.

> **Proyecto de un solo usuario.** Está construido para la cuenta de DaniBOD (UID 1000860143,
> servidor America) y muchas decisiones de diseño asumen ese roster. No es un producto: es una
> herramienta personal cuyo desarrollo se documenta en público.

---

## El problema

ZZZ te da un disco al terminar una expedición y te pregunta, implícitamente, "¿lo guardo o lo
tiro?". Para responder bien hace falta cruzar el disco contra 50+ personajes, sus thresholds, sus
sets y lo que ya tienen equipado. El juego no te da nada de eso, y hacerlo a mano por cada drop no
es viable.

La app resuelve eso mirando: detecta en qué pantalla estás, lee el disco, lo puntúa contra el
roster y te tira un toast con la recomendación — sin que salgas del juego.

## Cómo funciona

```
captura de pantalla  →  detector de pantalla  →  recorte de ROIs  →  OCR híbrido
                                                                          ↓
        toast  ←  recomendación  ←  scoring  ←  identidad del dueño  ←  parser
                                       ↓
                                  SQLite (sync)
```

**El detector es la pieza central.** Antes de leer nada, la app tiene que saber *qué* está mirando:
hoy distingue **30 pantallas** por template matching (`S1`–`S30`), desde el inventario general de
discos hasta el diálogo de confirmación de un desmontaje. Cada pantalla tiene su propio parser y su
propia política de escritura.

**El OCR es híbrido**: Tesseract para texto, PaddleOCR para números. Ninguno de los dos solo daba
resultados aceptables sobre la tipografía del juego.

**La identidad del personaje no sale del texto**, sale del avatar. Un descriptor visual compara el
badge del PJ contra una librería cosechada del propio juego, en tres superficies distintas (la
grilla, el panel de detalle, la fila del inventario) que se corrigen entre sí. Si ninguna lo puede
nombrar, la app **se abstiene** en vez de adivinar.

## Compatibilidad con los ToS de HoYoverse

Es una restricción de diseño, no un detalle:

| ✅ permitido | ❌ prohibido en este repo |
|---|---|
| `mss` / `win32` para capturar imagen | `pymem`, lectura de memoria del proceso |
| OCR sobre esa imagen | inyección de DLL |
| `pynput.keyboard.Listener` (leer hotkeys) | `keyboard.send()`, simulación de inputs |
| SQLite local | automatización de gameplay |

El equivalente legal conocido es Inventory Kamera (Genshin): observar la pantalla es lo mismo que
mirarla vos. Cualquier PR que cruce esa línea se rechaza.

---

## Estado actual

**Fase 2 (motor de captura) en curso.** Lo que sigue está medido sobre el repositorio, no estimado.

### Anda hoy

- **Detector de 30 pantallas** con máquina de estados y transiciones válidas.
- **Captura y persistencia** desde el panel de equipamiento del PJ, el inventario global de discos,
  el modal de mejora, la sustitución entre personajes, el desmontaje por lotes, el farmeo por
  baterías, la tienda de música y los resultados de sintonización.
- **Identidad de personaje por avatar** en tres superficies, con abstención explícita.
- **Censo de la cuenta**: pasada guiada que sincroniza roster y discos observando, con contador de
  progreso leído de la propia pantalla.
- **UI**: ícono de bandeja, toast flotante y panel en vivo (PySide6), empaquetado como `.exe`.
- **Instrumental de latencia** en una base aparte, para que las métricas no contaminen los datos.

### Todavía no

- El optimizador de builds completo (RF-06) y el team-aware con IA (RF-12).
- Validación lategame y tier list personal (RF-13).
- Optimizador de W-Engines (RF-14).
- El panel de 9 pestañas del diseño de UI: hoy existen la vista en vivo y el diálogo de roster.

### Números

| | |
|---|---|
| pantallas reconocidas | 30 |
| tablas en la base | 32 · 30 migraciones aplicadas |
| tests | **2446 passed**, 17 skipped, 1 xfailed |
| código de la app | ~72 000 líneas · 50 módulos en `app/core/` |
| código de tests | ~25 000 líneas |
| documentos de ingeniería | 67 en `Documentacion/Dev_IA/` |

> El inventario de discos está **a mitad de un re-censo** (115 de ~405). La base se vació a
> propósito el 2026-08-17 para re-sincronizar observando, así que los conteos de `inventory_discs`
> no son el inventario de la cuenta todavía.

---

## Instalación

Windows 10/11, Python 3.11+.

```bash
py -3.11 -m venv .venv && .venv\Scripts\activate && pip install -e ".[dev]"
```

**Tesseract es un requisito duro**, no opcional: sin él varias pantallas fallan cerrado. Se instala
aparte del `pip install`.

Para levantar la app:

```bash
python -m app.main
```

Y para regenerar el ejecutable:

```bash
powershell -ExecutionPolicy Bypass -File tools\rebuild.ps1
```

### Hotkeys

| tecla | qué hace |
|---|---|
| `F8` | cierra la pasada de censo en curso |
| `F9` | muestra/oculta el panel principal |
| `F10` | pausa/reanuda el monitor |
| `F11` | registra una run de lategame *(Fase 4)* |

`F12` está libre a propósito: la reservan los depuradores y varias grabadoras de pantalla.

---

## Reglas no negociables

Cuatro restricciones que atraviesan todo el código. Están enunciadas en
[`CLAUDE.md`](./CLAUDE.md) y se hacen cumplir en los tests.

- **RNF-01 · ETL sin fallas.** Toda escritura a la base va con backup previo, transacción y
  `PRAGMA foreign_key_check` + `integrity_check`. Los audits **no mutan** lo que auditan, y se
  verifica por sha256, no por buena intención.
- **RNF-02 · Dato no confirmado ⇒ NULL.** Nunca inventar una stat, un threshold o un nombre. Si el
  OCR no está seguro, se abstiene — pero abstenerse no puede costar el resto del dato.
- **RNF-03 · Sólo pixels.** Ver arriba.
- **RNF-06 · Responsividad.** Presupuestos de latencia por superficie (toast < 500 ms, lookups
  < 50 ms) medidos con instrumental propio, no estimados.

---

## Documentación

El repositorio documenta el proceso, no sólo el resultado.

| dónde | qué hay |
|---|---|
| [`Documentacion/Dev_IA/00_Practicas_Aprendidas.md`](./Documentacion/Dev_IA/00_Practicas_Aprendidas.md) | **empezá por acá** — 12 reglas, cada una con el error concreto que la generó |
| [`Documentacion/Dev_IA/`](./Documentacion/Dev_IA/) | 67 bitácoras de implementación, diagnóstico y QA |
| [`Documentacion/RF_*/`](./Documentacion/) | diseño cerrado de cada requerimiento funcional |
| [`Documentacion/Modelo_Relacional/`](./Documentacion/Modelo_Relacional/) | schema canónico y diagrama ER |
| [`Documentacion/QA/`](./Documentacion/QA/) | plan de pruebas y regresión por parches |
| [`project-context-IA.md`](./project-context-IA.md) | snapshot maestro del estado |
| [`CLAUDE.md`](./CLAUDE.md) | instrucciones para el agente que trabaja en el repo |

Los `Dev_IA/` son lo más interesante para alguien de afuera: varios documentan **hipótesis mías que
la medición desmintió**, que suelen valer más que el arreglo que salió después.

El README anterior —1214 líneas de diseño de la Fase 1— se archivó en
[`Documentacion/README_Referencia_Fase1_2026-05.md`](./Documentacion/README_Referencia_Fase1_2026-05.md).

## Stack

Python 3.11 · SQLite · PySide6 · OpenCV · mss · Tesseract · PaddleOCR · PyInstaller · pytest ·
ruff. La API de Anthropic se usa sólo para catalogación offline (RF-12), con tope de gasto
configurable.

---

*Desarrollado con Claude Code. Las decisiones de diseño, los errores y las correcciones están en
`Documentacion/Dev_IA/`.*
