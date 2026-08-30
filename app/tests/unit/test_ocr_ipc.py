"""El encuadre de mensajes con el worker de OCR. Sockets de verdad, sin Paddle.

Es plomería, pero es la clase de plomería que falla en producción y no en dev: un `recv` que
devuelve de a pedazos sólo se nota cuando el mensaje es grande, y los mensajes grandes acá son los
frames de 2560×1440.
"""
from __future__ import annotations

import socket
import threading

import numpy as np
import pytest

from app.core import ocr_ipc


@pytest.fixture
def par():
    """Dos extremos conectados de verdad. `socketpair` en Windows usa loopback, que es exactamente
    el transporte real."""
    a, b = socket.socketpair()
    yield a, b
    a.close()
    b.close()


def test_ida_y_vuelta_de_una_tupla(par):
    a, b = par
    ocr_ipc.enviar(a, ("text", ("hola", 0.93)))
    assert ocr_ipc.recibir(b) == ("text", ("hola", 0.93))


def test_un_array_grande_llega_ENTERO(par):
    """El caso que importa: `recv` puede devolver menos de lo pedido sin que sea un error, así que
    leer una sola vez trunca el mensaje. Con un frame de 11 MB pasa siempre; con uno chico, nunca
    —y por eso un test con payload chico no probaría nada—."""
    a, b = par
    grande = np.random.default_rng(0).integers(0, 255, (1439, 2559, 3), dtype=np.uint8)
    hilo = threading.Thread(target=ocr_ipc.enviar, args=(a, grande), daemon=True)
    hilo.start()
    recibido = ocr_ipc.recibir(b)
    hilo.join(timeout=30)
    assert recibido.shape == grande.shape
    assert np.array_equal(recibido, grande), "el array llegó truncado o corrupto"


def test_dos_mensajes_seguidos_no_se_mezclan(par):
    a, b = par
    ocr_ipc.enviar(a, {"uno": 1})
    ocr_ipc.enviar(a, {"dos": 2})
    assert ocr_ipc.recibir(b) == {"uno": 1}
    assert ocr_ipc.recibir(b) == {"dos": 2}


def test_si_el_otro_lado_cierra_se_avisa_en_vez_de_colgarse(par):
    a, b = par
    a.close()
    with pytest.raises(ocr_ipc.ErrorProtocolo):
        ocr_ipc.recibir(b)


def test_un_largo_absurdo_se_corta_antes_de_reservar(par):
    """Si el stream se desencuadra, la cabecera puede decir cualquier cosa. Confiar en ese número
    sería pedirle al sistema que reserve gigabytes por un byte corrido."""
    a, b = par
    a.sendall((10 ** 9).to_bytes(4, "big"))
    with pytest.raises(ocr_ipc.ErrorProtocolo, match="desencuadre"):
        ocr_ipc.recibir(b)


def test_el_centinela_de_argv_se_reconoce():
    assert ocr_ipc.es_arranque_de_worker(["app.exe", ocr_ipc.FLAG_WORKER]) is True
    assert ocr_ipc.es_arranque_de_worker(["app.exe"]) is False
