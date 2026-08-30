"""Encuadre de mensajes entre la app y el worker de OCR. Sólo la plomería, sin política.

Vive aparte de `ocr_worker` y de `ocr_service` porque lo usan los dos, y una sola autoridad sobre
*cómo se escribe un mensaje en el socket* evita que las dos puntas se separen (regla B1).

## Por qué un socket de loopback y no stdin/stdout

El `.exe` se compila `--windowed` (`console=False`, `app/build/main.spec`). En ese modo los handles
estándar del proceso no son confiables: `sys.stdout` puede venir `None`, y un protocolo binario
sobre un stream que a veces no existe es una fuente de fallas que **sólo aparecen empaquetado**
(regla D1). Un socket no depende de nada de eso.

Se bindea a `127.0.0.1` explícitamente —nunca a `0.0.0.0`— para que no haya nada escuchando fuera
de la máquina, y para no disparar el diálogo del firewall de Windows.

## Por qué no `multiprocessing`

No hay `freeze_support()` en ningún lado del proyecto. Sin él, el arranque por `spawn` bajo
PyInstaller **vuelve a ejecutar la app entera en cada hijo**: el modo de falla es una cascada de
procesos, no un error. Un `subprocess` con centinela de argv lo evita por construcción.

## El encuadre

    [4 bytes big-endian: largo]  [pickle protocolo 5]

`pickle` y no algo más austero porque lo que cruza son arrays de numpy y tuplas anidadas, y está
medido: el payload más grande del pipeline (1036×742×3, 2,3 MB) tarda **1,34 ms** ida y vuelta,
contra 124-235 ms de una inferencia. Menos del 1 % — no justifica memoria compartida.
"""
from __future__ import annotations

import os
import pickle
import socket
import struct

#: Nombre de la variable por la que el padre le pasa al hijo dónde conectarse.
ENV_PUERTO = "DANIBOD_OCR_PORT"
#: Secreto compartido. El socket escucha en loopback, así que cualquier proceso local podría
#: conectarse; el token hace que sólo el hijo que lanzamos nosotros sea atendido.
ENV_TOKEN = "DANIBOD_OCR_TOKEN"
#: Centinela de argv. El `.exe` es su propio worker: se lanza a sí mismo con este flag.
FLAG_WORKER = "--ocr-worker"

_CABECERA = struct.Struct(">I")
#: Tope defensivo del tamaño de un mensaje (32 MB). El frame completo de 2560×1440×3 son 11 MB;
#: cualquier cosa por encima de esto es un desencuadre, no un mensaje, y conviene cortar ahí antes
#: de intentar reservar la memoria que el largo dice.
MAX_MENSAJE = 32 * 1024 * 1024


class ErrorProtocolo(RuntimeError):
    """El otro lado cerró, se desencuadró, o mandó algo que no se puede leer."""


def enviar(sock: socket.socket, objeto) -> None:
    """Escribe un mensaje entero. Levanta `OSError` si el socket se cerró."""
    cuerpo = pickle.dumps(objeto, protocol=5)
    sock.sendall(_CABECERA.pack(len(cuerpo)) + cuerpo)


def _leer_exacto(sock: socket.socket, n: int) -> bytes:
    """Lee exactamente `n` bytes. `recv` puede devolver de a pedazos y devolver menos de lo pedido
    sin que sea un error: leer una sola vez es el bug clásico de este protocolo."""
    trozos: list[bytes] = []
    faltan = n
    while faltan:
        t = sock.recv(faltan)
        if not t:
            raise ErrorProtocolo("el otro lado cerró la conexión")
        trozos.append(t)
        faltan -= len(t)
    return b"".join(trozos)


def recibir(sock: socket.socket):
    """Lee un mensaje entero. Levanta `ErrorProtocolo` si el otro lado cerró o se desencuadró."""
    largo = _CABECERA.unpack(_leer_exacto(sock, _CABECERA.size))[0]
    if largo > MAX_MENSAJE:
        raise ErrorProtocolo(f"mensaje de {largo} bytes: por encima del tope, se asume desencuadre")
    try:
        return pickle.loads(_leer_exacto(sock, largo))
    except ErrorProtocolo:
        raise
    except Exception as exc:                      # pickle roto, versión distinta, lo que sea
        raise ErrorProtocolo(f"no se pudo deserializar el mensaje: {exc!r}") from exc


def es_arranque_de_worker(argv: list[str] | None = None) -> bool:
    """¿Este proceso fue lanzado como worker de OCR?

    Se consulta **antes de importar Qt** en `app/main.py`: el hijo empaquetado es el mismo `.exe`
    que la app, y sin este desvío levantaría la interfaz en vez de atender pedidos.
    """
    return FLAG_WORKER in (argv if argv is not None else os.sys.argv)
