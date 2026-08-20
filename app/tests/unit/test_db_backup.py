"""`respaldar_db`: la copia RNF-01 previa a toda escritura al dominio.

Por qué el nombre no puede colgar del reloj: el sello sirve para que un humano ubique la copia en
su día, pero `datetime.now()` en Windows avanza de a un tick del timer global del sistema —
15,625 ms por defecto— así que dos respaldos seguidos caen en el mismo nombre, y `shutil.copy2`
pisa el destino sin avisar. El modo de falla no es "un archivo menos": es un archivo con nombre de
*pre*-escritura cuyo contenido ya trae la escritura adentro. Eso es exactamente lo que RNF-01
existe para impedir.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.db.connection import respaldar_db


def _db(p: Path, contenido: bytes = b"SQLite format 3\x00original") -> Path:
    p.write_bytes(contenido)
    return p


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_copia_el_contenido_y_devuelve_donde_quedo(tmp_path):
    origen = _db(tmp_path / "danibod_zzz_v2.db")
    copia = respaldar_db(origen, "premig")
    assert copia.parent == origen.parent, "la copia va al lado de la DB, no a un temp del sistema"
    assert copia.name.startswith("danibod_zzz_v2.backup_premig_")
    assert _sha(copia) == _sha(origen)


def test_dos_respaldos_en_el_mismo_segundo_van_a_archivos_distintos(
        tmp_path, reloj_de_pared_congelado):
    origen = _db(tmp_path / "danibod_zzz_v2.db")
    primero = respaldar_db(origen, "precenso")
    _db(origen, b"SQLite format 3\x00YA ESCRITO")      # entre medio se escribió la DB
    segundo = respaldar_db(origen, "precenso")

    assert primero != segundo
    assert primero.name == "danibod_zzz_v2.backup_precenso_20260819_143012.db"
    assert segundo.name == "danibod_zzz_v2.backup_precenso_20260819_143012_2.db"
    assert primero.read_bytes() == b"SQLite format 3\x00original", \
        "el primer respaldo tiene que seguir siendo el estado previo"


def test_no_pisa_un_archivo_que_ya_ocupa_el_nombre(tmp_path, reloj_de_pared_congelado):
    """El que reserva puede no ser el único escribiendo en la carpeta: el `.exe` y un script de QA
    conviven. Por eso la reserva es `O_CREAT|O_EXCL` y no un `if existe`."""
    origen = _db(tmp_path / "danibod_zzz_v2.db")
    ajeno = tmp_path / "danibod_zzz_v2.backup_precenso_20260819_143012.db"
    ajeno.write_bytes(b"de otro proceso")

    copia = respaldar_db(origen, "precenso")
    assert copia != ajeno
    assert ajeno.read_bytes() == b"de otro proceso", "se pisó un archivo ajeno"


def test_al_agotar_los_intentos_levanta_en_vez_de_pisar(tmp_path, monkeypatch,
                                                        reloj_de_pared_congelado):
    """Quedarse sin nombre libre es una señal, no un caso normal. Levantar aborta la escritura
    al dominio, que es la conducta segura: sin backup no se escribe."""
    # El tope vive en `unique_paths`, que es la autoridad compartida: `respaldar_db` y
    # `reservar_rutas` lo consultan en cada llamada, no lo copian al importar.
    import app.core.unique_paths as up
    monkeypatch.setattr(up, "MAX_INTENTOS", 3)
    origen = _db(tmp_path / "danibod_zzz_v2.db")
    for sufijo in ("", "_2", "_3"):
        (tmp_path / f"danibod_zzz_v2.backup_precenso_20260819_143012{sufijo}.db").touch()

    with pytest.raises(FileExistsError):
        respaldar_db(origen, "precenso")


def test_si_la_copia_falla_no_queda_un_backup_vacio(tmp_path, monkeypatch):
    """Un `.db` de 0 bytes con nombre de backup es peor que ningún archivo: parece un respaldo.
    (Acá se limpia; en `audit/` la decisión es la contraria, porque allá el archivo vacío es
    ruido visible y no una copia de la que alguien podría intentar restaurar.)"""
    import app.db.connection as conn

    def _falla(*a, **k):
        raise OSError("disco lleno")

    origen = _db(tmp_path / "danibod_zzz_v2.db")
    monkeypatch.setattr(conn.shutil, "copy2", _falla)

    with pytest.raises(OSError):
        respaldar_db(origen, "precenso")
    assert list(tmp_path.glob("*.backup_*.db")) == [], "quedó una reserva vacía sin limpiar"
