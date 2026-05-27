# Material del curso

Coloca aquí los documentos que alimentarán al asistente de IA:

- **PDF** — apuntes, diapositivas exportadas
- **Markdown (.md)** — temarios estructurados por apartados
- **Texto (.txt)** — contenido plano

### Catálogo para `/bibliografia`

Edita `bibliografia.json` en esta misma carpeta para definir título y descripción de cada archivo:

```json
{
  "documentos": [
    {
      "archivo": "mi-tema.pdf",
      "titulo": "Tema 3 - Redes",
      "descripcion": "Apuntes del bloque de redes del curso."
    }
  ]
}
```

Los alumnos consultan el listado con `/bibliografia` y pueden recibir archivos ≤ 20 MB por Telegram.

Después de añadir o modificar archivos para la **IA**, ejecuta la ingesta (ver `GUIA_DESPLIEGUE_COMPLETA.md`).

No subas a GitHub material con copyright o datos personales si el repositorio es público.
