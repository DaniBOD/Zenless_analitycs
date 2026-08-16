# Un evento, una línea — y el instrumental de latencia · 2026-08-15

> Dos trabajos de **observabilidad** hechos el mismo día y que se necesitan mutuamente: primero se
> construyó con qué medir, después se limpió el canal por el que se mide.
>
> Commits: `b526aba` (instrumental QA-06) · el de reducción de logs cierra este doc.

---

## Parte 1 · El instrumental de latencia (QA-06)

*"Sin números registrados de p50/p99, «está rápido» es opinión, y las opiniones no cumplen
RNF-06."* Esto no optimiza nada: es lo que permite decidir **qué** optimizar sin adivinar.

### La decisión que más importa: DB APARTE

QA-06 §2.2 proponía una tabla `metrics_latency` dentro de `danibod_zzz_v2.db`. Se hizo en un
archivo separado (`metrics.db`). Tres razones, y la primera decidió:

1. **La prueba de que un QA en readonly no escribió nada es el sha256 de la DB de dominio** — se
   usó dos veces ese mismo día, y es lo que dio confianza para tocar la ruta que alimenta
   `sync_equip`. Si la telemetría escribiera ahí, esa propiedad desaparece.
2. En readonly no se podría medir, y varios QA corren así — justo los que más interesa medir.
3. RNF-01 protege la DB de dominio con backup + transacción + PRAGMA. Escrituras append-only de
   alta frecuencia no encajan, y un flush que salga mal se lleva datos del dominio.

**Efecto colateral: no hizo falta migración.** El esquema vive en su archivo y se crea solo. Hay un
test que compara el sha256 de la DB de dominio antes/después de un flush; si cae, se perdió la
propiedad que hace verificable cualquier QA en readonly.

### Dos latencias que no son la misma

| | qué mide | métricas |
|---|---|---|
| **cómputo** (doc §1-9) | cuánto tarda cada etapa | `capturer` · `detector` · `ocr_text` |
| **frescura** (doc §10) | cuánto tarda en **enterarse** | `frescura_estado_a_log` · `dispatch:SXX` |

La frescura salió de una observación de Daniel: *ni el usuario ni el sistema saben cuándo cambió
realmente la pantalla*, así que propuso cronometrar los intervalos entre logs, pasando de pantalla
apenas salta uno. El método funciona y da una cota superior — pero mezcla su tiempo de reacción con
el del sistema.

**Lo que lo destraba:** `classify` corre en **cada tick rápido (~109 ms)**, no a la cadencia. El
primer frame en que se ve el estado nuevo *es* el cambio de pantalla, con ese error acotado. Eso el
sistema sí lo sabe, sin que nadie cronometre.

**El límite honesto:** el CONTENIDO (disco, engine) no se mira en el loop rápido sino dentro del
handler, **a la cadencia (500-4000 ms)**. Para un cambio de contenido sin cambio de pantalla, el
término dominante es la cadencia, **no el cómputo**. Precisarlo más pediría una firma de contenido
en el loop caliente — la tensión de §5 — y no se hizo. Por eso además `dispatch:SXX`, etiquetado por
pantalla, cuyo techo natural es la cadencia de ese estado: comparar los dos separa *"tarda en
enterarse"* de *"tarda en procesar"*.

### Una trampa encontrada de paso

**El percentil de QA-06 §2.2 estaba mal.** `k = int(len(s) * p / 100)` está corrido en uno: con 100
muestras da `k=99` para p99 ⇒ **p99 salía siempre igual al máximo**. Un p99 que es el peor caso no
sirve para lo único que se le pide, separar la cola de lo típico. Corregido a rango-más-cercano; el
doc quedó actualizado.

---

## Parte 2 · Un evento, una línea

### La medición cambió el diagnóstico

El conteo inicial dio **46 % de líneas "repetidas"**, lo que apuntaba a un dedup roto. Pero los
timestamps decían otra cosa: **12 a 47 segundos entre líneas idénticas**.

No eran repeticiones. Era **una línea por disco**, y salían iguales porque **el mensaje no dice de
qué disco habla**.

> El log no repetía: era **indistinguible**. No se podían separar seis eventos reales de un evento
> logueado seis veces — y eso es exactamente lo que impide usarlo como señal.

Anatomía real de un disco: **4 a 7 líneas**, mezclando dos audiencias en un solo nivel.

| línea | para quién |
|---|---|
| `Disco detectado: set=… slot=… main=… nivel=…` | el usuario — **el evento** |
| `[readonly] S17 NO persiste — …` | el usuario — la decisión |
| `[S17] asignado a 'X' (latch; sim=…)` | mitad y mitad |
| `[badge] ancla decía 'X' pero el badge dice 'Y'` | **depuración** |
| `[badge] no rescato la cosecha del detalle para 'X'` | **depuración** |
| `S17: PJ no confiable para 'SET' slot=N` | **depuración** |

El problema estructural: **todo en INFO, sin separar QUÉ pasó de POR QUÉ el sistema decidió eso.**

### La regla

**En INFO va el evento. El razonamiento va a DEBUG** (`DANIBOD_LOG_DEBUG=1`, flag `-LogDebug`).

Y la línea del evento pasa a ser **autocontenida**, con la tenencia adentro:

```
Disco detectado: set=Jazz caótico slot=1 main=HP nivel=15 dueño=Corin conf=0.98 (agg 1c)
```

Antes eso eran dos líneas que había que aparear por cercanía en el archivo — imposible con varios
discos seguidos cuyos mensajes no se distinguen.

**No se borró ningún mensaje.** Bajarlos de nivel conserva el diagnóstico para cuando haga falta,
que es lo que evita arrepentirse de haber "limpiado" el log.

### Resultado, medido sobre los 62 discos del QA

| | antes | después |
|---|---|---|
| líneas **por disco** | 2.5 | **1.5** |
| total por-disco | 156 | 92 |

La que queda además del evento es `[readonly]/persiste`, que dice si se escribió — información
genuinamente distinta. Sin fusionar módulos, 1.5 es cerca del piso.

### Por qué importaba

1. **El log como señal de tiempo.** El plan para medir frescura a mano es pasar de pantalla apenas
   salta el log; con siete líneas por disco y varias indistinguibles, no hay señal que seguir.
2. **El censo.** ~300 discos × 4-7 líneas = 1200-2100 líneas con lo que importa enterrado.

---

## Lecciones

1. **Medir antes de nombrar el problema.** "Reducir logs" habría llevado a dedupear más — y el
   dedup no estaba roto. Los timestamps dijeron que eran eventos distintos sin discriminador.
2. **Un porcentaje agregado engaña dos veces.** El 46 % de "repetidas" era falso; y mi primer
   número de mejora ("5.0 → 3.4 líneas por disco") también, porque dividía TODAS las líneas por
   discos cuando muchas son por sesión. El número real es 2.5 → 1.5.
3. **Bajar de nivel no es borrar.** Es la diferencia entre limpiar y perder.
4. **Un test que falla porque el mundo cambió no es un test frágil.**
   `test_no_se_rescata_si_el_boton_no_confirma` capturaba en INFO; el mensaje se movió a DEBUG.
   Seguía protegiendo algo cierto —que la regla no dispare en silencio— así que se ajustó el nivel
   de captura, no la afirmación.
5. **Un test que afirma sobre un literal que uno mismo escribió no prueba nada.** El primer intento
   del test de la línea de evento comparaba contra un string hardcodeado en el propio test; se
   reemplazó por uno que invoca el emisor real, con los tres casos (con dueño, libre, y **dueño sin
   resolver** — que no puede salir como `None` ni omitirse: "no sé" es información).
