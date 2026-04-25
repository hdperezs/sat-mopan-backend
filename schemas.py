from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# ─── MEDICION ────────────────────────────────────────────────
class MedicionCreate(BaseModel):
    nivel_cm:        float
    voltaje_bateria: float
    codigo_estado:   int = 0
    dispositivo_id:  str = "SAT-MOPAN-01"

class MedicionOut(BaseModel):
    id:              int
    timestamp:       datetime
    nivel_cm:        float
    voltaje_bateria: float
    codigo_estado:   int
    dispositivo_id:  str

    class Config:
        from_attributes = True

# ─── ALERTA ──────────────────────────────────────────────────
class AlertaOut(BaseModel):
    id:                   int
    timestamp:            datetime
    nivel_activador:      float
    tipo_alerta:          str
    numeros_destinatarios: str
    texto_mensaje:        str
    estado_entrega:       str

    class Config:
        from_attributes = True

# ─── CONFIGURACION ───────────────────────────────────────────
class ConfiguracionOut(BaseModel):
    id:                int
    umbral_precaucion: float
    umbral_alerta:     float
    umbral_emergencia: float
    lista_numeros_sms: str

    class Config:
        from_attributes = True

class ConfiguracionUpdate(BaseModel):
    umbral_precaucion: Optional[float] = None
    umbral_alerta:     Optional[float] = None
    umbral_emergencia: Optional[float] = None
    lista_numeros_sms: Optional[str]   = None

# ─── AUTH ────────────────────────────────────────────────────
class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"

class UsuarioCreate(BaseModel):
    nombre:     str
    email:      EmailStr
    contrasena: str
