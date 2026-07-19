# Custom mode

Custom es una configuración autogestionada. El repositorio no proporciona claves, créditos ni una
garantía sobre la disponibilidad o gratuidad de modelos externos.

## Configuración mínima

1. Copia `.env.custom.example` como `.env.custom`.
2. Configura `OPENROUTER_API_KEY` y los modelos compatibles con tu cuenta.
3. Ejecuta:

```bash
docker compose -f compose.yaml -f compose.custom.yaml up --build
```

La API key permanece en el contenedor FastAPI. No la copies a `apps/web/.env.local`, no uses
`NEXT_PUBLIC_` y no la envíes a Git.

## Capacidades por proveedor

| Función | Configuración |
|---|---|
| Transcripción individual | OpenRouter u OpenAI |
| Evaluación estructurada | OpenRouter; Gemini puede actuar como juez principal |
| Compañero de IA | OpenRouter u OpenAI compatible |
| Dos candidatos | OpenAI diarization o WhisperX local |
| Almacenamiento | Local por defecto; Supabase opcional |

Los modelos gratuitos pueden desaparecer, cambiar límites o no admitir JSON Schema. Mantén al
menos un modelo alternativo y revisa las condiciones del proveedor antes de procesar audio de
terceros.

## WhisperX local

WhisperX evita pagar una API de diarización, pero no es ligero: requiere PyTorch, modelos de
Hugging Face/pyannote y normalmente una GPU compatible. Se instala en un entorno aislado
`.whisperx-venv` y nunca se incorpora a la imagen Offline básica.

Configura:

```dotenv
DIARIZATION_PROVIDER=whisperx
WHISPERX_PYTHON_PATH=.whisperx-venv/Scripts/python.exe
WHISPERX_BRIDGE_PATH=apps/api/scripts/whisperx_diarize.py
WHISPERX_MODEL=large-v3-turbo
WHISPERX_DEVICE=cuda
WHISPERX_COMPUTE_TYPE=float16
```

En Linux adapta `WHISPERX_PYTHON_PATH`. Los modelos de pyannote pueden requerir aceptar sus
condiciones y proporcionar un token de Hugging Face únicamente en el entorno local.

## Antes de exponerlo a Internet

- Cambia `SESSION_TOKEN_PEPPER` y `UPLOAD_SIGNING_SECRET` por valores aleatorios de 32 caracteres
  o más.
- Usa `ENVIRONMENT=production`, HTTPS y una lista cerrada en `CORS_ALLOWED_ORIGINS` y
  `TRUSTED_HOSTS`.
- Sustituye SQLite por Postgres cuando ejecutes varias réplicas.
- Añade límites de tráfico delante de los endpoints costosos.
- Configura una política de privacidad acorde con los proveedores y usuarios reales.
