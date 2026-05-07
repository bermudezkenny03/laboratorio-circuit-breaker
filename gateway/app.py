import os
import time
import requests
from flask import Flask, jsonify

app = Flask(__name__)


class CircuitBreaker:
    # Estados del circuito: normal, bloqueado o prueba de recuperación.
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, nombre: str, umbral_fallos: int, tiempo_espera: int):
        self.nombre = nombre
        self.umbral_fallos = umbral_fallos
        self.tiempo_espera = tiempo_espera
        self.estado = self.CLOSED
        self.fallos = 0
        self.tiempo_apertura = None

    def llamar(self, url: str, timeout: int = 2):
        # Si el circuito está abierto, solo se permite probar de nuevo cuando vence el tiempo de espera.
        if self.estado == self.OPEN:
            segundos_transcurridos = time.time() - self.tiempo_apertura
            segundos_restantes = round(self.tiempo_espera - segundos_transcurridos, 1)

            if segundos_transcurridos >= self.tiempo_espera:
                print(
                    f"[CB:{self.nombre}] {self.tiempo_espera}s cumplidos. "
                    "Pasando a HALF_OPEN para probar el servicio.",
                    flush=True
                )
                self.estado = self.HALF_OPEN
            else:
                print(
                    f"[CB:{self.nombre}] Circuito ABIERTO. "
                    f"Reintento en {segundos_restantes}s.",
                    flush=True
                )
                return {
                    "error": f"Servicio '{self.nombre}' bloqueado temporalmente.",
                    "estado_circuito": self.estado,
                    "reintentar_en_seg": segundos_restantes
                }, 503

        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            self._en_exito()
            return response.json(), 200
        except Exception as exc:
            return self._en_fallo(str(exc))

    def _en_exito(self):
        # Un éxito recupera el circuito y reinicia el contador de fallos.
        if self.estado == self.HALF_OPEN:
            print(
                f"[CB:{self.nombre}] Prueba exitosa en HALF_OPEN. "
                "Cerrando circuito — servicio recuperado.",
                flush=True
            )

        self.estado = self.CLOSED
        self.fallos = 0
        self.tiempo_apertura = None

    def _en_fallo(self, motivo: str):
        self.fallos += 1

        print(f"[CB:{self.nombre}] Fallo #{self.fallos} — {motivo}", flush=True)

        if self.estado == self.HALF_OPEN:
            # Si falla durante la prueba, el circuito vuelve a abrirse inmediatamente.
            print(
                f"[CB:{self.nombre}] Fallo en HALF_OPEN. "
                "Reabriendo circuito y reiniciando temporizador.",
                flush=True
            )
            self.estado = self.OPEN
            self.tiempo_apertura = time.time()
        elif self.fallos >= self.umbral_fallos:
            # El circuito se abre al alcanzar el umbral de fallos consecutivos.
            print(
                f"[CB:{self.nombre}] Umbral de {self.umbral_fallos} fallos alcanzado. "
                f"Abriendo circuito por {self.tiempo_espera}s.",
                flush=True
            )
            self.estado = self.OPEN
            self.tiempo_apertura = time.time()

        return {
            "error": f"Servicio '{self.nombre}' no disponible.",
            "estado_circuito": self.estado,
            "fallos_acumulados": self.fallos
        }, 503

    def info(self) -> dict:
        data = {
            "servicio": self.nombre,
            "estado": self.estado,
            "fallos": self.fallos,
        }

        if self.estado == self.OPEN and self.tiempo_apertura:
            restante = round(self.tiempo_espera - (time.time() - self.tiempo_apertura), 1)
            data["reintentar_en_seg"] = max(restante, 0)

        return data


# Configuración ajustable por variables de entorno.
CB_UMBRAL_FALLOS = int(os.getenv("CB_UMBRAL_FALLOS", 3))
CB_TIEMPO_ESPERA = int(os.getenv("CB_TIEMPO_ESPERA", 15))
CB_TIMEOUT_HTTP = int(os.getenv("CB_TIMEOUT_HTTP", 2))

URL_BACKEND = os.getenv("URL_BACKEND", "http://backend:5000")
URL_USUARIOS = os.getenv("URL_USUARIOS", "http://usuarios:5000")

# Cada servicio tiene su propio Circuit Breaker independiente.
cb_mascotas = CircuitBreaker("mascotas", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)
cb_usuarios = CircuitBreaker("usuarios", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)
cb_relacion = CircuitBreaker("relacion", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)


@app.route("/mascotas")
def mascotas():
    datos, codigo = cb_mascotas.llamar(f"{URL_BACKEND}/mascotas", CB_TIMEOUT_HTTP)
    return jsonify(datos), codigo


@app.route("/usuarios")
def usuarios():
    datos, codigo = cb_usuarios.llamar(f"{URL_USUARIOS}/usuarios", CB_TIMEOUT_HTTP)
    return jsonify(datos), codigo


@app.route("/resumen")
def resumen():
    # Combina dos servicios y permite ver que cada circuito falla o responde por separado.
    datos_mascotas, cod_m = cb_mascotas.llamar(f"{URL_BACKEND}/mascotas", CB_TIMEOUT_HTTP)
    datos_usuarios, cod_u = cb_usuarios.llamar(f"{URL_USUARIOS}/usuarios", CB_TIMEOUT_HTTP)

    return jsonify({
        "mascotas": datos_mascotas if cod_m == 200 else {"error": datos_mascotas},
        "usuarios": datos_usuarios if cod_u == 200 else {"error": datos_usuarios},
    }), 200


@app.route("/relacion")
def relacion():
    datos, codigo = cb_relacion.llamar(f"{URL_BACKEND}/relacion", CB_TIMEOUT_HTTP)
    return jsonify(datos), codigo


@app.route("/estado")
def estado_circuitos():
    # Endpoint de diagnóstico para revisar el estado de todos los circuitos.
    return jsonify({
        "circuitos": [
            cb_mascotas.info(),
            cb_usuarios.info(),
            cb_relacion.info(),
        ]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
