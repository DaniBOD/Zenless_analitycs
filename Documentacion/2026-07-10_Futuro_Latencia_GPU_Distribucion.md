# Futuro — Optimización de latencia, uso de GPU y distribución multi-hardware

> **Fecha:** 2026-07-10
> **Tipo:** Nota de dirección futura (DIFERIDA — no es trabajo activo)
> **Owner:** DaniBOD (con asistencia IA)
> **Prioridad actual real:** cerrar la cobertura de extracción de TODAS las pantallas. Este documento se retoma recién cuando la extracción esté validada y correcta en todas ellas.

Este documento registra una conversación de planificación a futuro sobre cómo llevar el extractor a "latencia en milisegundos", qué rol juega la GPU, y cómo distribuir la app a distintos usuarios (amigos → comunidad ZZZ) sin depender de un hardware específico. Surgió a raíz de un consejo genérico de Google Gemini que, al contrastarlo con el código real del proyecto, resultó en varios puntos inaplicable.

---

## 0. TL;DR

- **Hoy el sistema corre 100% en CPU.** No usa GPU para nada (`controller.py:292` → `PaddleBackend(lang="es")` con `use_gpu=False`).
- **"Milisegundos" es alcanzable**, pero NO por el camino que sugería Gemini (CUDA), porque la GPU de Daniel es **AMD** y CUDA es exclusivo NVIDIA.
- La mayoría del consejo genérico de Gemini **ya estaba implementado** hace meses (hilo aparte, singleton OCR, MSS→numpy, gate por cambio de frame).
- Caminos válidos: **template/NCC para números** (el mejor) · **ONNX + DirectML** (GPU agnóstica de fabricante en Windows) · **`det=False`** (recognition-only).
- **Distribución:** CPU como baseline universal + GPU como acelerador OPCIONAL con fallback. Nunca exigir GPU.
- El **benchmark CPU-vs-GPU va en el primer arranque de la app**, no en el instalador. Se cachea en `user_config.toml`.
- **Antes de optimizar hay que medir:** instrumental `@measure_latency` + tabla `metrics_latency` (QA-06, hoy no existe).
- **Hay DOS latencias distintas** (no confundir): (a) *cómputo* — cuán rápido el OCR convierte un frame en datos (todo §1–9); (b) *frescura / responsividad de los logs* — cuán actualizado está lo que el log reporta respecto a lo que pasa en pantalla (§10). El "caso 1" del upgrade S10 es (b), no (a): más GPU no lo arregla.

---

## 1. Estado real del pipeline hoy (verificado en código 2026-07-10)

- **OCR 100% en CPU.** `app/ui/controller.py:292` instancia `PaddleBackend(lang="es")`; el default es `use_gpu=False` (`app/core/ocr_paddle.py:55`). Ninguna etapa toca la GPU.
- **Arquitectura ya madura**, no un loop ingenuo:
  - Monitor en `threading.Thread` daemon (`monitor.py:520`), separado del hilo de Qt → la GUI no se congela.
  - Loop rápido a **100 ms / 10 fps** (`_FAST_CAPTURE_MS`) solo para *clasificar* el frame.
  - OCR **gateado por firma de frame** (edge-triggered): corre solo cuando la pantalla cambió de verdad, no en cada frame. Cadencias por estado en `polling_cadence_ms` (500–4000 ms).
  - PaddleOCR es un **singleton lazy-loaded**: se carga 1 vez (~30 s init), después se reusa.
  - MSS → `np.array` → `cv2.cvtColor` directo, sin pasar por PIL.

**Conclusión:** el sistema ya aplica casi todo lo que un consejo genérico de optimización recomendaría. El margen real está en la etapa de OCR en sí, no en la orquestación.

---

## 2. Por qué el consejo de CUDA no aplica

El núcleo del consejo de Gemini era: *"instalá `paddlepaddle-gpu`, forzá CUDA, el OCR baja a 10–20 ms"*.

**Inaplicable en el hardware de Daniel:**

- La GPU es una **AMD RX 9060 XT 16GB** (ver `QA/QA-04_IA_Catalogadora.md` §9).
- **CUDA es exclusivo de NVIDIA.** `paddlepaddle-gpu` está compilado contra CUDA.
- AMD solo tiene aceleración vía **ROCm**, que es **Linux-only** → no usable en Windows.

> **Jerga:** *CUDA* = plataforma de cómputo GPU de NVIDIA. Sin placa NVIDIA, el paquete GPU de Paddle no sirve.

---

## 3. Caminos válidos para bajar latencia (en el hardware de Daniel)

Ordenados por retorno (ROI), todos dentro del stack actual:

1. **Template matching / NCC para los números — el camino ganador.**
   Ya existe el patrón probado en `app/core/slot_digit_matcher.py` (reconoce el dígito de slot por correlación cruzada normalizada). El vocabulario de stats es finito y chico (dígitos, `%`, pocos labels). Extenderlo a los valores numéricos **saca el OCR del camino crítico** para los datos que más importan → corre en microsegundos-a-pocos-ms, determinista, sin costo de RAM. Es "milisegundos" de verdad y es el patrón más idiomático del proyecto.

   > **Jerga:** *NCC (Normalized Cross-Correlation)* = medir cuánto se parece un recorte a una plantilla de referencia. Barato y determinista.

2. **ONNX + DirectML — aceleración GPU real en AMD.**
   Ya hay infra ONNX (`app/core/onnx_embedder.py`, `app/resources/avatar_embedder.onnx`). Los modelos de PaddleOCR se exportan a ONNX y se corren con `onnxruntime-directml`. Este es el reemplazo correcto de CUDA para placas AMD (y NVIDIA) en Windows.

3. **`det=False` (recognition-only).**
   Hoy `ocr.ocr(img, cls=False)` corre el detector DBNet igual sobre cada recorte. Como las ROIs ya se segmentan manualmente, pasar los recortes al reconocedor puro evita ese costo. (A verificar contra la API de PaddleOCR 2.8.1 instalada.)

---

## 4. ONNX ≠ GPU (aclaración clave)

Migrar a ONNX **no** significa "usar la GPU". Son cosas separadas:

- **ONNX** = *formato* de modelo, portable. No es GPU ni CPU por sí mismo.
- **ONNX Runtime** = motor que lo ejecuta, con "execution providers" (backends) seleccionables:
  - `CPUExecutionProvider` → CPU.
  - `DmlExecutionProvider` (DirectML) → GPU AMD **o** NVIDIA en Windows.
  - `CUDAExecutionProvider` → GPU NVIDIA.

Migrar a ONNX **habilita** el uso opcional de GPU; no lo obliga. Si no se configura provider de GPU, corre en CPU igual que ahora.

---

## 5. La tensión que hay que respetar (RNF-06)

- RNF-06 pide **RAM idle < 200 MB** y **CPU polling < 3 %**.
- Historia pesada: **fuga de memoria de ~28 GB** por crecimiento nativo per-inferencia de PaddleOCR, contenida con `FLAGS_eager_delete_tensor_gb=0.0` + watchdog de auto-restart (ver `audit/mem_diag_20260613.md`).
- Correr OCR **más rápido / más seguido pelea** con ese presupuesto (más inferencias = más presión de memoria + más CPU).

**Marco correcto:** la latencia es un objetivo **por-evento** (disco aparece → toast < 500 ms), **no de throughput** (no hace falta OCR a 30 fps). El loop rápido ya detecta a 100 ms; el OCR está gateado para correr solo cuando el disco cambió.

---

## 6. Distribución multi-hardware (amigos → comunidad ZZZ)

**El diseño actual CPU-only es el MÁS portable posible** — no depende de marca de GPU. Corre en AMD, NVIDIA, Intel, integradas.

**Estrategia recomendada:**

| Capa | Qué es | Requisito |
|------|--------|-----------|
| **Baseline (obligatorio)** | Todo en CPU, como hoy | Cualquier PC que corra ZZZ. Cero dependencia de GPU. |
| **Acelerador (opcional)** | ONNX + DirectML si hay GPU | Detección automática con *fallback* a CPU |

**Regla de oro:** nunca *exigir* GPU; ofrecerla como bonus con caída automática a CPU. Nadie queda afuera por su hardware.

**Sobre la GTX 1650 / "igualar requisitos del juego":**
- Una GTX 1650 es NVIDIA → CUDA funcionaría ahí, pero es la placa de *ese* usuario, no la de desarrollo (AMD). No se puede probar CUDA localmente.
- **DirectML cubre AMD y NVIDIA con un solo camino de código** → es la apuesta para distribución, no CUDA.
- **No atar el requisito de la app al del juego.** La app es liviana comparada con renderizar ZZZ; el requisito real es "una PC que corra el juego + la app en segundo plano" ≈ cualquiera que ya juegue ZZZ. La GPU no debe ser requisito propio.

---

## 7. iGPU (gráficos integrados) + DirectML

- **DirectML corre sobre cualquier GPU DX12, incluidas las integradas** (Intel HD/Iris/Arc, APU AMD). Compatibilidad universal para usuarios de ZZZ.
- **Pero el beneficio no está garantizado:**
  1. Recortes OCR chicos → el overhead de transferencia CPU↔GPU puede comerse la ganancia en una iGPU débil.
  2. La iGPU comparte RAM y presupuesto térmico; además compite con el juego, que ya la está usando.
- **Por eso no es "GPU sí o sí" sino auto-selección del más rápido por máquina** (ver §8).

> **Jerga:** *iGPU* = GPU integrada en el procesador, sin memoria propia (comparte la RAM). *DX12* = versión de DirectX que DirectML necesita; la soportan casi todas las iGPU de los últimos ~8 años.

---

## 8. Dónde va el benchmark CPU-vs-GPU

**NO en el instalador. Sí en el primer arranque de la app.**

Razones para NO ponerlo en el instalador (Inno Setup / NSIS solo copian archivos + accesos directos):
1. En ese momento la app no está corriendo; el benchmark necesita cargar modelos (~30 s) → un instalador colgado asusta y dispara antivirus.
2. El instalador suele correr como admin; la app corre como usuario normal → se mediría en un contexto distinto al de ejecución.
3. El hardware puede cambiar después de instalar (GPU nueva, drivers, copiar la carpeta a otra PC).

**Flujo recomendado:**

```
INSTALADOR (una vez, liviano)
  └─ elegir carpeta → copiar archivos → crear acceso directo → listo

APP · PRIMER ARRANQUE (una vez, cacheado)
  └─ ¿existe config de hardware guardada en user_config.toml?
       NO → mini-benchmark CPU vs DirectML (misma inferencia, medir cuál gana)
            → guardar ganador (ej. ocr_provider = "cpu" | "directml")
       SÍ → leerlo y arrancar directo
```

- Encaja con la config existente: `app/config/user_config.toml`.
- Se hace **una sola vez**; arranques siguientes leen el valor cacheado.
- **Bonus:** botón "Re-detectar hardware" en la pestaña Configuración para re-evaluar si cambia la GPU. El instalador no puede dar eso; la app sí.

---

## 9. Primer paso cuando se retome

**Medir antes de optimizar.** Activar el instrumental planeado en `QA/QA-06_Performance_y_UX.md`:
- Decorator `@measure_latency`.
- Tabla `metrics_latency` (hoy NO existe → requiere migración).

Sin baseline real por etapa (y por hardware), tanto la optimización como el auto-selector CPU/GPU son adivinanza. El instrumental de medición es lo que alimenta la auto-selección de §8 en cada máquina.

**Orden de mayor ROI al retomar:**
1. Instrumental de medición (QA-06) → baseline.
2. Mover números a template/NCC (§3.1) → mayor golpe de latencia sin tocar el presupuesto de RAM.
3. ONNX + DirectML (§3.2) para el texto real que quede, si la medición dice que sigue siendo el cuello.

**Efecto secundario deseable:** si los números pasan a NCC y el texto a ONNX, se podría **sacar PaddleOCR del paquete** (~9459 archivos en `_internal/`) → instalador mucho más liviano, relevante para distribución masiva.

---

## 10. Responsividad de los logs — frescura del estado capturado (≠ latencia de cómputo)

Todo lo anterior (§1–9) trata la latencia de **cómputo**: cuán rápido el OCR convierte un frame en datos. Esta sección trata otra cosa: **cuán actualizado está lo que el log reporta respecto a lo que realmente está pasando en pantalla**. Un OCR instantáneo puede seguir reportando un dato viejo si lo capturó en el momento equivocado. Más GPU no arregla esto.

### 10.1 El "caso 1" (QA 2026-07-15, upgrade S10 por fases)

En un upgrade por fases el log mostró `materiales cargados · nivel 4 → proyectado 6`, pero el resultado real fue `nivel 4→7`. **No es un error de lectura** — el `6` estaba bien leído *en ese instante*. Lo que pasó: entre el poll que fotografió la proyección (6) y el click en "Mejorar", el usuario cargó **un material más** → la proyección real subió a 7, pero el log ya había sacado la foto del 6.

**Causa:** el sistema mira la pantalla por *polling* periódico (cadencias 500–4000 ms según estado, §1). El log refleja el **último poll**, no el **instante del commit** (cuando apretás "Mejorar"). En pantallas de interacción rápida (cargar materiales, confirmar), el estado cambia más rápido que la cadencia → el reporte queda *stale* (viejo).

> **Jerga:** *stale* = un dato que era correcto cuando se leyó pero quedó desactualizado antes de usarse/reportarse. *Polling* = mirar la pantalla a intervalos fijos, en vez de reaccionar a cada cambio al instante.

### 10.2 Marco conceptual

El nivel **proyectado es una PREDICCIÓN de tu intención**, no un hecho. El hecho final lo da siempre la **S17 posterior** (inventario del PJ), que ya lee bien los rolls asentados — es la *verdad de tierra*. Entonces ninguna solución tiene que "adivinar mejor": tiene que o bien **fotografiar en el instante correcto**, o bien **reconciliar contra la verdad**.

### 10.3 Ideas (ordenadas por ROI)

| # | Idea | Qué hace | Costo / riesgo |
|---|------|----------|----------------|
| **A** ⭐ | **Re-parsear el ÚLTIMO frame S10 en la transición** | Cuando la pantalla pasa S10→S20/S17 (justo tras "Mejorar"), ese último frame S10 es la proyección **más fresca** = la que realmente commiteaste. Parsearlo ahí en vez de usar una foto anterior. | Bajo: un parse extra en un evento que ya ocurre. Ataca la causa raíz sin subir el polling. |
| **B** ⭐ | **Reconciliar / auto-corregir contra la S17** | Si el proyectado logueado difiere del resultado real, emitir `proyectado 6 → real 7` en vez de dejar el `6` colgado. La S17 es verdad de tierra. | Nulo: no cambia la captura, solo cómo se cierra el relato. Complementa A. |
| **C** | **Poll más rápido / disparado-por-cambio SOLO en el flujo de upgrade** | Subir cadencia (o re-parsear al cambiar la firma de la barra) mientras estás en S10/S20, donde el estado cambia rápido; lento en pantallas estáticas. | **Pelea con RNF-06** (CPU polling <3%, presión de RAM de PaddleOCR — §5). Acotarlo al flujo de upgrade, medir antes. |
| **D** | **Rotular el proyectado como tentativo** | `proyectado 6 (tentativo)` → un mismatch posterior no se lee como bug. | Cero costo. Cosmético/honestidad, no arregla lo técnico. |

**Recomendación: A + B.** A hace correcto el caso normal (foto en el instante del commit); B blinda el caso raro (cargaste material después) reconciliando contra la S17. C solo como refuerzo si la **medición** muestra huecos, porque toca el presupuesto de CPU. D es un agregado gratis.

### 10.4 Igual que el resto del doc: medir antes de tocar

Antes de subir cadencias (idea C) hay que instrumentar la latencia **poll→emisión** con el mismo `@measure_latency` / `metrics_latency` de §9 (QA-06). Sin baseline no se sabe si el hueco es de 200 ms (irrelevante) o de 2 s (molesto). Las ideas A y B **no** dependen de esa medición (son correctas por diseño), así que se pueden encarar antes; C sí.

> **Relación con §5:** la tensión es la misma — más frescura por fuerza bruta (polling rápido, idea C) = más inferencias = más CPU/RAM. Las ideas A/B consiguen frescura **sin** ese costo, capturando en el momento correcto en lugar de mirar más seguido. Ese es el patrón preferible.

---

*Documento de dirección futura. No iniciar este trabajo hasta cerrar la cobertura de extracción de todas las pantallas. Referencias cruzadas: `QA/QA-04_IA_Catalogadora.md` (hardware), `QA/QA-06_Performance_y_UX.md` (medición), `audit/mem_diag_20260613.md` (fuga de memoria RNF-06), `Dev_IA/2026-07-10_IMPL_Mejora_Disco_S10.md` (flujo S10 del caso 1).*
