import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# ─── Constantes ───────────────────────────────────────────────
U_PREC  = 300.0   # cm
U_ALERT = 500.0   # cm
U_EMER  = 650.0   # cm

# ─── Extraer features de una ventana de mediciones ────────────
def extraer_features(mediciones: list) -> Optional[dict]:
    """
    Calcula las 6 características del modelo a partir de las
    últimas N mediciones, tal como describe el documento de tesis.
    """
    validas = [m for m in mediciones if m.nivel_cm < 900]
    if len(validas) < 4:
        return None

    niveles = [m.nivel_cm for m in validas]
    timestamps = [m.timestamp for m in validas]

    # 1. Nivel actual
    nivel_actual = niveles[-1]

    # 2. Tasa de cambio media entre las últimas 3 mediciones (cm/min)
    deltas = []
    for i in range(max(0, len(niveles)-3), len(niveles)-1):
        dt = (timestamps[i+1] - timestamps[i]).total_seconds() / 60
        if dt > 0:
            deltas.append((niveles[i+1] - niveles[i]) / dt)
    tasa_cambio = np.mean(deltas) if deltas else 0.0

    # 3. Aceleración (segunda derivada — ¿está subiendo más rápido?)
    aceleracion = 0.0
    if len(deltas) >= 2:
        aceleracion = deltas[-1] - deltas[-2]

    # 4. Nivel máximo de las últimas 6 lecturas
    nivel_max = max(niveles[-6:]) if len(niveles) >= 6 else max(niveles)

    # 5. Diferencia entre nivel actual y promedio de la ventana
    nivel_promedio = np.mean(niveles)
    diff_promedio = nivel_actual - nivel_promedio

    # 6. Voltaje batería (indicador ambiental)
    voltaje = validas[-1].voltaje_bateria if hasattr(validas[-1], 'voltaje_bateria') else 12.0

    return {
        "nivel_actual":   nivel_actual,
        "tasa_cambio":    round(tasa_cambio, 4),
        "aceleracion":    round(aceleracion, 4),
        "nivel_max":      nivel_max,
        "diff_promedio":  round(diff_promedio, 4),
        "voltaje":        voltaje,
    }


# ─── Motor de predicción Random Forest ────────────────────────
class ModeloRF:
    """
    Random Forest Regressor que se entrena con el historial
    de mediciones de Neon y predice el tiempo (minutos) hasta
    que el río alcanza el umbral de precaución.

    En etapa inicial (< 20 muestras válidas) usa reglas
    determinísticas basadas en las features extraídas.
    """

    def __init__(self):
        self.entrenado = False
        self.rf = None
        self.n_muestras = 0

    def entrenar(self, mediciones: list):
        """Construye el dataset y entrena el modelo."""
        validas = [m for m in mediciones if m.nivel_cm < 900]
        self.n_muestras = len(validas)

        if self.n_muestras < 20:
            self.entrenado = False
            return

        try:
            from sklearn.ensemble import RandomForestRegressor

            X, y = [], []
            ventana = 8

            for i in range(ventana, len(validas)):
                ventana_i = validas[i - ventana:i]
                features = extraer_features(ventana_i)
                if features is None:
                    continue

                # Calcular target: minutos hasta superar umbral
                # Buscamos hacia adelante cuándo se supera U_PREC
                target = None
                for j in range(i, min(i + 60, len(validas))):
                    if validas[j].nivel_cm >= U_PREC:
                        dt_min = (validas[j].timestamp - validas[i].timestamp).total_seconds() / 60
                        target = dt_min
                        break

                if target is None:
                    # Nunca superó el umbral en la ventana futura
                    # Estimamos con tasa lineal
                    tasa = features["tasa_cambio"]
                    if tasa > 0.01 and features["nivel_actual"] < U_PREC:
                        target = (U_PREC - features["nivel_actual"]) / tasa
                    else:
                        target = 9999  # Sin riesgo inminente

                X.append(list(features.values()))
                y.append(min(target, 9999))

            if len(X) < 10:
                self.entrenado = False
                return

            self.rf = RandomForestRegressor(
                n_estimators=100,
                max_depth=6,
                min_samples_leaf=2,
                random_state=42
            )
            self.rf.fit(X, y)
            self.entrenado = True

        except Exception:
            self.entrenado = False

    def predecir(self, features: dict) -> dict:
        """
        Devuelve la predicción completa del modelo.
        Si no está entrenado usa reglas determinísticas.
        """
        nivel    = features["nivel_actual"]
        tasa     = features["tasa_cambio"]
        acel     = features["aceleracion"]
        nivel_max = features["nivel_max"]

        # Clasificación de riesgo basada en múltiples features
        riesgo = self._clasificar_riesgo(nivel, tasa, acel, nivel_max)

        if self.entrenado and self.rf is not None:
            try:
                X = [list(features.values())]
                minutos_pred = float(self.rf.predict(X)[0])
                metodo = "Random Forest (scikit-learn)"
                importancias = dict(zip(
                    ["nivel_actual", "tasa_cambio", "aceleracion",
                     "nivel_max", "diff_promedio", "voltaje"],
                    [round(float(v), 4) for v in self.rf.feature_importances_]
                ))
            except Exception:
                minutos_pred = self._estimar_lineal(nivel, tasa)
                metodo = "Regresión lineal (fallback)"
                importancias = {}
        else:
            minutos_pred = self._estimar_lineal(nivel, tasa)
            metodo = f"Regresión lineal (acumulando datos: {self.n_muestras}/20)"
            importancias = {}

        return {
            "nivel_actual_m":      round(nivel / 100, 2),
            "tasa_cambio_cm_min":  round(tasa, 3),
            "aceleracion":         round(acel, 4),
            "nivel_max_m":         round(nivel_max / 100, 2),
            "riesgo":              riesgo["nivel"],
            "riesgo_score":        riesgo["score"],
            "minutos_a_precaucion": None if minutos_pred >= 9999 else round(minutos_pred),
            "metodo":              metodo,
            "modelo_entrenado":    self.entrenado,
            "n_muestras":          self.n_muestras,
            "importancia_features": importancias,
            "interpretacion":      self._interpretar(nivel, tasa, acel, riesgo, minutos_pred),
        }

    def _clasificar_riesgo(self, nivel, tasa, acel, nivel_max) -> dict:
        """
        Clasificación multi-variable del riesgo — esto es lo que
        diferencia al modelo de un simple umbral fijo.
        """
        score = 0

        # Factor 1: Nivel actual
        if nivel >= U_EMER:   score += 40
        elif nivel >= U_ALERT: score += 30
        elif nivel >= U_PREC:  score += 20
        else:
            score += int((nivel / U_PREC) * 10)

        # Factor 2: Tasa de cambio
        if tasa > 5:    score += 25
        elif tasa > 2:  score += 15
        elif tasa > 0.5: score += 8
        elif tasa > 0:  score += 3
        elif tasa < -2: score -= 10  # Bajando rápido = riesgo menor

        # Factor 3: Aceleración (subida acelerada = más peligroso)
        if acel > 1:   score += 15
        elif acel > 0.5: score += 8
        elif acel > 0:  score += 3

        # Factor 4: Nivel máximo reciente
        if nivel_max >= U_EMER:   score += 20
        elif nivel_max >= U_ALERT: score += 10
        elif nivel_max >= U_PREC:  score += 5

        score = max(0, min(100, score))

        if score >= 70:   nivel_riesgo = "CRÍTICO"
        elif score >= 50: nivel_riesgo = "ALTO"
        elif score >= 30: nivel_riesgo = "MEDIO"
        elif score >= 10: nivel_riesgo = "BAJO"
        else:             nivel_riesgo = "MÍNIMO"

        return {"nivel": nivel_riesgo, "score": score}

    def _estimar_lineal(self, nivel, tasa) -> float:
    # Si ya superó precaución, calcula tiempo a emergencia
    if nivel >= U_PREC and tasa > 0.01 and nivel < U_EMER:
        return (U_EMER - nivel) / tasa
    # Si aún no llega a precaución, calcula tiempo a precaución
    if tasa > 0.01 and nivel < U_PREC:
        return (U_PREC - nivel) / tasa
    return 9999

    def _interpretar(self, nivel, tasa, acel, riesgo, minutos) -> str:
        nM = round(nivel / 100, 2)
        if nivel >= U_EMER:
            return f"EMERGENCIA ACTIVA. Río en {nM}m — desbordamiento inminente o en curso."
        elif nivel >= U_ALERT:
            return f"Nivel en zona de alerta ({nM}m). Tasa: {round(tasa,2)} cm/min. Activar protocolo de evacuación."
        elif nivel >= U_PREC:
            return f"Nivel en precaución ({nM}m). Monitoreo intensivo requerido."
        elif tasa > 0.5 and minutos < 9999:
            return f"Nivel normal pero subiendo a {round(tasa,2)} cm/min. Riesgo score: {riesgo['score']}/100. Estimado a precaución: {round(minutos)} min."
        elif tasa < -0.5:
            return f"Nivel bajando ({round(tasa,2)} cm/min). Situación mejorando. Riesgo: {riesgo['nivel']}."
        else:
            return f"Nivel estable en {nM}m. Riesgo: {riesgo['nivel']} (score: {riesgo['score']}/100)."


# Instancia global del modelo
modelo_rf = ModeloRF()
