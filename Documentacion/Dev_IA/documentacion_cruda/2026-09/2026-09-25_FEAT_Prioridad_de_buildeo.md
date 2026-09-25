# FEAT · Prioridad de buildeo por PJ (2026-09-24/25)

> Fase A, etapa 1. Del hallazgo a la QA en vivo en un día. Decisiones de Daniel; diseño por Claude
> Design (brief `BRIEF_prioridad_de_buildeo.md`, handoff `mockups/design_v3_prioridad_de_buildeo/`).

## Por qué

Con los stats reales de los 52 PJs (pasada S18 del 2026-09-24), `sugerir_movimientos` mandaba
**32 de 108** movimientos a Piper, "que no uso casi nada", sacándole discos a PJs que Daniel sí usa.
El motor no tenía forma de saber a quién quiere mejorar.

## Lo que decidió Daniel

| | |
|---|---|
| niveles | alta / normal / baja; todos arrancan en normal |
| efecto | **bloquea**: nunca se sugiere sacarle un disco a un PJ para dárselo a otro de prioridad más baja |
| entre iguales | "el que lo tiene no pierde" (la regla del paso 7) |
| discos libres | primero a los de prioridad alta |
| dónde | **en la app**, no por chat, diseñado con Claude Design |

## Lo que se hizo (un commit por paso, cada uno con sabotajes en rojo y suite verde antes del push)

| paso | commit | qué |
|---|---|---|
| mig 42 | `cc4f2da` | `ajustes_usuario_prioridad` (normal = sin fila, B1); en `rebuild_account_db.DECLARADO` (la suite lo marcó) |
| repo | `ec543aa` | `PrioridadRepo`, `Agent.prioridad` |
| motor | `5db885d` | `recommender.nivel_prioridad / puede_recibir_de / _elegir` (única regla); optimizador; `resolver_conflictos` |
| roster | `3ae57c9` | marca (lima `#C4F03A` alta, pizarra `#8C95A8` baja), filtro, leyenda |
| editor | `11339f9` | `EditorPrioridades` (RNF-01, **un backup por sesión**); `AgentRepo` relee tras un cambio |
| edición | `973b0a4` | modo "Editar prioridades" del Roster |
| ficha | `712dc19` | selector en la ficha del PJ; la ventana lo conecta al Roster |

**Efecto verificado sin prioridades:** 180/180 sugerencias idénticas a las previas (misma decisión,
mismo delta). **Con Claret alta + Piper baja (en una copia):** Piper 32 → 0.

### Lo que encontraron las verificaciones en el camino

- **Qt lee `"#RRGGBB" + "AA"` como `#AARRGGBB`.** La primera captura de la marca de alta mostró una
  línea ROJA bajo la barra. Arreglado con `setAlpha`; el mismo error ya estaba en otras cinco marcas
  (esquina ámbar de Roster y Armas, halo del ∞, dos bordes QSS de Armas): los arregló una tarea
  aparte (`814818b`…`4546383`), con una guarda sobre `app/ui`.
- **El caché de `AgentRepo`**: el controller y la captura en vivo tienen instancias de toda la
  sesión; una prioridad editada no llegaba al motor hasta reiniciar, y "sugerencias recalculadas"
  habría mentido. `prioridades_cambiaron()` tras el commit.
- **Un sabotaje salió verde** (la botonera dejando tildado lo no guardado): el test miraba un
  atributo interno, no el segmento tildado. Corregido.
- **La etiqueta NUEVO** tomaba el alto entero del header (captura). Alto fijo.

## QA en vivo (2026-09-24, 23:54–23:59)

Daniel declaró las prioridades en la app (Roster en modo edición y ficha de PJ): "todo check".

- **48 clicks** sobre 40 PJs; el último valor de cada uno en el log (`[prioridad] <PJ> → <valor>`)
  es **idéntico** a la DB: **13 alta, 22 baja, 17 normal**. `integrity_check` ok, sin FKs rotas,
  cero errores o avisos en el log de la sesión.
- **3 backups `preprioridad`**, uno por sesión de edición (no uno por click).

## Las sugerencias con las prioridades reales

`audit/sugerencias/20260925_000654_781001_sugerencias_discos.{md,json}` contra
`20260924_111059_755557` (sin prioridades):

- 180 → **168** sugerencias; mover 108 → **96** (12 movimientos bloqueados).
- Los destinos pasan a ser los de alta: de 154 mover+equipar, **128 van a un PJ de alta** (Nangong
  Yu 23, Ye Shunguang 18, Aria 17 propuestas de mover); casi todas chocan entre sí por el mismo slot
  y quedan **en conflicto**: firmes, 28 (16 a alta, 5 a normal, 7 a baja).
- A baja sólo llegan discos que nadie de mayor prioridad quiere (6 libres) y un movimiento entre dos
  de baja (#305 Piper → Seth, permitido: misma prioridad).
- **El caso abierto del mínimo** (#61, +0,25 para Claret contra +3,97 para Corin): ahora queda en
  conflicto, porque ese slot de Claret lo toma el #340 (+1,55). Entre las 16 firmes a alta, **una
  sola** mejora menos de 1 (#248 → Yixuan, +0,85).

## Abierto

- ¿Un mínimo de mejora para que alta tenga preferencia? Con las prioridades reales el efecto es
  chico (1 caso firme < 1). Decide Daniel al revisar el reporte.
- Revisión de las sugerencias por Daniel (ciclo human-first: las que no comparta, casos nuevos).
