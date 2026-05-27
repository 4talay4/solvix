# Guía completa de despliegue — Curso IA Telegram

Documento único para desplegar el proyecto desde cero en **Ubuntu 24.04**, con IA local, tres bots de Telegram, bibliografía del temario y gestión de incidencias.

**Versión actual:** incluye `/bibliografia`, resolución de tickets con notificación al usuario y optimización para respuestas rápidas.

---

## Índice

1. [Infraestructura disponible](#1-infraestructura-disponible)
2. [Qué hace el sistema](#2-qué-hace-el-sistema)
3. [Requisitos previos](#3-requisitos-previos)
4. [Crear bots en Telegram (BotFather)](#4-crear-bots-en-telegram-botfather)
5. [Obtener tu ID de administrador](#5-obtener-tu-id-de-administrador)
6. [Preparar el servidor principal (8 GB)](#6-preparar-el-servidor-principal-8-gb)
7. [Subir el proyecto a GitHub](#7-subir-el-proyecto-a-github)
8. [Clonar y configurar .env](#8-clonar-y-configurar-env)
9. [Material del curso y bibliografía](#9-material-del-curso-y-bibliografía)
10. [Arrancar Docker](#10-arrancar-docker)
11. [Descargar modelos de IA](#11-descargar-modelos-de-ia)
12. [Indexar documentos (ingesta RAG)](#12-indexar-documentos-ingesta-rag)
13. [Verificaciones técnicas](#13-verificaciones-técnicas)
14. [Pruebas en Telegram](#14-pruebas-en-telegram)
15. [Comandos de los bots](#15-comandos-de-los-bots)
16. [Servidor auxiliar de 4 GB (opcional)](#16-servidor-auxiliar-de-4-gb-opcional)
17. [Mantenimiento](#17-mantenimiento)
18. [Backups](#18-backups)
19. [Solución de problemas](#19-solución-de-problemas)
20. [Seguridad](#20-seguridad)
21. [Referencia rápida](#21-referencia-rápida)
22. [Checklist final](#22-checklist-final)

---

## 1. Infraestructura disponible

| Recurso | Especificación | Uso recomendado |
|---------|----------------|-----------------|
| **Servidor principal** | Ubuntu 24.04 · 8 GB RAM · 2 cores · 80 GB disco | Todo el proyecto (recomendado) |
| **Servidor auxiliar** | 4 GB RAM | Solo Ollama (IA), opcional |

### ¿Por qué 8 GB?

Con 8 GB puedes ejecutar **todos los servicios en un solo servidor** con el modelo `qwen2.5:3b`, que ofrece mejor equilibrio entre **velocidad** y **precisión** que modelos más pequeños.

El servidor de 4 GB es **complementario**: úsalo solo si quieres separar la IA del resto (ver [apartado 16](#16-servidor-auxiliar-de-4-gb-opcional)). No es obligatorio.

### Objetivo de rendimiento

El sistema está configurado para:

- **Respuestas rápidas:** caché semántica de preguntas repetidas (sin llamar al LLM).
- **Respuestas precisas:** RAG limitado al material del curso + citas de documento/apartado.
- **Consulta directa:** `/bibliografia` sin pasar por la IA (instantáneo).

---

## 2. Qué hace el sistema

| Servicio | Función |
|----------|---------|
| **Bot alumnos** | Registro, preguntas IA, `/bibliografia`, `/test` |
| **Bot admin** | Autorizar usuarios, estadísticas, **resolver tickets** |
| **Bot soporte** | Mejoras e incidencias → notifica al admin |
| **RAG API** | Preguntas con contexto del curso + caché |
| **Ollama** | Modelo local de chat y embeddings |
| **ChromaDB** | Índice vectorial del temario |
| **PostgreSQL** | Usuarios, actividad, caché, tickets |

### Flujos principales

**Alumno autorizado:**
```
Pregunta texto → caché? → sí: respuesta instantánea
                      → no: RAG + LLM → respuesta con fuentes
/bibliografia → listado de PDF/MD → detalle + descarga (≤ 20 MB)
```

**Incidencia de soporte:**
```
Usuario → bot soporte → ticket en BD → admin notificado
Admin → /resolver 5 → escribe respuesta → usuario notificado en bot soporte
```

---

## 3. Requisitos previos

### Servidor principal
- Ubuntu 24.04 LTS
- Acceso SSH con sudo
- Salida a internet (Telegram, Docker Hub, modelos Ollama)
- **No** hace falta abrir puertos entrantes

### Telegram
- 3 bots creados en @BotFather (o seguir apartado 4)
- 3 tokens guardados
- Tu Telegram ID numérico

### En tu PC
- Git (opcional)
- Cliente SSH / SCP

---

## 4. Crear bots en Telegram (BotFather)

Si ya tienes los 3 bots, pasa al apartado 5.

1. Abre **@BotFather** en Telegram.
2. Crea tres bots con `/newbot`:

| Bot | Nombre sugerido | Username ejemplo |
|-----|-----------------|------------------|
| Alumnos | Curso Alumnos Bot | `mi_curso_alumnos_bot` |
| Admin | Curso Admin Bot | `mi_curso_admin_bot` |
| Soporte | Curso Soporte Bot | `mi_curso_soporte_bot` |

3. Guarda los **3 tokens**.

### Comandos sugeridos en BotFather (bot alumnos)

```
start - Registrarse o ver estado
help - Ayuda
bibliografia - Documentos del temario
test - Preguntas tipo test resueltas
```

> Telegram no admite tildes en comandos: se usa `/bibliografia` (sin tilde).

---

## 5. Obtener tu ID de administrador

1. Abre [@userinfobot](https://t.me/userinfobot).
2. Pulsa Start.
3. Copia el número **Id** (ej. `987654321`).

Varios admins:

```env
ADMIN_TELEGRAM_IDS=987654321,111222333
```

---

## 6. Preparar el servidor principal (8 GB)

### 6.1 Conectar por SSH

```bash
ssh TU_USUARIO@IP_SERVIDOR_8GB
```

### 6.2 Actualizar sistema

```bash
sudo apt update && sudo apt upgrade -y
```

### 6.3 Instalar Docker

```bash
sudo apt install -y docker.io docker-compose-v2 git curl nano
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

Cierra sesión y reconecta:

```bash
exit
ssh TU_USUARIO@IP_SERVIDOR_8GB
docker --version
docker compose version
```

### 6.4 Swap de respaldo (opcional con 8 GB, recomendable)

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

Con 8 GB el swap es opcional pero protege picos de memoria al generar respuestas.

---

## 7. Subir el proyecto a GitHub

### Desde tu PC

```bash
cd ruta/a/curso-ia-telegram
git init
git add .
git commit -m "Proyecto curso IA Telegram"
```

Crea repo vacío en GitHub y sube:

```bash
git remote add origin https://github.com/TU_USUARIO/curso-ia-telegram.git
git branch -M main
git push -u origin main
```

> **Nunca subas `.env`** (tokens secretos). Está en `.gitignore`.

### Alternativa sin GitHub

```bash
scp -r ./curso-ia-telegram TU_USUARIO@IP_SERVIDOR_8GB:~/
```

---

## 8. Clonar y configurar .env

### 8.1 Clonar en el servidor

```bash
cd ~
git clone https://github.com/TU_USUARIO/curso-ia-telegram.git
cd curso-ia-telegram
```

### 8.2 Crear `.env`

```bash
cp .env.example .env
nano .env
```

### 8.3 Variables obligatorias

```env
BOT_ALUMNOS_TOKEN=TOKEN_BOT_ALUMNOS
BOT_ADMIN_TOKEN=TOKEN_BOT_ADMIN
BOT_SOPORTE_TOKEN=TOKEN_BOT_SOPORTE
ADMIN_TELEGRAM_IDS=TU_TELEGRAM_ID

POSTGRES_PASSWORD=contraseña_segura_larga
```

### 8.4 Variables recomendadas (8 GB RAM — equilibrio velocidad/precisión)

```env
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_EMBED_MODEL=nomic-embed-text
SIMILARITY_CACHE_THRESHOLD=0.87
CACHE_LOOKUP_LIMIT=300
```

| Variable | Qué hace |
|----------|----------|
| `OLLAMA_MODEL` | Modelo de chat (`3b` = más preciso; `1.5b` = más rápido) |
| `SIMILARITY_CACHE_THRESHOLD` | Similitud mínima para reutilizar respuesta cacheada |
| `CACHE_LOOKUP_LIMIT` | Máx. entradas de caché consultadas (menor = más rápido) |

Guardar en nano: `Ctrl+O` Enter · Salir: `Ctrl+X`.

---

## 9. Material del curso y bibliografía

### 9.1 Subir apuntes

Coloca PDF, MD o TXT en `data/curso/`:

```bash
# Desde tu PC:
scp -r ./apuntes/* TU_USUARIO@IP_SERVIDOR:~/curso-ia-telegram/data/curso/
```

Comprobar:

```bash
ls -la ~/curso-ia-telegram/data/curso/
```

### 9.2 Catálogo bibliográfico (`/bibliografia`)

Edita `data/curso/bibliografia.json`:

```bash
nano ~/curso-ia-telegram/data/curso/bibliografia.json
```

Ejemplo:

```json
{
  "documentos": [
    {
      "archivo": "tema1.pdf",
      "titulo": "Tema 1 — Introducción",
      "descripcion": "Conceptos básicos y objetivos del módulo 1."
    },
    {
      "archivo": "tema2.md",
      "titulo": "Tema 2 — Desarrollo",
      "descripcion": "Contenido ampliado con ejercicios resueltos."
    }
  ]
}
```

- El campo `archivo` debe coincidir **exactamente** con el nombre del fichero en `data/curso/`.
- Si un archivo no está en el JSON, se listará igualmente con nombre automático.
- Los alumnos pueden **recibir por Telegram** archivos de hasta **20 MB**.

### 9.3 Preguntas test (opcional)

```bash
nano data/tests/preguntas_test.json
```

---

## 10. Arrancar Docker

```bash
cd ~/curso-ia-telegram
docker compose up -d --build
```

Comprobar (1–2 min la primera vez):

```bash
docker compose ps
```

Servicios esperados: `postgres`, `ollama`, `chromadb`, `rag-api`, `bot-alumnos`, `bot-admin`, `bot-soporte`.

Logs:

```bash
docker compose logs -f
docker compose logs -f rag-api
```

Health check:

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

---

## 11. Descargar modelos de IA

```bash
chmod +x scripts/pull_models.sh scripts/ingest.sh
bash scripts/pull_models.sh
```

Manual:

```bash
docker compose exec ollama ollama pull qwen2.5:3b
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama list
```

Prueba rápida:

```bash
docker compose exec ollama ollama run qwen2.5:3b "Responde en una frase: ¿qué es un bot?"
```

> Descarga inicial: 10–30 min según conexión. Modelo `3b` ≈ 2 GB.

---

## 12. Indexar documentos (ingesta RAG)

Necesario para que la **IA responda preguntas** citando el temario.

### Opción A — Comando directo (recomendado)

```bash
docker compose exec -T rag-api python /app/scripts/ingest_docs.py
```

### Opción B — Script

```bash
chmod +x scripts/ingest.sh
bash scripts/ingest.sh
```

> Si el script falla con `ingest_docs.py\r`, es un problema de finales de línea Windows. Usa la **opción A** o ejecuta en el servidor:
> ```bash
> sed -i 's/\r$//' scripts/*.sh
> ```

Salida esperada:

```
✅ Ingesta completada: N fragmentos en 'curso_docs'
```

**Repetir** cada vez que añadas o modifiques apuntes en `data/curso/`.

> `/bibliografia` **no** requiere ingesta; lee los archivos directamente.

---

## 13. Verificaciones técnicas

```bash
# Contenedores
docker compose ps

# Recursos
docker stats --no-stream
free -h
df -h

# RAG
curl -X POST http://localhost:8080/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"¿Qué debe hacer un alumno tras registrarse?"}'

# Base de datos
docker compose exec postgres psql -U curso -d curso_ia -c "\dt"
```

---

## 14. Pruebas en Telegram

### Checklist

- [ ] **Bot admin** → `/start` → panel (sin "Sin permisos")
- [ ] **Bot alumnos** → `/start` → registro nombre/apellidos
- [ ] **Bot admin** → notificación con ✅ Aceptar / ❌ Rechazar
- [ ] Aceptar → alumno recibe bienvenida
- [ ] Alumno → pregunta del temario → respuesta **con fuentes**
- [ ] Repetir pregunta → **⚡ Respuesta rápida** (caché)
- [ ] `/bibliografia` → listado → detalle → descarga (si ≤ 20 MB)
- [ ] `/test` → bloques de preguntas
- [ ] **Bot soporte** → incidencia → llega a admin
- [ ] **Bot admin** → `/resolver <id>` → respuesta → **usuario notificado en bot soporte**
- [ ] `/stats` y `/logs` funcionan

### Resolver un ticket (admin)

```
/soporte
→ Pulsa "✅ Resolver" en un ticket
→ Escribe: "Hemos corregido el error. Prueba de nuevo con /start."
→ El usuario recibe el mensaje en el bot de soporte
```

Alternativa:

```
/resolver 3
→ (escribes la respuesta en el siguiente mensaje)
```

Cerrar sin notificar:

```
/cerrar 3
```

---

## 15. Comandos de los bots

### Bot alumnos

| Comando | Descripción |
|---------|-------------|
| `/start` | Registro o estado |
| `/help` | Ayuda |
| `/bibliografia` | Listado y consulta de documentos del temario |
| `/test` | Exámenes tipo test resueltos |
| Texto libre | Pregunta al temario (solo autorizados) |

### Bot admin

| Comando | Descripción |
|---------|-------------|
| `/start`, `/help` | Panel y ayuda |
| `/pendientes` | Usuarios por autorizar |
| `/usuarios`, `/usuario <id>` | Consulta de usuarios |
| `/autorizar <tg_id>`, `/rechazar <tg_id>` | Gestión de acceso |
| `/stats`, `/logs` | Monitorización |
| `/soporte` | Tickets abiertos |
| `/ticket <id>` | Detalle de ticket |
| `/resolver <id>` | Resolver y notificar al usuario |
| `/cerrar <id>` | Cerrar sin notificar |
| `/cancelar` | Cancelar resolución en curso |

### Bot soporte

| Comando | Descripción |
|---------|-------------|
| `/start` | Enviar mejora o incidencia |
| `/help` | Ayuda |
| `/cancelar` | Cancelar envío |

---

## 16. Servidor auxiliar de 4 GB (opcional)

Usa el servidor de **4 GB solo para Ollama** si quieres liberar RAM en el principal.

### En el servidor auxiliar (4 GB)

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# reconectar SSH

docker run -d --name ollama --restart unless-stopped \
  -v ollama_data:/root/.ollama \
  -p 11434:11434 \
  ollama/ollama

docker exec -it ollama ollama pull qwen2.5:3b
docker exec -it ollama ollama pull nomic-embed-text
```

Abre el puerto **11434** solo entre ambos servidores (firewall interno / red privada).

### En el servidor principal (8 GB)

Edita `.env`:

```env
OLLAMA_HOST=http://IP_SERVIDOR_4GB:11434
```

Comenta o elimina el servicio `ollama` en `docker-compose.yml` (opcional) y reinicia:

```bash
docker compose up -d --build
```

> El servidor principal ejecuta bots, BD, RAG y ChromaDB. El auxiliar solo genera embeddings y respuestas LLM.

---

## 17. Mantenimiento

```bash
cd ~/curso-ia-telegram

# Estado
docker compose ps
docker stats

# Reiniciar servicio
docker compose restart bot-alumnos

# Parar / arrancar
docker compose down
docker compose up -d

# Tras cambios de código
git pull
docker compose up -d --build

# Tras nuevos apuntes (IA)
bash scripts/ingest.sh

# Tras editar bibliografia.json (solo /bibliografia)
# No requiere reinicio
```

---

## 18. Backups

```bash
# Backup PostgreSQL
docker compose exec postgres pg_dump -U curso curso_ia > backup_$(date +%F).sql

# Copiar a tu PC
scp TU_USUARIO@IP:~/curso-ia-telegram/backup_*.sql ./

# Restaurar
cat backup.sql | docker compose exec -T postgres psql -U curso -d curso_ia
```

Backup automático diario (cron):

```bash
mkdir -p ~/backups
crontab -e
```

```
0 3 * * * cd /home/TU_USUARIO/curso-ia-telegram && docker compose exec -T postgres pg_dump -U curso curso_ia > /home/TU_USUARIO/backups/curso_$(date +\%F).sql
```

---

## 19. Solución de problemas

| Problema | Solución |
|----------|----------|
| Bot no responde | `docker compose logs -f bot-alumnos` · revisar token en `.env` |
| Admin "Sin permisos" | Corregir `ADMIN_TELEGRAM_IDS` · `docker compose restart bot-admin` |
| IA sin material | `bash scripts/ingest.sh` · comprobar `data/curso/` |
| Respuestas lentas | Normal en 1ª pregunta; 2ª igual debería usar caché |
| `/bibliografia` vacía | Añadir PDF/MD/TXT en `data/curso/` |
| Error `ingest_docs.py\r` | Finales de línea Windows: usar `docker compose exec -T rag-api python /app/scripts/ingest_docs.py` o `sed -i 's/\r$//' scripts/*.sh` |
| ChromaDB `KeyError: '_type'` | Versión cliente/servidor distinta. Ver apartado abajo |
| No llega notificación de ticket | Comprobar `BOT_SOPORTE_TOKEN` · usuario debe haber iniciado bot soporte alguna vez |
| Ollama sin memoria | Swap · modelo `qwen2.5:1.5b` · separar Ollama al servidor 4 GB |
| rag-api unhealthy | `docker compose logs rag-api` · esperar postgres · reiniciar |

### ChromaDB: `KeyError: '_type'`

Ocurre cuando la imagen Docker `chromadb/chroma:latest` no coincide con el cliente Python (`chromadb==0.5.23`).

```bash
cd ~/curso-ia-telegram
docker compose down
docker volume ls | grep chroma
# Elimina el volumen de chroma (nombre tipo curso-ia-telegram_chroma_data):
docker volume rm NOMBRE_DEL_VOLUMEN_CHROMA

docker compose pull chromadb
docker compose up -d --build
docker compose exec -T rag-api python /app/scripts/ingest_docs.py
```

El `docker-compose.yml` debe usar `chromadb/chroma:0.5.23` (no `latest`).

### Probar notificación de ticket manualmente

Tras `/resolver`, revisa logs:

```bash
docker compose logs -f bot-admin
```

### Reinstalar desde cero (⚠️ borra datos)

```bash
docker compose down -v
docker compose up -d --build
bash scripts/pull_models.sh
bash scripts/ingest.sh
```

---

## 20. Seguridad

- No subas `.env` a GitHub.
- No publiques tokens de BotFather.
- Usa contraseña fuerte en PostgreSQL.
- Si el repo es público, no subas PDFs con datos personales.
- Limita acceso SSH al servidor.
- Backups periódicos.

---

## 21. Referencia rápida

Instalación completa en servidor 8 GB:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 git curl nano
sudo usermod -aG docker $USER
# reconectar SSH

cd ~
git clone https://github.com/TU_USUARIO/curso-ia-telegram.git
cd curso-ia-telegram
cp .env.example .env
nano .env

docker compose up -d --build
chmod +x scripts/*.sh
bash scripts/pull_models.sh
bash scripts/ingest.sh

curl http://localhost:8080/health
docker compose ps
```

---

## 22. Checklist final

Antes de abrir a los alumnos:

- [ ] Servidor 8 GB preparado con Docker
- [ ] `.env` con 3 tokens + ADMIN_TELEGRAM_IDS + POSTGRES_PASSWORD
- [ ] Modelos `qwen2.5:3b` y `nomic-embed-text` descargados
- [ ] Apuntes reales en `data/curso/`
- [ ] `bibliografia.json` con títulos y descripciones
- [ ] Ingesta RAG completada
- [ ] Registro → autorización → pregunta → caché probados
- [ ] `/bibliografia` y descarga de archivo probados
- [ ] Ticket soporte → resolución → notificación probados
- [ ] Backup de prueba realizado
- [ ] Comandos `/help` en los 3 bots verificados

---

*Documento actualizado para Ubuntu 24.04 · servidor 8 GB + auxiliar 4 GB opcional · modelo qwen2.5:3b por defecto.*
