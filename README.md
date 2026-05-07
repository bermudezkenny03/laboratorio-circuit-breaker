# Laboratorio Circuit Breaker

Sistema de microservicios con Flask, MySQL, Docker y Circuit Breaker.

## Requisitos

- Docker Desktop
- Python

## Instalacion y ejecucion

### Opcion recomendada: Docker

```bash
docker compose up --build
```

Para detener el proyecto:

```bash
docker compose down
```

### Opcion local con entorno virtual

Crear entorno virtual:

```bash
python -m venv .venv
```

Activar entorno virtual en Windows:

```bash
.venv\Scripts\activate
```

Instalar dependencias:

```bash
pip install -r backend/requirements.txt
pip install -r gateway/requirements.txt
pip install -r usuarios/requirements.txt
```

## Endpoints

| Endpoint | URL |
|---|---|
| Mascotas | http://localhost:5000/mascotas |
| Usuarios | http://localhost:5000/usuarios |
| Resumen | http://localhost:5000/resumen |
| Relacion | http://localhost:5000/relacion |
| Estado | http://localhost:5000/estado |

## Probar Circuit Breaker

Apagar backend:

```bash
docker compose stop backend
```

Ver logs:

```bash
docker compose logs -f gateway
```

Encender backend:

```bash
docker compose start backend
```

## Configuracion

Los valores principales estan en `.env`:

```env
CB_UMBRAL_FALLOS=3
CB_TIEMPO_ESPERA=15
CB_TIMEOUT_HTTP=2
```

## Evidencias

Las capturas estan en la carpeta `evidencias/`.