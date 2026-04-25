from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timedelta
from typing import List
import jwt
import bcrypt
import os

from database import get_db, engine, Base
from models import Medicion, Alerta, Usuario, Configuracion
from schemas import (
    MedicionCreate, MedicionOut,
    AlertaOut, ConfiguracionOut, ConfiguracionUpdate,
    TokenOut, UsuarioCreate
)

# ─── Configuración JWT ────────────────────────────────────────
SECRET_KEY         = os.getenv("SECRET_KEY", "sat-mopan-secret-2024")
ALGORITHM          = "HS256"
TOKEN_EXPIRE_HOURS = 8

# ─── App ──────────────────────────────────────────────────────
app = FastAPI(title="SAT Mopán API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Helpers Auth ─────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def crear_token(email: str) -> str:
    payload = {
        "sub": email,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_usuario_actual(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Usuario:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

    result = await db.execute(select(Usuario).where(Usuario.email == email))
    usuario = result.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return usuario

# ─── STARTUP ──────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ═════════════════════════════════════════════════════════════
#  ENDPOINTS PÚBLICOS — sin autenticación (Arduino puede usar)
# ═════════════════════════════════════════════════════════════

@app.get("/", tags=["Sistema"])
async def raiz():
    return {"sistema": "SAT Mopán", "estado": "operativo", "version": "1.0.0"}

@app.get("/salud", tags=["Sistema"])
async def salud():
    return {"ok": True}

# ── Recibir medición del Arduino (PÚBLICO - sin JWT) ──────────
@app.post("/medicion", status_code=201, tags=["Arduino"])
async def recibir_medicion(
    datos: MedicionCreate,
    db: AsyncSession = Depends(get_db)
):
    # Guardar medición
    nueva = Medicion(**datos.model_dump())
    db.add(nueva)
    await db.flush()

    # Leer umbrales actuales
    result = await db.execute(select(Configuracion).where(Configuracion.id == 1))
    config = result.scalar_one_or_none()

    # Generar alerta si supera un umbral
    if config and datos.nivel_cm != 999.0:
        tipo = None
        if datos.nivel_cm >= config.umbral_emergencia:
            tipo = "emergencia"
        elif datos.nivel_cm >= config.umbral_alerta:
            tipo = "alerta"
        elif datos.nivel_cm >= config.umbral_precaucion:
            tipo = "precaucion"

        if tipo:
            alerta = Alerta(
                nivel_activador=datos.nivel_cm,
                tipo_alerta=tipo,
                numeros_destinatarios=config.lista_numeros_sms,
                texto_mensaje=f"SAT MOPÁN [{tipo.upper()}]: Nivel {datos.nivel_cm} cm",
                estado_entrega="registrado"
            )
            db.add(alerta)

    await db.commit()
    return {"ok": True, "id": nueva.id, "nivel_cm": datos.nivel_cm}

# ── Nivel actual (PÚBLICO - para el tablero sin login) ────────
@app.get("/nivel-actual", response_model=MedicionOut, tags=["Público"])
async def nivel_actual(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Medicion).order_by(desc(Medicion.timestamp)).limit(1)
    )
    medicion = result.scalar_one_or_none()
    if not medicion:
        raise HTTPException(status_code=404, detail="Sin datos aún")
    return medicion

# ── Historial últimas N mediciones (PÚBLICO) ──────────────────
@app.get("/historial", response_model=List[MedicionOut], tags=["Público"])
async def historial(limite: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Medicion).order_by(desc(Medicion.timestamp)).limit(limite)
    )
    return result.scalars().all()

# ═════════════════════════════════════════════════════════════
#  ENDPOINTS PROTEGIDOS — requieren JWT (solo administrador)
# ═════════════════════════════════════════════════════════════

# ── Login ─────────────────────────────────────────────────────
@app.post("/auth/login", response_model=TokenOut, tags=["Auth"])
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Usuario).where(Usuario.email == form.username))
    usuario = result.scalar_one_or_none()

    if not usuario or not bcrypt.checkpw(
        form.password.encode(), usuario.hash_contrasena.encode()
    ):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    return {"access_token": crear_token(usuario.email), "token_type": "bearer"}

# ── Alertas (protegido) ───────────────────────────────────────
@app.get("/alertas", response_model=List[AlertaOut], tags=["Admin"])
async def listar_alertas(
    limite: int = 50,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual)
):
    result = await db.execute(
        select(Alerta).order_by(desc(Alerta.timestamp)).limit(limite)
    )
    return result.scalars().all()

# ── Configuración GET (protegido) ─────────────────────────────
@app.get("/configuracion", response_model=ConfiguracionOut, tags=["Admin"])
async def obtener_config(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual)
):
    result = await db.execute(select(Configuracion).where(Configuracion.id == 1))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Sin configuración")
    return config

# ── Configuración UPDATE (protegido) ──────────────────────────
@app.patch("/configuracion", response_model=ConfiguracionOut, tags=["Admin"])
async def actualizar_config(
    cambios: ConfiguracionUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual)
):
    result = await db.execute(select(Configuracion).where(Configuracion.id == 1))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Sin configuración")

    for campo, valor in cambios.model_dump(exclude_none=True).items():
        setattr(config, campo, valor)

    await db.commit()
    await db.refresh(config)
    return config

# ── Historial protegido (todas las mediciones) ────────────────
@app.get("/admin/mediciones", response_model=List[MedicionOut], tags=["Admin"])
async def todas_las_mediciones(
    limite: int = 500,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual)
):
    result = await db.execute(
        select(Medicion).order_by(desc(Medicion.timestamp)).limit(limite)
    )
    return result.scalars().all()
