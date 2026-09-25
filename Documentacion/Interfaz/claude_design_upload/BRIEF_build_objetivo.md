# Brief Claude Design — Build objetivo por PJ (modal de PJ)

> **Qué se pide:** que el usuario pueda **ver y declarar el build de sets** que quiere para cada
> PJ (**un 4pc + un 2pc**) dentro de la ficha del PJ, con la guía a la vista para elegir bien.
> Como la prioridad de buildeo, es un dato que pone él, no algo que el sistema lee de la pantalla.
>
> **Dónde vive:** el **modal de PJ** (1000×640, ya implementado, con el selector de prioridad de
> 262 px arriba a la derecha). Opcional: una marca o filtro en el **Roster** (§2.4).
>
> Sistema visual y tokens: `BRIEF_COMPLETO.md` (§1), `app/ui/tokens.py`. Diseño previo del mismo
> tipo (ajuste del usuario en la ficha): `mockups/design_v3_prioridad_de_buildeo/README.md`.
> Implementación real: `app/ui/pj_modal/modal.py`, `app/ui/roster/`.

---

## 1. Para qué sirve (el porqué)

El motor de discos sugiere equipar o mover discos entre PJs. Al revisar sus sugerencias, el usuario
encontró dos errores que salen de lo mismo — **el motor no sabía qué sets usa cada PJ**:

- le mandaba discos de **Armonía umbría** a Ye Shunguang ("no genera réplicas, ese set no le sirve");
- le mandaba discos de **Balada de la rama y la espada** a Nangong Yu ("ese 2pc es de daño crítico
  y ella es aturdidora con build de Anomalía").

Ahora hay una **base de conocimiento por PJ** sacada de las guías de Prydwen (52 PJs): qué 4pc le
sirven, en qué orden, y qué 2pc combina la guía con cada uno. Sobre eso, el usuario declara **su**
build objetivo.

**Reglas ya decididas por el usuario (el diseño las tiene que comunicar):**

| | |
|---|---|
| qué manda | el build que **declara el usuario**. |
| si no declaró | los sets que el PJ **tiene equipados**, si están en la guía para ese PJ ("razonables"); si no, el **primer** build de la guía. |
| efecto | un disco de un set **fuera** del build objetivo **no se le sugiere** a ese PJ, por buenos que sean sus stats. |
| naturaleza | ajuste del usuario: se cambia cuando quiera, no se pierde con una recaptura. |

**Cómo están hoy los 52** (datos reales, 2026-09-25): 35 llevan un build que la guía avala; 6
llevan un 4pc que la guía **no** lista (entre ellos Gatillo y Grace, dos de los PJs que el usuario
marcó con prioridad alta — puede ser a propósito); 2 llevan un 2pc que la guía no combina con su
4pc; 2 tienen el 4pc sin 2pc; 7 no tienen un 4pc completo. Esos 17 son el caso de uso principal.

---

## 2. Lo que hay que diseñar

### 2.1 La sección "Build objetivo" en el modal de PJ

Tiene que mostrar, de un vistazo:

1. **El build que usa el motor para este PJ** y **de dónde sale**, que es lo más importante de
   entender: *declarado por vos* · *el que tiene equipado* · *el primero de la guía (lo equipado no
   está en la guía)* · *el primero de la guía (no tiene un 4pc completo)*.
2. **Cómo está equipado hoy** (ej. "4× Balada de aguas blancas · 2× Tecno tetraodóntido"), y si
   coincide con el objetivo.
3. **La guía**: los 4pc recomendados en orden (algunas guías dan un % calculado —"100 %",
   "95,22 %"—, otras un puesto, y dos 4pc pueden compartir el puesto 1), y para el 4pc elegido
   sus 2pc: un renglón puede traer **dos sets equivalentes** ("Blues Libre / Jazz Caótico") y uno
   viene marcado **recomendado**.

Y permitir:

4. **Elegir el 4pc** (de la guía, o **cualquier otro set** — el usuario puede tener una razón que
   la guía no contempla; en ese caso se muestra, sin bloquear, que está fuera de la guía).
5. **Elegir el 2pc** (opcional; mismas reglas: los de la guía primero, cualquiera permitido).
6. **Volver al automático** (borrar la declaración).

Cada cambio se guarda al momento (como la prioridad): sin "Guardar" final. Los nombres de sets van
en **español** (el nombre del juego); los íconos de sets están en `Documentacion/Interfaz/`.

### 2.2 Espacio

El modal ya tiene portada, stats, discos equipados y el selector de prioridad. Proponer dónde entra
sin tapar lo que existe: una sección, una pestaña interna, o un panel desplegable. La lista de la
guía puede ser larga (Lycaon: 4 opciones de 4pc × 3–4 renglones de 2pc).

### 2.3 El caso "no hay guía"

Hoy los 52 tienen guía, pero un PJ nuevo (sale uno cada ~6 semanas) puede no tenerla todavía. El
estado vacío tiene que decir eso y seguir dejando declarar.

### 2.4 Roster (opcional, a evaluar)

Una forma de encontrar los PJs cuyo build **no está en la guía** o que **no tienen 4pc completo**,
para declararlos de una sentada. Colores ya ocupados (no reusar): ámbar `#F0AA3C` (faltan datos),
naranja (∞), violeta `#B06FF0` (atuendo), lima `#C4F03A` (prioridad alta), pizarra `#8C95A8`
(prioridad baja).

---

## 3. Estados que tiene que cubrir el entregable (con datos reales)

1. **Nangong Yu**, sin declarar, build equipado avalado por la guía: 4× Melodía de Faetón +
   2× Jazz Caótico. Guía: 4pc Melodía de Faetón (puesto 1) con 2pc *Blues Libre / Jazz Caótico*
   (recomendado), *Aria radiante / Metal Caótico*, *Voz Astral / Punk Hormonal*; 4pc Blues Libre
   (también puesto 1) con 2pc Melodía de Faetón (recomendado).
2. **Gatillo**, sin declarar, 4pc fuera de la guía: equipado 4× Armonía umbría + 2× Tecno Pícido;
   el motor usa el primero de la guía (Monarca del Pináculo + Disco Sacudestrellas). Es el estado
   que tiene que invitar a declarar.
3. **Gatillo** con build declarado = el que lleva (Armonía umbría + Tecno Pícido), marcado "fuera
   de la guía".
4. **Piper**, sin un 4pc completo (3× Blues Libre, 2× Jazz Oscilante, 1× Jazz Caótico): el motor
   usa Metal Colmilludo + Melodía de Faetón.
5. El selector abierto eligiendo el 2pc de un 4pc.

## 4. Fuera de este brief

- Los **stats** por PJ (principales y prioridad de substats): ya están en la base de conocimiento y
  los usa el motor; mostrarlos o ajustarlos es otro brief.
- Mostrar las **sugerencias** del motor: brief propio.

## 5. Data model sugerido (para el render)

```js
{
  agente_id: 26, nombre: "Nangong Yu",
  equipado: { "Melodía de Faetón": 4, "Jazz Caótico": 2 },
  declarado: null,                       // o { set_4p: "…", set_2p: "…" | null, actualizado: "…" }
  objetivo: { set_4p: "Melodía de Faetón", set_2p: "Jazz Caótico",
              origen: "equipado" },      // "declarado" | "equipado" | "guia_fuera" | "guia_sin_4pc"
  guia: {
    fuente: "Prydwen", url: "https://www.prydwen.gg/zenless/characters/nangong-yu",
    version: "Patch 2.7",
    opciones_4pc: [
      { set: "Melodía de Faetón", puesto: 1, puntaje: null,
        dos: [ { sets: ["Blues Libre", "Jazz Caótico"], recomendado: true },
               { sets: ["Aria radiante", "Metal Caótico"], recomendado: false },
               { sets: ["Voz Astral", "Punk Hormonal"], recomendado: false } ] },
      { set: "Blues Libre", puesto: 1, puntaje: null,
        dos: [ { sets: ["Melodía de Faetón"], recomendado: true } ] }
    ]
  }
}
```
