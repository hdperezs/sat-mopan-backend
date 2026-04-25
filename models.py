from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from database import Base

class Medicion(Base):
    __tablename__ = "mediciones"

    id              = Column(Integer, primary_key=True, index=True)
    timestamp       = Column(DateTime(timezone=True), server_default=func.now())
    nivel_cm        = Column(Float, nullable=False)
    voltaje_bateria = Column(Float, nullable=False)
    codigo_estado   = Column(Integer, nullable=False, default=0)
    dispositivo_id  = Column(String(50), nullable=False, default="SAT-MOPAN-01")


class Alerta(Base):
    __tablename__ = "alertas"

    id                   = Column(Integer, primary_key=True, index=True)
    timestamp            = Column(DateTime(timezone=True), server_default=func.now())
    nivel_activador      = Column(Float, nullable=False)
    tipo_alerta          = Column(String(20), nullable=False)
    numeros_destinatarios = Column(Text, nullable=False)
    texto_mensaje        = Column(Text, nullable=False)
    estado_entrega       = Column(String(20), nullable=False, default="enviado")


class Usuario(Base):
    __tablename__ = "usuarios"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(100), nullable=False)
    email           = Column(String(150), nullable=False, unique=True)
    hash_contrasena = Column(Text, nullable=False)
    creado_en       = Column(DateTime(timezone=True), server_default=func.now())


class Configuracion(Base):
    __tablename__ = "configuracion"

    id                 = Column(Integer, primary_key=True, default=1)
    umbral_precaucion  = Column(Float, nullable=False, default=150.0)
    umbral_alerta      = Column(Float, nullable=False, default=250.0)
    umbral_emergencia  = Column(Float, nullable=False, default=350.0)
    lista_numeros_sms  = Column(Text, nullable=False, default='["+50239913010"]')
