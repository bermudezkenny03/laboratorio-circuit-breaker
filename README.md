# Laboratorio - Circuit Breaker

---

## Estructura del repositorio

```
laboratorio_circuit_breaker/
├── docker-compose.yml
├── .env                       ← configuración del Circuit Breaker
├── README.md
├── gateway/
│   ├── app.py                 ← Circuit Breaker completo (Fases 2-5)
│   ├── Dockerfile
│   └── requirements.txt
├── usuarios/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── backend/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
└── evidencias/
    ├── fase1.png
    ├── fase2.png
    ├── fase3.png
    ├── fase4.png
    └── fase5.png
```

---

## Cómo levantar el proyecto

```bash
# 1. Entrar a la carpeta
cd laboratorio_circuit_breaker

# 2. Levantar todos los servicios
docker compose up --build
```

### Endpoints disponibles

| Endpoint    | URL                              | Descripción                              |
|-------------|----------------------------------|------------------------------------------|
| `/mascotas` | http://localhost:5000/mascotas   | Lista mascotas (con Circuit Breaker)     |
| `/usuarios` | http://localhost:5000/usuarios   | Lista usuarios (con Circuit Breaker)     |
| `/resumen`  | http://localhost:5000/resumen    | Ambos servicios en una sola respuesta    |
| `/relacion` | http://localhost:5000/relacion   | Relación mascota-usuario                 |
| `/estado`   | http://localhost:5000/estado     | Estado en tiempo real de los circuitos   |

---

## Configuración del Circuit Breaker (.env)

Los parámetros se configuran desde el `.env` **sin tocar código**.
Después de cambiar un valor, reinicia con `docker compose up`.

```env
# Fallos consecutivos que abren el circuito
CB_UMBRAL_FALLOS=3

# Segundos en OPEN antes de pasar a HALF_OPEN
CB_TIEMPO_ESPERA=15

# Timeout máximo por petición HTTP (segundos)
CB_TIMEOUT_HTTP=2
```

---

## FASE 1 – OBSERVAR (sin modificar código)

### ¿Qué hicimos?
Levantamos el sistema y apagamos el servicio de mascotas:
```bash
docker compose stop backend
```
Luego hicimos varias peticiones a `/mascotas` y revisamos los logs con:
```bash
docker compose logs gateway
```

### ¿Qué hace el sistema actualmente?

El gateway original tenía un Circuit Breaker **parcial** solo en `/mascotas`:
- Contaba fallos con una variable global `fallos_backend`.
- Después de 3 fallos ponía `circuito_abierto = True`.
- Devolvía `503` cuando el circuito estaba abierto.

El endpoint `/usuarios` **no tenía ninguna protección**: si el servicio caía, el gateway devolvía error 500 o se quedaba colgado esperando el timeout.

### ¿Se protege o insiste?

| Endpoint    | Comportamiento con servicio caído                        |
|-------------|----------------------------------------------------------|
| `/mascotas` | Insiste 3 veces → luego bloquea (protección básica)      |
| `/usuarios` | Insiste indefinidamente, sin timeout ni fallback         |

**Conclusión:** El sistema se protege parcialmente. El Circuit Breaker de clase no tenía estado Half-Open, por lo que el circuito nunca se cerraba solo aunque el servicio se recuperara. Había que reiniciar el gateway manualmente.

---

## FASE 2 – APLICAR (extensión del Circuit Breaker)

### ¿Qué hicimos?

En lugar de copiar el mismo bloque de variables globales tres veces, creamos una **clase `CircuitBreaker` reutilizable** que encapsula estado, contador y lógica de transición.

Instanciamos **un objeto independiente por servicio**:

```python
cb_mascotas = CircuitBreaker("mascotas", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)
cb_usuarios = CircuitBreaker("usuarios", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)
cb_relacion = CircuitBreaker("relacion", CB_UMBRAL_FALLOS, CB_TIEMPO_ESPERA)
```

Los valores `CB_UMBRAL_FALLOS` y `CB_TIEMPO_ESPERA` vienen del `.env` con `os.getenv()`, no están hardcodeados en el código.

### Decisiones de diseño

**¿Cada servicio debe tener su propio contador de fallos?**
Sí. Un fallo en mascotas no tiene relación con la salud del servicio de usuarios. Mezclar contadores llevaría a bloquear servicios que están funcionando bien.

**¿El circuito debe abrirse de forma independiente por servicio?**
Sí. Si el backend cae, `/usuarios` debe seguir respondiendo normalmente. Esto se demuestra en el endpoint `/resumen`, que llama a los dos servicios y devuelve lo que esté disponible.

**¿Qué pasa si falla un servicio pero el otro sigue funcionando?**
El endpoint `/resumen` lo muestra claramente: cada `CircuitBreaker` es autónomo. Si `cb_mascotas` está `OPEN` y `cb_usuarios` está `CLOSED`, el resumen devuelve los usuarios correctamente y solo reporta error en mascotas.

---

## FASE 3 – INVESTIGAR (Half-Open)

### ¿Qué significa "half-open"?

**Half-Open** es el tercer estado del Circuit Breaker. Funciona como una sala de espera: el circuito lleva un tiempo abierto y decide hacer **un único intento de prueba** para ver si el servicio se recuperó, antes de volver a abrir el tráfico completo.

### ¿Cuándo se vuelve a intentar una llamada?

Cuando transcurre el tiempo configurado en `CB_TIEMPO_ESPERA` (15 segundos por defecto). En ese momento el estado cambia automáticamente de `OPEN` a `HALF_OPEN` y la próxima petición actúa como prueba real.

```
CLOSED ──(3 fallos)──► OPEN
OPEN   ──(15 s)──────► HALF_OPEN
HALF_OPEN ──(éxito)──► CLOSED    ← circuito cerrado de nuevo
HALF_OPEN ──(fallo)──► OPEN      ← vuelve a esperar 15 s
```

### ¿Qué pasa si el servicio vuelve a fallar?

Si la llamada de prueba en `HALF_OPEN` también falla, el circuito **regresa inmediatamente a `OPEN`** y reinicia el temporizador. No se abre tráfico hasta confirmar que el servicio responde correctamente.

---

## FASE 4 – IMPLEMENTAR (Recuperación)

### ¿Qué implementamos?

La lógica completa de recuperación está en la clase `CircuitBreaker` del `gateway/app.py`:

```python
# Al abrir el circuito se guarda el timestamp
self.tiempo_apertura = time.time()

# En cada llamada, si está OPEN se verifica si ya pasó el tiempo
if self.estado == self.OPEN:
    if time.time() - self.tiempo_apertura >= self.tiempo_espera:
        self.estado = self.HALF_OPEN   # ← transición automática

# Éxito en HALF_OPEN → cerrar circuito
self.estado = self.CLOSED
self.fallos = 0

# Fallo en HALF_OPEN → volver a OPEN y reiniciar temporizador
self.estado          = self.OPEN
self.tiempo_apertura = time.time()
```

### Parámetros elegidos

| Variable          | Valor | Justificación                                         |
|-------------------|-------|-------------------------------------------------------|
| `CB_UMBRAL_FALLOS`| 3     | 3 errores consecutivos son señal clara de caída       |
| `CB_TIEMPO_ESPERA`| 15 s  | Tiempo razonable para que un contenedor Docker reinicie|
| `CB_TIMEOUT_HTTP` | 2 s   | Evita que el gateway se quede esperando indefinidamente|

---

## FASE 5 – VALIDAR

### Comandos para cada escenario

```bash
# Apagar el backend (servicio de mascotas)
docker compose stop backend

# Volver a encenderlo
docker compose start backend

# Ver logs del gateway en tiempo real
docker compose logs -f gateway
```

### Escenario 1 – Servicio funcionando (CLOSED)
```json
GET /estado
{
  "circuitos": [
    { "servicio": "mascotas", "estado": "CLOSED", "fallos": 0 },
    { "servicio": "usuarios", "estado": "CLOSED", "fallos": 0 }
  ]
}
```

### Escenario 2 – Servicio caído (acumulando fallos)
```json
GET /mascotas  →  503
{ "error": "Servicio 'mascotas' no disponible.", "fallos_acumulados": 1 }

GET /mascotas  →  503
{ "error": "Servicio 'mascotas' no disponible.", "fallos_acumulados": 2 }

GET /mascotas  →  503
{ "error": "Servicio 'mascotas' no disponible.", "fallos_acumulados": 3 }
```

### Escenario 3 – Circuito abierto (respuesta inmediata sin tocar el servicio)
```json
GET /mascotas  →  503
{
  "error": "Servicio 'mascotas' bloqueado temporalmente.",
  "estado_circuito": "OPEN",
  "reintentar_en_seg": 11.4
}

# El servicio de usuarios sigue funcionando normalmente
GET /usuarios  →  200 OK
```

### Escenario 4 – Recuperación (HALF_OPEN → CLOSED)
```bash
# Reiniciar backend y esperar 15 segundos
docker compose start backend

# La siguiente petición actúa como prueba
GET /mascotas  →  200 OK   ← circuito se cierra automáticamente
```
```json
GET /estado
{ "servicio": "mascotas", "estado": "CLOSED", "fallos": 0 }
```

---

## Análisis final

### ¿Qué cambió en el comportamiento del sistema?

Antes el gateway colapsaba sin control cuando un servicio fallaba. Ahora:
- Responde rápido con mensajes claros cuando un circuito está abierto.
- Los servicios son independientes: si cae uno, los demás siguen operando.
- El sistema se recupera solo cuando el servicio vuelve, sin reinicio manual.
- Los parámetros se configuran desde `.env` sin tocar código.

### ¿Qué decisiones tomaron?

1. **Clase reutilizable** en lugar de variables globales repetidas — más limpio y escalable.
2. **Variables de entorno** para todos los parámetros — permite cambiar el comportamiento sin modificar código.
3. **Endpoint `/estado`** — permite ver el estado de los circuitos en tiempo real, muy útil para monitoreo y evidencias.
4. **Endpoint `/resumen`** — demuestra visiblemente que los circuitos son independientes.

### ¿Qué dificultades encontraron?

- **Estado en memoria**: en producción con múltiples workers el estado de los CircuitBreakers debería estar en Redis para ser compartido. En este laboratorio con un solo proceso Flask es suficiente.
- **Half-Open con una sola prueba**: si la prueba llega justo cuando el servicio sube pero aún no está listo, el circuito vuelve a abrirse. Una mejora sería exigir N éxitos consecutivos antes de cerrar definitivamente.
- **Distinguir fallo transitorio de fallo permanente**: un umbral de 3 puede ser agresivo para errores de red intermitentes. En producción se usaría una ventana de tiempo deslizante.
