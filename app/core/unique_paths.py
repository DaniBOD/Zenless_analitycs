"""Reserva de nombres de archivo que no pisan a nadie. Primitiva, sin política.

Es la **única autoridad** del proyecto sobre *cómo se consigue un nombre libre*. Llegó a existir
porque el 2026-08-19 la misma decisión se escribió dos veces, en dos worktrees que no se veían —
`audit_paths.reservar_rutas` para las bitácoras y `db.connection.respaldar_db` para los respaldos
RNF-01—, con el mismo `O_EXCL` y el mismo tope de 1000. Casi calcadas.

Pero **no eran duplicados**: divergían en qué hacer si algo falla a mitad, y las dos tenían razón.

    audit/    deja el archivo vacío   → ruido visible, y nadie restaura de un archivo de audit/
    backups   borra la reserva        → un `.db` vacío PARECE un respaldo del que se puede volver

Una primitiva con dos políticas, entonces. Acá vive la primitiva; la política se queda en cada
llamador, que es quien sabe qué significa su archivo.

## Por qué el reloj no sirve como discriminador

Los nombres del proyecto llevan un sello de tiempo, y está bien que lo lleven: sirve para que un
humano ubique la corrida en su día. Lo que **no** puede colgar de él es la unicidad.

Dos escrituras seguidas caen en el mismo sello salvo que el reloj de pared alcance a avanzar entre
una y otra — y cuánto tarda en avanzar no lo decide esta app. En Windows `datetime.now()` lee
`GetSystemTimeAsFileTime`, cuya granularidad es una propiedad **global y mutable** del sistema:
15,625 ms por defecto, y baja a ~1 ms sólo mientras algún otro proceso la sube con
`timeBeginPeriod`. Que hoy funcione está prestado de un proceso ajeno.

Medido el 2026-08-19 con el timer global en 1,0 ms: dos `write_teardown_record` consecutivas
colisionaban el **14 %** de las veces. Con el timer en su valor por defecto, casi siempre. Y los
respaldos de DB eran peores todavía porque su sello es al **segundo**.

Un sello con seis dígitos de microsegundos (`%f`) no cambia nada: el formato declara una unidad,
no una granularidad. Es la misma trampa que `thread_time` con su `resolution=1e-07`, que en
realidad avanza de a 15,625 ms.

## Por qué `O_EXCL` y no `if destino.exists()`

Preguntar y después escribir son **dos** pasos, y entre medio cabe otro escritor: otro hilo, o el
`.exe` corriendo mientras un script de QA escribe en la misma carpeta. `O_CREAT | O_EXCL` es la
primitiva del sistema operativo que crea **sólo si no existe**, en un paso indivisible. El que
pierde la carrera recibe `FileExistsError` y prueba el número siguiente.
"""
from __future__ import annotations

import os
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

#: Cota para no girar para siempre si algo patológico deja todo nombre ocupado. Mil artefactos
#: con el mismo sello no es un caso real: es una señal, y por eso se levanta en vez de seguir.
MAX_INTENTOS = 1000


def candidatos_numerados(carpeta: Path, base: str, extensiones: Sequence[str] = ("json",),
                         max_intentos: int | None = None) -> Iterator[list[Path]]:
    """Genera juegos de rutas hermanas: `base.ext`, después `base_2.ext`, `base_3.ext`…

    `extensiones` vacío reserva el nombre pelado (para llamadores que ya traen la extensión
    adentro de `base`). El punto de más se tolera: `"png"` y `".png"` dan lo mismo.

    Crea la carpeta al primer pedido — quien reserva necesita que exista, y hacerlo acá evita que
    cada llamador se acuerde.
    """
    # `MAX_INTENTOS` se resuelve ACÁ y no como valor por defecto del parámetro: un default se
    # evalúa al importar, así que quedaría una copia congelada del módulo y la constante dejaría
    # de ser la autoridad (además de volverla imparcheable desde un test).
    if max_intentos is None:
        max_intentos = MAX_INTENTOS
    carpeta.mkdir(parents=True, exist_ok=True)
    for intento in range(1, max_intentos + 1):
        nombre = base if intento == 1 else f"{base}_{intento}"
        if extensiones:
            yield [carpeta / f"{nombre}.{str(e).lstrip('.')}" for e in extensiones]
        else:
            yield [carpeta / nombre]


def reservar(candidatos: Iterable[Sequence[Path]]) -> list[Path]:
    """Del primer juego de rutas que se pueda crear **entero**, devuelve la lista en el orden dado.

    Todo-o-nada por hermano: si un solo miembro del juego está ocupado se sueltan los ya creados y
    se pasa al siguiente candidato. Sin eso, dos corridas podrían repartirse un par `.json`/`.md`
    y cada reporte quedaría a medias — pareciendo completo.

    El orden es parte del contrato: los llamadores desempaquetan posicionalmente.

    Deja archivos de 0 bytes que el llamador pisa enseguida con su contenido real. Qué hacer si
    ese segundo paso falla es **decisión del llamador**, no de acá.

    Levanta `FileExistsError` si se agotan los candidatos sin dejar residuos.
    """
    ultimo: Sequence[Path] | None = None
    for rutas in candidatos:
        ultimo = rutas
        creadas: list[Path] = []
        try:
            for ruta in rutas:
                os.close(os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                creadas.append(ruta)
            return list(rutas)
        except FileExistsError:
            # Soltar los hermanos ya creados: si quedaran, la próxima corrida los vería ocupados
            # y se correría de nombre por un residuo nuestro.
            for ruta in creadas:
                ruta.unlink(missing_ok=True)
    donde = ultimo[0].parent if ultimo else "(sin candidatos)"
    raise FileExistsError(f"no quedó ningún nombre libre en {donde}")
