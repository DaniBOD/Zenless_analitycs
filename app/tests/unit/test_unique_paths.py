"""La primitiva de reserva de nombres: crear-sólo-si-no-existe, en un paso indivisible.

Existe porque la misma decisión se escribió DOS veces el 2026-08-19, en dos worktrees que no se
veían: `audit_paths.reservar_rutas` (bitácoras) y `db.connection.respaldar_db` (respaldos RNF-01).
Las dos implementaciones eran casi calcadas —mismo `O_EXCL`, mismo tope de 1000— pero **divergían
en la política de falla, y las dos tenían razón**:

    audit/    si algo falla a mitad, DEJA el archivo vacío  → ruido visible, nadie restaura de él
    backups   si la copia falla, BORRA la reserva           → un .db vacío parece un respaldo bueno

O sea que no eran dos primitivas: era una primitiva con dos políticas. Acá vive la primitiva; la
política se queda en cada llamador.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.unique_paths import candidatos_numerados, reservar


def test_reserva_el_primer_candidato_libre(tmp_path):
    (rutas,) = [reservar(candidatos_numerados(tmp_path, "corrida", ("json",)))]
    assert rutas == [tmp_path / "corrida.json"]
    assert rutas[0].exists(), "reservar CREA el archivo; si no, otro escritor puede ganártelo"


def test_saltea_los_ocupados_sin_pisarlos(tmp_path):
    ajeno = tmp_path / "corrida.json"
    ajeno.write_text("de otro proceso", encoding="utf-8")

    (ruta,) = reservar(candidatos_numerados(tmp_path, "corrida", ("json",)))

    assert ruta.name == "corrida_2.json"
    assert ajeno.read_text(encoding="utf-8") == "de otro proceso", "se pisó un archivo ajeno"


def test_el_juego_de_hermanos_se_toma_ENTERO_o_ninguno(tmp_path):
    """El censo escribe `.json` y `.md` bajo el mismo sello. Si se pudieran repartir entre dos
    corridas, cada reporte quedaría a medias —y peor: parecería completo—. Acá el `.md` está
    ocupado y el `.json` libre: el juego entero tiene que irse al número siguiente."""
    (tmp_path / "censo.md").write_text("ocupado", encoding="utf-8")

    rutas = reservar(candidatos_numerados(tmp_path, "censo", ("json", "md")))

    assert [r.name for r in rutas] == ["censo_2.json", "censo_2.md"]
    assert not (tmp_path / "censo.json").exists(), \
        "se quedó con el hermano suelto del intento fallido"


def test_devuelve_los_hermanos_en_el_ORDEN_pedido(tmp_path):
    """El llamador desempaqueta posicionalmente (`json_p, md_p = reservar(...)`), así que el orden
    es parte del contrato, no un detalle."""
    rutas = reservar(candidatos_numerados(tmp_path, "censo", ("json", "md")))
    assert [r.suffix for r in rutas] == [".json", ".md"]


def test_al_agotar_los_intentos_levanta_en_vez_de_pisar(tmp_path):
    """Quedarse sin nombre libre no es un caso normal: es una señal. Levantar deja que el llamador
    aborte la escritura, que es la conducta segura."""
    for n in ("corrida.json", "corrida_2.json", "corrida_3.json"):
        (tmp_path / n).write_text("x", encoding="utf-8")

    with pytest.raises(FileExistsError):
        reservar(candidatos_numerados(tmp_path, "corrida", ("json",), max_intentos=3))


def test_no_deja_reservas_a_medias_cuando_agota(tmp_path):
    """Si al rendirse quedaran hermanos sueltos, la próxima corrida los vería ocupados y se
    correría de nombre por un residuo nuestro."""
    for n in ("c.json", "c_2.json", "c_3.json"):
        (tmp_path / n).write_text("x", encoding="utf-8")

    with pytest.raises(FileExistsError):
        reservar(candidatos_numerados(tmp_path, "c", ("json", "md"), max_intentos=3))

    assert not list(tmp_path.glob("*.md")), "quedaron hermanos sueltos de los intentos fallidos"


def test_crea_la_carpeta_si_no_existe(tmp_path):
    destino = tmp_path / "sub" / "dir"
    (ruta,) = reservar(candidatos_numerados(destino, "x", ("json",)))
    assert ruta.exists()


def test_la_extension_tolera_el_punto_de_mas(tmp_path):
    (ruta,) = reservar(candidatos_numerados(tmp_path, "x", (".png",)))
    assert ruta.name == "x.png", "'.png' y 'png' tienen que dar lo mismo"


def test_sin_extensiones_reserva_el_nombre_pelado(tmp_path):
    """Los dumps de frames traen la extensión adentro del base; no todos los llamadores la
    separan."""
    (ruta,) = reservar(candidatos_numerados(tmp_path, "frame.png", ()))
    assert ruta.name == "frame.png"


def test_es_ATOMICA_no_un_mira_y_despues_escribe(tmp_path, monkeypatch):
    """El corazón del arreglo. `if not existe: escribir` son DOS pasos, y entre medio cabe otro
    escritor —otro hilo, o el `.exe` mientras un script de QA usa la misma carpeta—. Simulamos ese
    intruso: aparece JUSTO después de que el candidato se vio libre.

    Si la implementación consultara y después creara, se llevaría puesto al intruso. Con
    `O_CREAT|O_EXCL` el que pierde la carrera recibe `FileExistsError` y se corre de nombre.
    """
    real_open = os.open
    intruso = tmp_path / "x.json"

    def open_con_intruso(path, flags, *a, **kw):
        if Path(path) == intruso and not intruso.exists():
            intruso.write_text("me adelanté", encoding="utf-8")   # gana la carrera
        return real_open(path, flags, *a, **kw)

    monkeypatch.setattr(os, "open", open_con_intruso)

    (ruta,) = reservar(candidatos_numerados(tmp_path, "x", ("json",)))

    assert ruta.name == "x_2.json"
    assert intruso.read_text(encoding="utf-8") == "me adelanté", \
        "se pisó al escritor que ganó la carrera — la reserva no es atómica"
