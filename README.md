# A.S.A.P. Backend

A.S.A.P. (Apnea Sleep Analytics Platform) es el backend de analitica para apnea del sueno. Expone APIs para analisis, captacion de leads (waitlist con doble opt-in) y autenticacion con JWT.

## Arquitectura General

1. La app movil o la landing envia datos al backend en formato JSON.
2. FastAPI valida payloads con Pydantic.
3. SQLAlchemy maneja persistencia en SQLite o PostgreSQL.
4. Alembic versiona cambios de esquema.
5. El backend responde datos normalizados para UI.

## Endpoints Principales

Analisis:

- `POST /analyze`

Waitlist:

- `POST /api/leads`
- `POST /api/leads/resend-confirmation`
- `GET /api/leads/confirm?token=...`
- `GET /api/leads?limit=20`

Autenticacion:

- `POST /api/auth/registro`
- `POST /api/auth/login`
- `GET /api/auth/perfil` (requiere `Authorization: Bearer <token>`)

Dashboard:

- `GET /api/dashboard/resumen` (requiere `Authorization: Bearer <token>`)

Sueño (MVP):

- `POST /api/sleep/calibracion`
- `POST /api/sleep/sesiones/iniciar` (Bearer)
- `POST /api/sleep/sesiones/{session_id}/fragmento` (Bearer, multipart UploadFile)
- `POST /api/sleep/sesiones/{session_id}/finalizar` (Bearer)
- `GET /api/sleep/sesiones?limit=20` (Bearer)

### Pipeline de Analisis de Fragmentos

Al cerrar una sesion (`/finalizar`), el backend ejecuta:

1. Consolidacion de archivos temporales por `session_id`.
2. Pre-procesamiento DSP con `librosa`:
  - normalizacion,
  - eliminacion de silencio,
  - extraccion MFCC (20 coeficientes).
3. Inferencia por ventanas de tiempo:
  - modelo Scikit-Learn si existe (`ML_SLEEP_MODEL_PATH`),
  - fallback heuristico por amplitud dB si el modelo no esta entrenado.
4. Scoring final basado en duracion y penalizacion por apnea/ronquido.
5. Persistencia de eventos y confianza en `sleep_detection_logs`.
6. Limpieza de fragmentos temporales en disco tras guardar resultados.

Nota:
El log de confianza permite trazabilidad de inferencia y prepara el camino para futuros ciclos de feedback del usuario para re-entrenamiento.

Ejemplo de registro:

```json
{
  "nombre_completo": "Alejandro",
  "email": "alejandro@example.com",
  "password": "ClaveSegura123"
}
```

Ejemplo de lead:

```json
{
  "name": "Alejandro",
  "email": "alejandro@example.com",
  "device": "ios",
  "source": "landing-page"
}
```

## Base De Datos

Stack de persistencia:

- ORM: `SQLAlchemy 2.x`
- Migraciones: `Alembic`
- Principal para todos los entornos: `PostgreSQL` (Neon compatible)
- Fallback secundario opcional en local: `SQLite` (`sqlite:///./asap.db`)

URL ejemplo para Neon:

```bash
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>/<database>?sslmode=require
```

Importante:
El backend carga automaticamente variables desde `.env` (via `python-dotenv`).
`DATABASE_URL` debe apuntar a Neon/PostgreSQL en entornos reales.

### Como Trabajar La Base De Datos

1. Desarrollo local / staging / producción:
  Configura `DATABASE_URL` apuntando a Neon/PostgreSQL.
2. Desarrollo local alterno (opcional):
  Usa `SQLITE_DATABASE_URL` solo como fallback temporal.
3. Migraciones:
	Ejecuta `alembic upgrade head` en cada despliegue.

### Verificar Que Estas En Neon

Con el entorno activo, ejecuta:

```bash
python -c "from app.core.config import settings; print(settings.database_url)"
```

Si ves una URL `postgresql+psycopg://...neon...`, estas conectado a Neon.

Despues aplica migraciones:

```bash
alembic upgrade head
```

Nota:
`AUTO_CREATE_TABLES=true` ayuda en desarrollo local. Para entornos serios, manten `AUTO_CREATE_TABLES=false` y usa Alembic como fuente de verdad del esquema.

## Flujo Doble Opt-In (Waitlist)

1. Usuario envia formulario (`POST /api/leads`).
2. Backend genera token de confirmacion y envia email.
3. Usuario confirma en `GET /api/leads/confirm?token=...`.
4. Lead cambia de `pending` a `confirmed`.

Si SMTP no esta configurado, la API devuelve `confirmation_url_preview` para pruebas locales.

## Flujo MVP De Monitoreo

1. Registro/Login con onboarding breve de sueño y consentimiento legal.
2. Calibracion de microfono por nivel de ruido ambiente.
3. Inicio de sesion nocturna (`/api/sleep/sesiones/iniciar`).
4. Finalizacion de sesion y score inmediato (`/api/sleep/sesiones/{id}/finalizar`).
5. Dashboard con 3 indicadores: Sleep Score, eventos apnea/ronquido y continuidad nocturna.

## SMTP En Produccion

`SMTP_PROVIDER` soporta:

- `resend`
- `sendgrid`
- `gmail`
- `custom`

Toma `.env.example` como base.

### Resend

```bash
SMTP_PROVIDER=resend
SMTP_PASSWORD=re_xxxxxxxxxxxxxxxxx
SMTP_FROM_EMAIL=no-reply@tu-dominio.com
```

### SendGrid

```bash
SMTP_PROVIDER=sendgrid
SMTP_PASSWORD=SG.xxxxxxxxxxxxxxxxx
SMTP_FROM_EMAIL=no-reply@tu-dominio.com
```

### Gmail

```bash
SMTP_PROVIDER=gmail
SMTP_USERNAME=tu.cuenta@gmail.com
SMTP_PASSWORD=<app-password-gmail>
SMTP_FROM_EMAIL=tu.cuenta@gmail.com
```

Para SMTP personalizado, usa `SMTP_PROVIDER=custom` y define `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`.

## Desarrollo Local

Requisito recomendado de Python: `3.11` o `3.12` (scikit-learn 1.4.0 no está soportado en Python 3.14).

Instalar dependencias:

```bash
pip install -r requirements-dev.txt
```

Aplicar migraciones:

```bash
alembic upgrade head
```

Levantar API:

```bash
uvicorn main:app --reload
```

Ejecutar pruebas:

```bash
pytest -q
```

Variables importantes para entornos reales:

- `APP_ENV=production`
- `AUTH_SECRET_KEY` (obligatorio y robusto)
- `ADMIN_DATASET_EXPORT_KEY` (obligatorio y robusto)
- `CORS_ALLOWED_ORIGINS` (lista separada por comas)
- `SLEEP_FRAGMENT_ROOT`
- `MAX_SLEEP_FRAGMENT_SIZE_BYTES`

## Modelos ML v3 (audio + SpO2)

Artefactos requeridos en `ML_V3_MODEL_DIR`:

- `model_spo2_v3.joblib`
- `model_audio_v3.joblib`
- `scaler_spo2_v3.joblib`
- `scaler_audio_v3.joblib`
- `metadata_v3.json`

Descarga automática (si tienes una URL base donde están publicados):

1. Agrega en `.env`:

```bash
ML_V3_MODELS_BASE_URL=https://tu-origen-de-archivos/asap/v3
```

2. Ejecuta:

```bash
python scripts/download_ml_v3_models.py
```

Esto descargará los cinco archivos al directorio configurado en `ML_V3_MODEL_DIR`.
