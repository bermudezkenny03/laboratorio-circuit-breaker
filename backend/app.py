"""
Backend de mascotas. Maneja el CRUD y consulta MySQL.
"""

import os
import time
import requests
import mysql.connector
from flask import Flask, request, jsonify

app = Flask(__name__)


def get_connection():
    """Conecta a MySQL reintentando hasta 10 veces si no está lista."""
    intentos = 0
    while intentos < 10:
        try:
            return mysql.connector.connect(
                host=os.getenv("DB_HOST"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME")
            )
        except Exception as e:
            intentos += 1
            print(f"[backend] MySQL no disponible aun (intento {intentos}/10): {e}", flush=True)
            time.sleep(3)

    raise Exception("No se pudo conectar a MySQL despues de 10 intentos.")


@app.route("/")
def home():
    return "Backend de mascotas funcionando"


@app.route("/mascotas", methods=["GET"])
def listar_mascotas():
    """Devuelve todas las mascotas de la base de datos."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id, nombre, tipo, id_usuario FROM mascotas")
    filas = cursor.fetchall()
    connection.close()

    mascotas = [
        {"id": f[0], "nombre": f[1], "tipo": f[2], "id_usuario": f[3]}
        for f in filas
    ]

    return jsonify({"mascotas": mascotas})


@app.route("/mascotas/<int:id_mascota>", methods=["GET"])
def obtener_mascota(id_mascota):
    """Busca una mascota por ID. Retorna 404 si no existe."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, nombre, tipo, id_usuario FROM mascotas WHERE id = %s",
        (id_mascota,)
    )
    fila = cursor.fetchone()
    connection.close()

    if not fila:
        return jsonify({"error": f"Mascota {id_mascota} no encontrada"}), 404

    return jsonify({
        "id": fila[0],
        "nombre": fila[1],
        "tipo": fila[2],
        "id_usuario": fila[3]
    })


@app.route("/mascotas", methods=["POST"])
def crear_mascota():
    """Inserta una nueva mascota. id_usuario es opcional (default 1)."""
    data = request.json

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO mascotas (nombre, tipo, id_usuario) VALUES (%s, %s, %s)",
        (data["nombre"], data["tipo"], data.get("id_usuario", 1))
    )
    connection.commit()
    nuevo_id = cursor.lastrowid
    connection.close()

    return jsonify({"mensaje": "Mascota creada", "id": nuevo_id}), 201


@app.route("/relacion")
def relacion():
    """
    Junta mascotas con usuarios llamando directamente al servicio de usuarios.
    Nota: el gateway tiene su propia versión con Circuit Breaker.
    """
    resp_usuarios = requests.get("http://usuarios:5000/usuarios", timeout=2)
    usuarios_lista = resp_usuarios.json()
    usuarios_map = {u["id"]: u for u in usuarios_lista}

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id, nombre, tipo, id_usuario FROM mascotas")
    filas = cursor.fetchall()
    connection.close()

    resultado = []
    for fila in filas:
        id_m, nombre_m, tipo_m, id_u = fila
        dueno = usuarios_map.get(id_u, {"nombre": "Desconocido", "correo": "-"})
        resultado.append({
            "mascota": {"id": id_m, "nombre": nombre_m, "tipo": tipo_m},
            "dueno": dueno
        })

    return jsonify({"relaciones": resultado})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
