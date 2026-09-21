"""De dónde salen `app/resources/ocr/*.onnx`, y cómo volver a hacerlos.

Los dos modelos que usa el OCR son **los mismos** que PaddleOCR bajaba a `~/.paddleocr`
(PP-OCRv3 detección en inglés + reconocimiento latino), convertidos a ONNX. No se re-entrenó ni se
cambió nada: sólo cambia el motor que los corre, porque medido sobre el panel de S9 con la máquina
ocupada ONNX Runtime rinde 40 % mejor que paddle inference (ver
`Dev_IA/documentacion_cruda/2026-09/2026-09-21_PERF_Fase_2E_el_motor_del_OCR.md`).

## Por qué esto es un script y no un `pip install`

`paddle2onnx` necesita `paddlepaddle` **y** arrastra `onnx`, que a su vez quiere subir `protobuf`
a 4.x. El entorno de la app está clavado en protobuf 3.20.2 porque paddlepaddle 2.6.2 lo pide, y
este proyecto ya perdió un día reconstruyendo el entorno por una subida así. Entonces: la
conversión se hace **en un venv desechable**, y al repo entran sólo los `.onnx`.

    py -3.11 -m venv C:\\Temp\\vonnx          # ruta CORTA: `onnx` tiene paths larguísimos y
                                              # revienta con WinError 206 en una ruta profunda
    C:\\Temp\\vonnx\\Scripts\\pip install numpy==1.26.4 paddlepaddle==2.6.2 paddle2onnx==1.3.1
    C:\\Temp\\vonnx\\Scripts\\python tools\\export_ocr_onnx.py

## Verificación obligatoria después de convertir

No alcanza con que el archivo exista. Lo que hay que mirar es que **el parser saque exactamente lo
mismo**, que es el dato que termina en la DB: correr el dump de las 19 capturas de S9 con un motor
y con el otro (`DANIBOD_OCR_ENGINE=paddle`) y comparar set, slot, nivel, main y los 4 substats con
sus rolls. Cuando se hizo esta conversión dio **0 diferencias en 19**.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESTINO = REPO / "app" / "resources" / "ocr"

#: (carpeta del modelo bajo ~/.paddleocr/whl, nombre del .onnx que viaja en la app)
MODELOS = [
    ("det/en/en_PP-OCRv3_det_infer", "ppocrv3_det_en.onnx"),
    ("rec/latin/latin_PP-OCRv3_rec_infer", "ppocrv3_rec_latin.onnx"),
]


def main() -> int:
    cache = Path.home() / ".paddleocr" / "whl"
    if not cache.is_dir():
        print(f"No está {cache}. Esos son los modelos que PaddleOCR baja en el primer arranque:\n"
              "correr la app una vez con el motor viejo (DANIBOD_OCR_ENGINE=paddle) los trae.")
        return 2
    DESTINO.mkdir(parents=True, exist_ok=True)
    for sub, nombre in MODELOS:
        origen = cache / sub
        if not origen.is_dir():
            print(f"falta {origen}")
            return 2
        salida = DESTINO / nombre
        # opset 11 es un piso: paddle2onnx lo sube solo a 14 por `hard_swish`, y lo dice.
        cmd = [sys.executable, "-m", "paddle2onnx", "--model_dir", str(origen),
               "--model_filename", "inference.pdmodel",
               "--params_filename", "inference.pdiparams",
               "--save_file", str(salida), "--opset_version", "11"]
        print(f"\n== {nombre} ==\n{' '.join(cmd)}", flush=True)
        r = subprocess.run(cmd)
        if r.returncode != 0 or not salida.is_file():
            # El ejecutable `paddle2onnx.exe` del venv es el mismo, por si `-m` no está disponible.
            exe = Path(sys.executable).with_name("paddle2onnx.exe")
            if not exe.is_file():
                print("no se pudo convertir y no está paddle2onnx.exe")
                return 1
            r = subprocess.run([str(exe)] + cmd[3:])
            if r.returncode != 0:
                return 1
        print(f"{salida.relative_to(REPO)} · {salida.stat().st_size/1e6:.1f} MB")
    print("\nListo. Ahora verificar que el PARSER saque lo mismo con los dos motores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
