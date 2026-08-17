# QA en vivo del censo de roster — y el problema de los grises · 2026-08-17

> Primera pasada real del censo. **Funcionó**: 49/51 en ~18 minutos, cero huérfanos.
> Pero el intento de censar los personajes **no obtenidos** destapó dos defectos, uno de ellos
> fuera del censo. Este doc los deja escritos y define el camino que Daniel propuso.
>
> Continúa [2026-08-16_IMPL_Censo_Fase0_y_Roster.md](./2026-08-16_IMPL_Censo_Fase0_y_Roster.md).

---

## 1. La pasada salió bien

```
[censo] pasada cerrada — 49/51 vistos · 2 dudosos · 0 huérfanos · 0 no reconocidos
```

51 PJs recorridos en ~18 min (~6-10 s por PJ, human-bound como se esperaba). Los 2 dudosos
—Miyabi 0.79 y Ellen 0.71— cayeron por confianza de OCR bajo el umbral de 0.80, que es
exactamente lo que ese estado existe para decir: *se vio, pero repetilo*.

Reporte en `audit/censos/20260817_141306_*`. Cobertura 96 %.

Confirmado también: **multi-sesión funciona en vivo.** Se reinició la app a mitad de camino (para
aplicar un fix) y la corrida retomó en 5/51 sin perder nada.

### El conteo real del roster: 55 personajes, no 51

Daniel corrigió el número y la DB lo confirma exacto:

```
51 filas en agents
 −2 variantes de ATUENDO (Billy Estelar = Billy · N.º 0: Anby = Anby)
 = 49 personajes distintos que posee
 +6 que no posee (Norma, Promeia, Banyue, Yidhari, Hugo, Lichter)
 = 55
```

Vale registrarlo porque `agents` cuenta **filas**, no personajes, y las dos variantes son el mismo
límite conocido que produce los 4 imanes de "Billy Estelar" en la librería de badges.

---

## 2. Dos arreglos que salieron del QA

### El progreso iba al archivo y el usuario miraba el panel

El censo contaba bien y Daniel no veía nada: las líneas iban a `app.log` vía `log.info` y él
estaba mirando el panel de la app. En un recorrido de 51 selecciones eso lo vuelve inservible.

Arreglado sumando `self._diag(...)` junto al log. El panel **es** el log visible, así que no
contradice la decisión de "solo log": lo que se descartó fue el toast (interrumpe) y el panel de
progreso dedicado (fase 5).

### Cerrar una pasada parcial declaraba huérfanos falsos

Riesgo que estaba declarado y se materializó al toque: después de cerrar la pasada completa,
volver al menú a revisar unos pocos PJs **abre una corrida nueva**. Cerrarla ahí habría declarado
huérfanos a los 49 por los que no se volvió a pasar.

`Monitor._confirmar_cierre_parcial`: con pendientes, el primer F8 **advierte y nombra** a quiénes
declararía huérfanos; el segundo dentro de 15 s confirma. Sin pendientes cierra de una — cero
fricción en el caso normal. La ventana caduca a propósito: un F8 diez minutos después no es una
confirmación consciente.

### El catálogo ahora es la unión de las dos carpetas de arte

Daniel agregó el splash de Norma esperando que el censo se enterara, y no pasó: el catálogo salía
solo de `app/resources/avatar_refs/*.png`, mientras que el paso 7 del onboarding escribe en
`Documentacion/Interfaz/splash_arts/*.webp`. Ahora `roster_y_catalogo()` une las dos.

⚠️ **Inconsistencia de assets encontrada de paso**, sin resolver:

```
avatar_refs/Lichter.png
splash_arts/Lichter-ico.webp
splash_arts/Lighter-extend.webp   ← la distinta
```

Dos grafías del mismo personaje. **No se resuelve por mayoría ni de memoria**: el nombre correcto
es el que muestra la pantalla, y hace falta una lectura del OCR sobre ese PJ para decidir.

---

## 3. ⚠️ Defecto ABIERTO y grave: un gris se hace pasar por un PJ propio

Medido con `_match_agent_scored` sobre los seis nombres:

| leído | matchea a | sim | ¿supera 0.55? |
|---|---|---|---|
| **Norma** | Nekomata | 0.615 | **sí** |
| **Promeia** | Pyrois | 0.615 | **sí** |
| **Banyue** | Anby | 0.600 | **sí** |
| **Lichter** | Alice | 0.667 | **sí** |
| Yidhari | (Aria) | 0.545 | no |
| Hugo | (Zhao) | 0.500 | no |

**Cuatro de seis.** Y se vio en vivo, en el mismo frame:

```
[censo] Norma — no lo poseés (gris del menú), no se cuenta
[S15]   Menú de personajes reconocido — PJ=Nekomata · rol=Ataque · elemento=Físico
```

El censo salió bien porque `RosterCensus._resolver_clave` da **precedencia al match exacto contra
el catálogo** sobre el difuso. Pero esa guarda vive **dentro del censo**, y el resto del sistema
no la tiene:

- `read_menu_agent` devuelve `nombre='Nekomata'`;
- `_seed_identity_from_menu` **siembra el latch con el PJ equivocado**.

**Esto no es un problema del censo, es del reconocimiento de identidad.** Pararse sobre un
personaje no obtenido le dice al sistema que estás en otro PJ, y ese latch después atribuye
discos. Es el mismo modo de falla que el latch sostenido (commit `a08b4cc`), por otra puerta.

**Arreglo propuesto:** subir la precedencia del catálogo al parser — que `_match_agent_scored`
conozca la lista de personajes que existen y se **abstenga** cuando el texto coincide exactamente
con uno que no está en el roster. Hoy la lista se arma en `census_store.roster_y_catalogo()` y
habría que moverla a un lugar que el parser pueda consultar sin importar el censo.

---

## 4. ⚠️ Defecto ABIERTO: solo 1 de 6 grises dejó observación

Entre `14:28:39` y `14:30:13` hay **94 segundos sin una sola línea**, y en ese rato Daniel recorrió
los seis. Solo Norma quedó registrada.

Hipótesis no verificada, en orden de plausibilidad:

1. **La barra de nombre no cambia lo suficiente** para un personaje bloqueado, así que el gate de
   firma (`_MENU_SIG_MAX = 6.0`) suprime el OCR. Es el riesgo declarado del gate, materializado.
2. La barra directamente **no muestra el nombre** de un no obtenido, y lo que se leyó fue residuo
   de la selección anterior.

**Falta la evidencia decisiva: una captura del menú con un personaje NO OBTENIDO seleccionado.**
Todas las capturas que hay son de PJs propios. Sin eso no se puede decidir entre las dos hipótesis
y cualquier arreglo sería a ciegas.

---

## 5. El camino que decidió Daniel: censo manual del roster

> *"podríamos implementar de golpe el censo vía manual por el usuario… lo primario será el roster
> que ingrese el usuario, el descriptor + OCR será un complemento"*

**Es la decisión correcta, y los defectos de §3 y §4 son la razón.** El sistema no puede enumerar
por observación lo que la pantalla no expone de forma fiable — y encima el intento de leerlo
envenena la identidad. El usuario, en cambio, sabe perfectamente qué personajes tiene.

Reencuadre que esto implica, y conviene tenerlo explícito:

| | fuente | por qué |
|---|---|---|
| **Roster** | **declaración del usuario** | son ~55 casillas que sabe de memoria; la pantalla no expone bien a los no obtenidos |
| **Discos** (367) | observación | son demasiados y con datos que el usuario no puede transcribir sin error |
| **Armas** | observación | ídem |

No contradice la tesis del censo. La tesis es *"la transcripción manual sin verificar diverge"*, y
el remedio es **verificar**, no necesariamente **observar**: una declaración explícita del usuario,
hecha una vez y contrastada después contra lo que el sistema ve, es más confiable que una
transcripción vieja que nadie volvió a mirar.

### Qué habilita

- El **denominador completo** (los 55), que la observación nunca puede dar: por más que recorra, el
  sistema no sabe cuántos hay en total.
- Los grises dejan de ser un problema de visión: si el usuario declaró que no tiene a Norma, un
  match difuso a Nekomata se puede **vetar** con esa lista.
- Se puede sembrar la tabla `agents` de un PJ nuevo sin esperar a cruzárselo.

### Diseño pendiente (para la próxima sesión)

- **Pantalla temporal aparte**, a pulir después; Daniel quiere pasarla por Claude Design.
- Selección múltiple sobre el catálogo de personajes conocidos (unión de las dos carpetas de arte,
  hoy 58 nombres — ojo con el duplicado Lichter/Lighter de §2).
- **Dónde se guarda:** lo declarado es dato de dominio (define el roster), así que va a
  `danibod_zzz_v2.db` con ceremonia RNF-01 — no a `census.db`, que es evidencia observacional.
- **Qué pasa con un PJ declarado que no está en `agents`:** dispara el onboarding
  (`Onboarding_Nuevo_PJ.md`), no lo inventa.
- **Qué pasa con un PJ en `agents` que el usuario no declara:** es la señal más fuerte que puede
  dar el sistema de una fila espuria — pero sigue sin borrarse solo (RNF-02).
- El censo por observación queda como **verificación** de lo declarado, no como su fuente.

---

## 6. ⚠️ Encontrado al ir a commitear: un test escribió en la DB de dominio

`db/danibod_zzz_v2.db` aparecía modificada y el diff de git no decía nada (mismo tamaño, binario).
Comparando el **contenido** (`con.iterdump()` de HEAD contra el working tree), la diferencia eran
dos filas:

```
38  Jane   | … | no_visto_en_censo_2026-08-17
44  Ellen  | … | no_visto_en_censo_2026-08-17
```

**Marcas falsas.** Jane está en los 49 vistos de la corrida buena de §1.

Además había **dos reportes falsos** en `audit/censos/`, con la firma delatora de un fixture:

```
"ts_apertura": 0.0,                      ← convención de los tests
"vistos": ["Nangong Yu"], "huerfanos": ["Jane", "Ellen"],  ← el roster de 3 de test_monitor_censo_s15
```

Origen: una versión temprana de esos tests, antes de que les agregara `DANIBOD_AUDIT_DIR` y
`DANIBOD_READONLY`, corrió contra los archivos reales. **El código ya estaba arreglado; el residuo
no.** Nada de esto se commiteó — el estado bueno se recupera con `git checkout` — pero de no
haberlo mirado, dos PJs de la cuenta hubieran quedado con una nota que dice lo contrario de lo que
pasó.

### Las dos guardas que se agregaron (`app/tests/conftest.py`)

1. **`_isolate_side_outputs`** (autouse) redirige `DANIBOD_AUDIT_DIR`, `DANIBOD_CENSUS_DB` y
   `DANIBOD_METRICS_DB` a `tmp_path`. Es el mismo patrón de `_isolate_avatar_library`, que ya
   existía por un incidente igual con la librería de badges.
   Cuidado con un detalle que casi meto mal: **`DANIBOD_METRICS` es el interruptor on/off**; el path
   es `DANIBOD_METRICS_DB`. Setear el primero con un path prendía las métricas en toda la suite.
2. **`_domain_db_untouched`** (session, autouse) hashea `danibod_zzz_v2.db` antes y después de la
   suite entera. La DB de dominio **no se puede redirigir**: varios tests la leen de verdad
   (cobertura de assets, roster). Lo que sí se puede es verificar el efecto.

El principio: **aislar el efecto de costado por defecto y que el test que lo necesita opte por
salir.** Al revés —cada test acordándose de redirigir— falla en silencio.

---

## 7. Lecciones

1. **Un log que el usuario no ve no existe.** El censo funcionaba perfecto y la sesión parecía
   rota, porque las líneas estaban en un archivo y él miraba la app.
2. **El riesgo declarado se materializó a los diez minutos.** "Cerrar una pasada parcial declara
   huérfanos falsos" estaba escrito como riesgo teórico; pasó en la primera sesión de uso real.
   Escribir el riesgo no lo mitiga.
3. **Una guarda que vive dentro de un módulo no protege a los demás.** La precedencia del catálogo
   salvó al censo y dejó el latch envenenado: la misma evidencia, aplicada en un solo lugar.
4. **Cuando la observación no alcanza, el usuario es una fuente legítima.** La doctrina del proyecto
   es "no inventar", no "no preguntar". Declarar 55 casillas no es transcribir 367 discos.
5. **Arreglar el test no limpia lo que el test ya ensució.** El código estaba bien y los archivos
   seguían mal. Después de arreglar un test que tenía efectos de costado, hay que ir a mirar qué
   dejó — y el diff binario de git no alcanza para verlo.
