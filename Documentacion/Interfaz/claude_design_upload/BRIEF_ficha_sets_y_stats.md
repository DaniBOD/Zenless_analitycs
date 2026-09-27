# Brief Claude Design — La ficha del PJ: sets y stats (modal de PJ)

> **Qué se pide:** una sección del **modal de PJ** donde el usuario elige, para cada PJ, **sus sets
> (4pc + 2pc), los principales de los discos 4-6, la prioridad de los secundarios y sus stats
> fijos**, con la guía a la vista y avisos cuando algo no tiene sentido.
> **Reemplaza a `BRIEF_build_objetivo.md`**, que era sólo la parte de sets.
>
> **Dónde vive:** el modal de PJ (1000×640, ya implementado, con el selector de prioridad de 262 px
> arriba a la derecha). Sistema visual y tokens: `BRIEF_COMPLETO.md` (§1), `app/ui/tokens.py`.
> Diseño previo del mismo tipo (un ajuste del usuario en la ficha):
> `mockups/design_v3_prioridad_de_buildeo/README.md`. Implementación real: `app/ui/pj_modal/`.
> Datos: `app/core/ficha_pj.py::foto()` (ya existe y está probado).

---

## 1. Para qué sirve (el porqué)

El motor sugiere qué disco equipar en cada PJ. Decide con lo que dice la **guía** del PJ (Prydwen:
qué sets, qué principales, qué secundarios valen más) y con lo que el usuario **corrige** encima.

La regla del usuario, textual: *"el usuario no es que toque el motor, sino que al seleccionar un set
y los stats deseados influyen en los pesos de forma interna"*. Por eso:

- **nunca se muestran pesos ni números del motor**: el usuario elige NIVELES y SETS;
- cada elección se guarda al momento (como la prioridad): **sin botón "Guardar"**;
- todo se puede **volver a la guía** (por dato y entero);
- el sistema **avisa pero nunca bloquea**: el usuario puede elegir DEF% para Ellen; la ficha le
  dice que no le beneficia y qué recomienda la guía.

## 2. Lo que hay que diseñar

### 2.1 Sets (lo que manda primero)

- El build que usa el motor (4pc + 2pc) y **de dónde sale**: *declarado por vos* · *el que tiene
  equipado* · *el primero de la guía (lo equipado no está en la guía)* · *el primero de la guía (no
  tiene un 4pc completo)*.
- La guía: los 4pc en orden y, para el 4pc elegido, sus 2pc en renglones (un renglón puede traer
  **dos sets equivalentes**, uno viene marcado recomendado). El orden importa: si al PJ le falta un
  stat fijo, el motor puede proponer cambiar el 2pc **por el siguiente de la lista** (de a dos
  discos, nunca tocando el 4pc).
- Elegir 4pc y 2pc de la guía **o cualquier otro set** (se marca "fuera de la guía", sin bloquear).

### 2.2 Principales de los discos 4, 5 y 6

Por slot, los que pide la guía y los que eligió el usuario (varios por slot). Elegir uno fuera de la
guía muestra el aviso.

### 2.3 Prioridad de los secundarios — cinco niveles

Los 10 secundarios (PV, PV%, ATK, ATK%, DEF, DEF%, Prob. Crítica, Daño Crítico, Perforación, Maestría
de Anomalía) repartidos en **Imprescindible / Muy bueno / Bueno / Sirve / No sirve**. Varios pueden
compartir nivel (la guía dice "Prob. Crítica = Daño Crítico"). Tiene que verse cuál nivel viene de la
guía y cuál lo movió el usuario. Interacción sugerida: fichas arrastrables entre filas, o un selector
por ficha; que se entienda en 2 segundos.

### 2.4 Stats fijos

El valor que un stat tiene que alcanzar para que una pasiva o el 4pc rinda completo. Tres orígenes
que se tienen que distinguir: **del kit** (la pasiva: Gatillo 90 % de Prob. Crítica), **del set**
(Monarca del Pináculo: Prob. Crítica ≥ 50) y **tuyo**. Con el valor actual del PJ (leído del juego) y
cuánto falta. Mientras falte, **el motor lo busca** (pesa como Imprescindible): tiene que notarse. El
usuario puede cambiar el objetivo, agregar uno o desactivar uno de la guía.

### 2.5 Avisos

Dos severidades, ya calculadas por el motor (texto listo):

- **⚠️ No te beneficia** — algo que el usuario eligió y la guía o el set contradicen.
- **ℹ️ Informativo** — sin tono de error.

Tienen que estar cerca de lo que avisan (el de DEF% junto a los secundarios), y un resumen arriba.

### 2.6 Espacio

El modal ya tiene portada, stats, discos equipados y el selector de prioridad. Proponer cómo entra
todo esto: pestaña interna "Build", panel desplegable, o una vista aparte desde el modal.

## 3. Estados con datos reales (2026-09-27)

1. **Ellen**, el usuario puso **DEF% en Imprescindible**. Guía: Daño Crítico (1), Prob. Crítica (2),
   ATK% (3), Perforación y ATK (4). Principales: slot 4 Daño Crítico · slot 5 Bono Daño Hielo o Tasa
   de Perforación · slot 6 ATK%. Build equipado: 4× Tecno tetraodóntido + 2× Balada de la rama y la
   espada. Aviso ⚠️: *"DEF% no le suma nada a Ellen. La guía prioriza Daño Crítico y Prob. Crítica."*
2. **Gatillo**, build **declarado fuera de la guía**: Armonía umbría + Tecno Pícido (la guía lista
   Monarca, Voz Astral, Punk Primitivo, Disco Sacudestrellas). Fijo del kit: Prob. Crítica 90, tiene
   75,4. Avisos ℹ️: *"El 4pc de Armonía umbría está fuera de la guía de Gatillo: es un build tuyo."* ·
   *"Prob. Crítica: 75,4 de 90 (faltan 14,6). El motor lo busca."*
3. **Grace**, build declarado Blues Libre + Jazz Caótico (la guía: Metal Eléctrico, Jazz Caótico). Sólo
   el ℹ️ de fuera de la guía. Guía de secundarios orientada a Anomalía (Maestría de Anomalía primero).
4. **Anby**, 4× Monarca del Pináculo + 2× Disco Sacudestrellas (equipado). Fijo **del set**: Prob.
   Crítica ≥ 50, tiene **48,2**. Avisos ℹ️: *"El 4pc de Monarca del Pináculo pide Prob. Crítica ≥ 50:
   queda como stat fijo."* · *"Prob. Crítica: 48,2 de 50 (faltan 1,8). El motor lo busca."* Su lista de
   2pc para Monarca: 1 Disco Sacudestrellas (recomendado), 2 Jazz Oscilante.
5. Un PJ **nuevo sin guía**: sin niveles ni sets de guía; se puede declarar todo igual.
6. El selector de 2pc abierto para un 4pc con renglones de dos sets (Ju Fufu con Monarca: 1 Disco
   Sacudestrellas · 2 Tecno Pícido · 3 Voz Astral / Punk Hormonal · 4 Jazz Oscilante).

## 4. Data model (lo que entrega `foto()`)

```js
{
  agente_id: 44, nombre: "Ellen",
  set_4p: "Tecno tetraodóntido", set_2p: "Balada de la rama y la espada",
  origen_build: "equipado",          // "declarado" | "equipado" | "guia_fuera" | "guia_sin_4pc"
  niveles: { "Daño Crítico": 1, "Prob. Crítica": 2, "ATK%": 3, "Perforación": 4, "ATK": 4,
             "DEF%": 1 /* del usuario */, "HP": 0, "HP%": 0, "DEF": 0, "Maestría de Anomalía": 0 },
  eleccion: { niveles: { "DEF%": 1 }, principales: {}, set_4p: null, set_2p: null },
  guia: {
    niveles: { "Daño Crítico": 1, "Prob. Crítica": 2, "ATK%": 3, "Perforación": 4, "ATK": 4 },
    principales: { 4: ["Daño Crítico"], 5: ["Bono Daño Hielo", "Tasa de Perforación"], 6: ["ATK%"] },
    sets_4pc: ["Tecno tetraodóntido", "Tecno Pícido", "Armonía umbría"],
    dos_por_4pc: { "Tecno tetraodóntido": ["…"] }
  },
  principales: { 4: ["Daño Crítico"], 5: ["Bono Daño Hielo", "Tasa de Perforación"], 6: ["ATK%"] },
  fijos: { },                        // stat → objetivo (el valor actual viene de las stats del PJ)
  avisos: [ { severidad: "aviso", tipo: "substat_no_te_beneficia",
              texto: "DEF% no le suma nada a Ellen. La guía prioriza Daño Crítico y Prob. Crítica." } ]
}
```

Colores ya ocupados en el Roster (no reusar para otra cosa): ámbar `#F0AA3C` (faltan datos), naranja
(∞), violeta `#B06FF0` (atuendo), lima `#C4F03A` (prioridad alta), pizarra `#8C95A8` (prioridad baja).

## 5. Fuera de este brief

- Mostrar las **sugerencias** del motor (van a la pantalla Discos, brief propio).
- Elegir la **variante** de la guía (5 PJs tienen más de una build).
- Recordar avisos descartados.
