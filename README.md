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
- `POST /api/sleep/sesiones/{session_id}/finalizar` (Bearer)
- `GET /api/sleep/sesiones?limit=20` (Bearer)

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
- Desarrollo rapido: `SQLite` (`sqlite:///./asap.db`)
- Recomendado para staging/produccion: `PostgreSQL` (Neon compatible)

URL ejemplo para Neon:

```bash
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>/<database>?sslmode=require
```

Importante:
El backend carga automaticamente variables desde `.env` (via `python-dotenv`).
Si no defines `DATABASE_URL`, se usara SQLite local.

### Como Trabajar La Base De Datos

1. Desarrollo local simple:
	Usa el fallback SQLite sin configurar nada extra.
2. Desarrollo local con PostgreSQL:
	Ejecuta `docker compose up --build`.
3. Staging/produccion:
	Configura `DATABASE_URL` apuntando a Neon/PostgreSQL.
4. Migraciones:
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
