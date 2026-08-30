# El OCR se muda a un proceso desechable

> **2026-08-29.** Implementa lo que concluye
> [`2026-08-29_DIAG_La_fuga_es_del_OCR_12MB_por_inferencia.md`](./2026-08-29_DIAG_La_fuga_es_del_OCR_12MB_por_inferencia.md):
> la fuga no se puede arreglar dentro del proceso, así que el proceso pasa a ser reemplazable.

---

## 1. Dónde cae la frontera

En `OcrBackend` (`app/core/ocr_backend.py`), que ya era una interfaz de tres métodos. `OcrProxy` la
implementa reenviando a un hijo; ni el parser ni el monitor se enteran.

Que el corte cayera en una interfaz que ya existía es la razón de que esto sea un cambio chico:
**no hubo que tocar ni uno de los 90 archivos de test que construyen `PaddleBackend()` directo**. El
proxy es aditivo; sólo la app lo cablea.

## 2. Tres decisiones de transporte, y por qué

**Socket de loopback, no stdin/stdout.** El `.exe` se compila `--windowed` (`console=False`) y en
ese modo los handles estándar del hijo no son confiables — `sys.stdout` puede venir `None`. Un
protocolo binario sobre un stream que a veces no existe es una falla que **sólo aparece
empaquetada** (regla D1). El socket no depende de nada de eso. Se bindea a `127.0.0.1` explícito.

**Nada de `multiprocessing`.** No hay `freeze_support()` en ningún lado del proyecto, y sin él el
arranque por `spawn` bajo PyInstaller **vuelve a ejecutar la app entera en cada hijo**: el modo de
falla es una cascada de procesos, no un error prolijo. Un `subprocess` con centinela de argv lo
evita por construcción.

**`pickle` pelado, sin memoria compartida.** Medido antes de decidir: el payload más grande del
pipeline (1036×742×3, 2,3 MB) tarda **1,34 ms** ida y vuelta, contra 124-235 ms de una inferencia.
Menos del 1 %. La memoria compartida habría sido complejidad comprada con nada.

## 3. El pre-calentado

Reciclar cuesta 2,2 s de carga de modelos. Hacerlo en el momento habría cambiado un problema de
memoria por un tirón visible cada tantos discos. En vez de eso:

1. el worker actual **sigue atendiendo** mientras el reemplazo carga en paralelo,
2. el turno se pasa cuando el nuevo ya está caliente,
3. recién ahí se termina el viejo.

El hijo hace una inferencia de juguete antes de decir "listo": sin eso diría estar listo antes de
tiempo y los 2,2 s se los comería la primera llamada real — justo lo que el pre-calentado existe
para evitar.

### El techo, y el sobrepaso que hay que contar

El disparo no es instantáneo: entre que se cruza el techo y el reemplazo está listo siguen entrando
llamadas. **Medido con techo 1200: el worker llegaba a 1700-1975 MB**, o sea ~750 MB de sobrepaso.
Es acotado en el tiempo, no proporcional al techo.

Con el techo de producción en 2500 el pico queda en ~2500 + 750 de sobrepaso + ~650 del repuesto
calentando = **~3,9 GB** entre los dos procesos, y son ~5 reciclados en un censo completo.

⚠️ **El watchdog de RNF-06 ya no es la red de esto.** `monitor._ram_watchdog` lee el commit de **su
propio proceso**; con el OCR afuera, el proceso principal queda plano y el watchdog no vuelve a
dispararse. El control real del consumo pasó a ser `TECHO_RECICLADO_MB`.

## 4. Había DOS motores de Paddle, no uno

Es la mitad del problema y era fácil de no ver. Además del backend del controller, `detector.py`
tenía su propia global `_s26_verify_ocr` — y ésa corre sobre **toda** pantalla que matchee el
template de S17, o sea muchas más inferencias que el parser. Mudar sólo el primero habría dejado la
fuga casi intacta.

Se resolvió con un registro (`set_shared_ocr` / `get_shared_ocr`): una sola autoridad sobre cuál es
el OCR de esta app (regla B1). El detector le pregunta al registro y sólo se construye uno propio
cuando no hay app alrededor (tests, scripts sueltos).

De paso, la elección de backend (Paddle primero, Tesseract si no) se mudó de `ui/controller.py` a
`ocr_worker.construir_backend`: el hijo no puede importar la UI, y tenerla en los dos lados
garantizaba que se separaran.

## 5. Verificación

**Transparencia** — el proxy da resultados **idénticos** al backend directo sobre 7 fixtures (set,
slot, main, nivel y los cuatro substats con rolls). 7/7. Si esto no diera igual, lo demás no
importaría.

**La medición que motivó todo**, repetida con el proxy y techo bajo a propósito para ejercer el
reciclado:

```
                          antes        ahora
commit del PADRE          +4401 MB     +0 MB      (150 parseos de contenido variado)
worker                    —            1200-1950 MB, reciclado 6 veces
```

**17 tests nuevos.** Los de política usan workers de mentira y corren en menos de un segundo; uno
levanta un worker **de verdad** —subprocess, socket y Paddle— porque si no, el camino de arranque
no se ejercería nunca en dev (regla D2). También se fija el comando del hijo en las dos variantes,
empaquetado y desde fuente: equivocarse ahí es el bug que sólo se ve empaquetado.

El test que sostiene el diseño es `test_al_pasarse_del_techo_precalienta_y_RECIEN_DESPUES_releva`.
Saboteado —terminando al viejo apenas cruza el techo, que es el reciclado ingenuo— falla **ése y
sólo ése**.

Suite completa: **2468 passed**, 17 skipped, 1 xfailed. Ruff 598 contra un baseline de 591: los 7
de más son `BLE001`/`S110` en caminos de limpieza, el mismo patrón que el resto del proyecto
(`detector.py` solo tiene 36). sha256 de la DB de dominio idéntico antes y después.

## 6. Lo que quedó SIN probar

**El camino empaquetado.** Smart App Control está activado en la máquina
(`VerifiedAndReputablePolicyState = 1`) y bloquea el `.exe` recién compilado, así que todo lo de
arriba se verificó **desde fuente**. El centinela de argv, el `sys.frozen` del comando del hijo y el
comportamiento de los handles en modo `--windowed` están cubiertos por tests unitarios y por
razonamiento, no por ejecución.

Es exactamente el tipo de cosa que anda en dev y muere empaquetada. **No se da por cerrado hasta
ejercerlo**, y para eso hace falta resolver antes lo del bloqueo del `.exe` (firmarlo).

---

## Lo que me llevo

**Una interfaz angosta que ya existía convirtió un cambio grande en uno chico.** El OCR se mudó de
proceso sin tocar el parser, el monitor ni 90 archivos de test, porque `OcrBackend` tenía tres
métodos y nada más. El costo de haberla definido bien en su momento se cobró hoy.

**Y el arreglo puede mover el problema fuera de la vista de su propia red.** El watchdog seguía ahí,
seguía andando, y dejó de servir para esto en el mismo commit que arregló la fuga — no porque se
rompiera, sino porque mide el proceso equivocado. Un control que deja de aplicar es más peligroso
que uno que falla, porque no avisa.

---

**Archivos:** `app/core/ocr_ipc.py` · `app/core/ocr_worker.py` · `app/core/ocr_service.py` (nuevos) ·
`app/main.py` · `app/ui/controller.py` · `app/core/detector.py` ·
`app/tests/unit/{test_ocr_ipc,test_ocr_service}.py` (nuevos) ·
`app/tests/unit/test_controller_graceful.py`.
