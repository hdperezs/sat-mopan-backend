# SAT Mopán — Backend FastAPI

## Archivos del proyecto
```
sat-backend/
├── main.py          ← API completa (endpoints Arduino + Admin)
├── database.py      ← Conexión a Neon PostgreSQL
├── models.py        ← Tablas SQLAlchemy
├── schemas.py       ← Validación Pydantic
├── requirements.txt ← Dependencias Python
└── Procfile         ← Comando de inicio para Railway
```

## Deploy en Railway (paso a paso)

### 1. Subir a GitHub
Crea un repositorio nuevo en GitHub y sube estos 6 archivos.

```bash
git init
git add .
git commit -m "SAT Mopan backend inicial"
git remote add origin https://github.com/TU_USUARIO/sat-mopan-backend.git
git push -u origin main
```

### 2. Crear servicio en Railway
1. Ve a https://railway.app
2. "New Project" → "Deploy from GitHub repo"
3. Selecciona tu repositorio
4. Railway detecta el Procfile automáticamente

### 3. Agregar variables de entorno en Railway
En tu servicio → pestaña "Variables" → agregar:



### 4. Verificar que funciona
Después del deploy, abre:
```
https://TU-APP.up.railway.app/
```
Debe responder:
```json
{"sistema": "SAT Mopán", "estado": "operativo", "version": "1.0.0"}
```

## Endpoints principales

| Método | Ruta | Auth | Usado por |
|--------|------|------|-----------|
| POST | `/medicion` | ❌ Libre | Arduino/SIM900 |
| GET | `/nivel-actual` | ❌ Libre | Tablero público |
| GET | `/historial` | ❌ Libre | Tablero público |
| POST | `/auth/login` | ❌ Libre | Admin login |
| GET | `/alertas` | ✅ JWT | Admin |
| GET | `/configuracion` | ✅ JWT | Admin |
| PATCH | `/configuracion` | ✅ JWT | Admin |
| GET | `/admin/mediciones` | ✅ JWT | Admin |

## Credenciales por defecto
- **Email:** admin@satmopan.gt
- **Contraseña:** admin123

## Documentación interactiva
```
https://TU-APP.up.railway.app/docs
```
