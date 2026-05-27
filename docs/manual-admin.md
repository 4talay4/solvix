# Manual del administrador

## Comandos del bot admin

| Comando | Descripción |
|---------|-------------|
| `/start`, `/help` | Panel y ayuda |
| `/pendientes` | Usuarios por autorizar |
| `/usuarios`, `/usuario <id>` | Consultar usuarios |
| `/autorizar <tg_id>`, `/rechazar <tg_id>` | Gestión de acceso |
| `/stats`, `/logs` | Monitorización |
| `/soporte` | Tickets abiertos (con botones) |
| `/ticket <id>` | Detalle de un ticket |
| `/resolver <id>` | Resolver ticket y notificar al usuario |
| `/cerrar <id>` | Cerrar sin notificar |
| `/cancelar` | Cancelar resolución en curso |

## Resolver incidencias

1. `/soporte` → lista tickets abiertos.
2. Pulsa **✅ Resolver** o usa `/resolver 5`.
3. Escribe la respuesta que verá el usuario.
4. El usuario recibe notificación automática en el **bot de soporte**.

Si cierras con **🚫 Cerrar** o `/cerrar`, el usuario **no** recibe mensaje.

## Bibliografía del curso

Edita `data/curso/bibliografia.json` para títulos y descripciones:

```json
{
  "documentos": [
    {
      "archivo": "tema1.pdf",
      "titulo": "Tema 1 - Introducción",
      "descripcion": "Conceptos fundamentales del bloque 1."
    }
  ]
}
```

Tras añadir archivos: `bash scripts/ingest.sh` (para preguntas IA) — la bibliografía se lee al vuelo, no requiere ingesta.

## Añadir otro administrador

```env
ADMIN_TELEGRAM_IDS=111111111,222222222
```

```bash
docker compose restart bot-admin
```
