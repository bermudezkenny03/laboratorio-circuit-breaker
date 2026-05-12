"""
Gateway principal que enruta las peticiones a los microservicios.
Implementa Circuit Breaker para evitar fallos en cascada.
"""

import os
import time
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)


class CircuitBreaker:
    """
    Controla el estado de un servicio externo.
    Si falla muchas veces seguidas, deja de enviar peticiones por un tiempo.
    """

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
        """
        Hace la petición GET al servicio. Si el circuito está abierto,
        verifica si ya pasó el tiempo de espera para probar de nuevo.
        """
        if self.estado == self.OPEN:
            segundos_transcurridos = time.time() - self.tiempo_apertura
            segundos_restantes = round(self.tiempo_espera - segundos_transcurridos, 1)

            if segundos_transcurridos >= self.tiempo_espera:
                # Ya pasó el tiempo, pasamos a prueba
                print(
                    f"[CB:{self.nombre}] {self.tiempo_espera}s cumplidos. "
                    "Pasando a HALF_OPEN para probar el servicio.",
                    flush=True
                )
                self.estado = self.HALF_OPEN
            else:
                # Aún no, rechazamos la petición
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
        """Resetea el circuito a normal cuando la petición funciona."""
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
        """
        Cuenta el fallo. Si llega al umbral o falla en HALF_OPEN,
        abre el circuito y empieza a contar el tiempo.
        """
        self.fallos += 1

        print(f"[CB:{self.nombre}] Fallo #{self.fallos} — {motivo}", flush=True)

        if self.estado == self.HALF_OPEN:
            print(
                f"[CB:{self.nombre}] Fallo en HALF_OPEN. "
                "Reabriendo circuito y reiniciando temporizador.",
                flush=True
            )
            self.estado = self.OPEN
            self.tiempo_apertura = time.time()
        elif self.fallos >= self.umbral_fallos:
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
        """Devuelve el estado actual del circuito para el endpoint /estado."""
        data = {
            "servicio": self.nombre,
            "estado": self.estado,
            "fallos": self.fallos,
        }

        if self.estado == self.OPEN and self.tiempo_apertura:
            restante = round(self.tiempo_espera - (time.time() - self.tiempo_apertura), 1)
            data["reintentar_en_seg"] = max(restante, 0)

        return data


# Parámetros del Circuit Breaker desde variables de entorno
CB_UMBRAL_FALLOS = int(os.getenv("CB_UMBRAL_FALLOS", 3))
CB_TIEMPO_ESPERA = int(os.getenv("CB_TIEMPO_ESPERA", 15))
CB_TIMEOUT_HTTP = int(os.getenv("CB_TIMEOUT_HTTP", 2))

URL_BACKEND = os.getenv("URL_BACKEND", "http://backend:5000")
URL_USUARIOS = os.getenv("URL_USUARIOS", "http://usuarios:5000")

# Un circuito por servicio para que fallen de forma independiente
cb_mascotas = CircuitBreaker("mascotas", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)
cb_usuarios = CircuitBreaker("usuarios", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)


@app.route("/mascotas")
def mascotas():
    """Lista todas las mascotas."""
    datos, codigo = cb_mascotas.llamar(f"{URL_BACKEND}/mascotas", CB_TIMEOUT_HTTP)
    return jsonify(datos), codigo


@app.route("/usuarios")
def usuarios():
    """Lista todos los usuarios."""
    datos, codigo = cb_usuarios.llamar(f"{URL_USUARIOS}/usuarios", CB_TIMEOUT_HTTP)
    return jsonify(datos), codigo


@app.route("/mascotas/<int:id_mascota>")
def obtener_mascota(id_mascota):
    """Busca una mascota por ID."""
    datos, codigo = cb_mascotas.llamar(f"{URL_BACKEND}/mascotas/{id_mascota}", CB_TIMEOUT_HTTP)
    return jsonify(datos), codigo


@app.route("/mascotas", methods=["POST"])
def crear_mascota():
    """Crea una mascota enviando JSON al backend."""
    try:
        response = requests.post(f"{URL_BACKEND}/mascotas", json=request.json, timeout=CB_TIMEOUT_HTTP)
        response.raise_for_status()
        cb_mascotas._en_exito()
        return jsonify(response.json()), 201
    except Exception as exc:
        return cb_mascotas._en_fallo(str(exc))


@app.route("/usuarios/<int:id_usuario>")
def obtener_usuario(id_usuario):
    """Busca un usuario por ID."""
    datos, codigo = cb_usuarios.llamar(f"{URL_USUARIOS}/usuarios/{id_usuario}", CB_TIMEOUT_HTTP)
    return jsonify(datos), codigo


@app.route("/usuarios", methods=["POST"])
def crear_usuario():
    """Crea un usuario enviando JSON al servicio de usuarios."""
    try:
        response = requests.post(f"{URL_USUARIOS}/usuarios", json=request.json, timeout=CB_TIMEOUT_HTTP)
        response.raise_for_status()
        cb_usuarios._en_exito()
        return jsonify(response.json()), 201
    except Exception as exc:
        return cb_usuarios._en_fallo(str(exc))


@app.route("/usuarios/<int:id_usuario>", methods=["DELETE"])
def eliminar_usuario(id_usuario):
    """Elimina un usuario por ID."""
    try:
        response = requests.delete(f"{URL_USUARIOS}/usuarios/{id_usuario}", timeout=CB_TIMEOUT_HTTP)
        response.raise_for_status()
        cb_usuarios._en_exito()
        return jsonify(response.json()), 200
    except Exception as exc:
        return cb_usuarios._en_fallo(str(exc))


@app.route("/resumen")
def resumen():
    """Devuelve mascotas y usuarios por separado. Si uno falla, el otro sigue."""
    datos_mascotas, cod_m = cb_mascotas.llamar(f"{URL_BACKEND}/mascotas", CB_TIMEOUT_HTTP)
    datos_usuarios, cod_u = cb_usuarios.llamar(f"{URL_USUARIOS}/usuarios", CB_TIMEOUT_HTTP)

    return jsonify({
        "mascotas": datos_mascotas if cod_m == 200 else {"error": datos_mascotas},
        "usuarios": datos_usuarios if cod_u == 200 else {"error": datos_usuarios},
    }), 200


@app.route("/relacion")
def relacion():
    """
    Junta mascotas con sus dueños directamente en el gateway.
    Si usuarios falla, muestra "Desconocido" en lugar de romper todo.
    """
    datos_mascotas, cod_m = cb_mascotas.llamar(f"{URL_BACKEND}/mascotas", CB_TIMEOUT_HTTP)
    datos_usuarios, cod_u = cb_usuarios.llamar(f"{URL_USUARIOS}/usuarios", CB_TIMEOUT_HTTP)

    mascotas = datos_mascotas.get("mascotas", []) if cod_m == 200 else []
    usuarios_lista = datos_usuarios if cod_u == 200 else []
    usuarios_map = {u["id"]: u for u in usuarios_lista}

    resultado = []
    for m in mascotas:
        dueno = usuarios_map.get(m["id_usuario"], {"nombre": "Desconocido", "correo": "-"})
        resultado.append({
            "mascota": {"id": m["id"], "nombre": m["nombre"], "tipo": m["tipo"]},
            "dueno": dueno
        })

    return jsonify({
        "relaciones": resultado,
        "estado": {
            "mascotas": "OK" if cod_m == 200 else "FALLIDO",
            "usuarios": "OK" if cod_u == 200 else "FALLIDO"
        }
    }), 200


@app.route("/estado")
def estado_circuitos():
    """Muestra cómo está cada circuito (CLOSED, OPEN, HALF_OPEN)."""
    return jsonify({
        "circuitos": [
            cb_mascotas.info(),
            cb_usuarios.info(),
        ]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
