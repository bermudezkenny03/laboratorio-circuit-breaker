"""
Servicio de usuarios. CRUD básico conectado a MySQL.
"""

import os
import time
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
            print(f"[usuarios] MySQL no disponible aun (intento {intentos}/10): {e}", flush=True)
            time.sleep(3)

    raise Exception("No se pudo conectar a MySQL despues de 10 intentos.")


@app.route("/")
def home():
    return "Servicio de usuarios funcionando"


@app.route("/usuarios", methods=["GET"])
def listar_usuarios():
    """Devuelve todos los usuarios registrados."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id, nombre, correo FROM usuarios")
    filas = cursor.fetchall()
    connection.close()

    usuarios = [
        {"id": f[0], "nombre": f[1], "correo": f[2]}
        for f in filas
    ]

    return jsonify(usuarios)


@app.route("/usuarios/<int:id_usuario>", methods=["GET"])
def obtener_usuario(id_usuario):
    """Busca un usuario por ID. Retorna 404 si no existe."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, nombre, correo FROM usuarios WHERE id = %s",
        (id_usuario,)
    )
    fila = cursor.fetchone()
    connection.close()

    if not fila:
        return jsonify({"error": f"Usuario {id_usuario} no encontrado"}), 404

    return jsonify({
        "id": fila[0],
        "nombre": fila[1],
        "correo": fila[2]
    })


@app.route("/usuarios", methods=["POST"])
def crear_usuario():
    """Inserta un nuevo usuario con nombre y correo."""
    data = request.json

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO usuarios (nombre, correo) VALUES (%s, %s)",
        (data["nombre"], data["correo"])
    )
    connection.commit()
    nuevo_id = cursor.lastrowid
    connection.close()

    return jsonify({"mensaje": "Usuario creado", "id": nuevo_id}), 201


@app.route("/usuarios/<int:id_usuario>", methods=["DELETE"])
def eliminar_usuario(id_usuario):
    """Elimina un usuario por ID. Retorna 404 si no existe."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (id_usuario,))
    connection.commit()
    afectados = cursor.rowcount
    connection.close()

    if afectados == 0:
        return jsonify({"error": f"Usuario {id_usuario} no encontrado"}), 404

    return jsonify({"mensaje": f"Usuario {id_usuario} eliminado"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
