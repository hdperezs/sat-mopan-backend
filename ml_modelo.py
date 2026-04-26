import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# Constantes
U_PREC  = 300.0
U_ALERT = 500.0
U_EMER  = 650.0


def extraer_features(mediciones: list) -> Optional[dict]:
    validas = [m for m in mediciones if m.nivel_cm < 900]
    if len(validas) < 4:
        return None

    niveles    = [m.nivel_cm for m in validas]
    timestamps = [m.timestamp for m in validas]

    nivel_actual = niveles[-1]

    deltas = []
    for i in range(max(0, len(niveles)-3), len(niveles)-1):
        dt = (timestamps[i+1] - timestamps[i]).total_seconds() / 60
        if dt > 0:
            deltas.append((niveles[i+1] - niveles[i]) / dt)
    tasa_cambio = np.mean(deltas) if deltas else 0.0

    aceleracion = 0.0
    if len(deltas) >= 2:
        aceleracion = deltas[-1] - deltas[-2]

    nivel_max    = max(niveles[-6:]) if len(niveles) >= 6 else max(niveles)
    nivel_promedio = np.mean(niveles)
    diff_promedio  = nivel_actual - nivel_promedio
    voltaje        = validas[-1].voltaje_bateria if hasattr(validas[-1], 'voltaje_bateria') else 12.0

    return {
        "nivel_actual":  nivel_actual,
        "tasa_cambio":   round(tasa_cambio, 4),
        "aceleracion":   round(aceleracion, 4),
        "nivel_max":     nivel_max,
        "diff_promedio": round(diff_promedio, 4),
        "voltaje":       voltaje,
    }


class ModeloRF:

    def __init__(self):
        self.entrenado  = False
        self.rf         = None
        self.n_muestras = 0

    def entrenar(self, mediciones: list):
        validas         = [m for m in mediciones if m.nivel_cm < 900]
        self.n_muestras = len(validas)

        if self.n_muestras < 20:
            self.entrenado = False
            return

        try:
            from sklearn.ensemble import RandomForestRegressor

            X, y    = [], []
            ventana = 8

            for i in range(ventana, len(validas)):
                ventana_i = validas[i - ventana:i]
                features  = extraer_features(ventana_i)
                if features is None:
                    continue

                target = None
                for j in range(i, min(i + 60, len(validas))):
                    if validas[j].nivel_cm >= U_PREC:
                        dt_min = (validas[j].timestamp - validas[i].timestamp).total_seconds() / 60
                        target = dt_min
                        break

                if target is None:
                    tasa = features["tasa_cambio"]
                    if tasa > 0.01 and features["nivel_actual"] < U_PREC:
                        target = (U_PREC - features["nivel_actual"]) / tasa
                    else:
                        target = 9999

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
        nivel     = features["nivel_actual"]
        tasa      = features["tasa_cambio"]
        acel      = features["aceleracion"]
        nivel_max = features["nivel_max"]

        riesgo = self._clasificar_riesgo(nivel, tasa, acel, nivel_max)

        if self.entrenado and self.rf is not None:
            try:
                X             = [list(features.values())]
                minutos_pred  = float(self.rf.predict(X)[0])
                metodo        = "Random Forest (scikit-learn)"
                importancias  = dict(zip(
                    ["nivel_actual", "tasa_cambio", "aceleracion",
                     "nivel_max", "diff_promedio", "voltaje"],
                    [round(float(v), 4) for v in self.rf.feature_importances_]
                ))
            except Exception:
                minutos_pred = self._estimar_lineal(nivel, tasa)
                metodo       = "Regresion lineal (fallback)"
                importancias = {}
        else:
            minutos_pred = self._estimar_lineal(nivel, tasa)
            metodo       = f"Regresion lineal (acumulando datos: {self.n_muestras}/20)"
            importancias = {}

        return {
            "nivel_actual_m":       round(nivel / 100, 2),
            "tasa_cambio_cm_min":   round(tasa, 3),
            "aceleracion":          round(acel, 4),
            "nivel_max_m":          round(nivel_max / 100, 2),
            "riesgo":               riesgo["nivel"],
            "riesgo_score":         riesgo["score"],
            "minutos_a_precaucion": None if minutos_pred >= 9999 else round(minutos_pred),
            "umbral_objetivo":      "EMERGENCIA (6.5m)" if nivel >= U_PREC else "PRECAUCION (3.0m)",
            "metodo":               metodo,
            "modelo_entrenado":     self.entrenado,
            "n_muestras":           self.n_muestras,
            "importancia_features": importancias,
            "interpretacion":       self._interpretar(nivel, tasa, acel, riesgo, minutos_pred),
        }

    def _clasificar_riesgo(self, nivel, tasa, acel, nivel_max) -> dict:
        score = 0

        if nivel >= U_EMER:
            score += 40
        elif nivel >= U_ALERT:
            score += 30
        elif nivel >= U_PREC:
            score += 20
        else:
            score += int((nivel / U_PREC) * 10)

        if tasa > 5:
            score += 25
        elif tasa > 2:
            score += 15
        elif tasa > 0.5:
            score += 8
        elif tasa > 0:
            score += 3
        elif tasa < -2:
            score -= 10

        if acel > 1:
            score += 15
        elif acel > 0.5:
            score += 8
        elif acel > 0:
            score += 3

        if nivel_max >= U_EMER:
            score += 20
        elif nivel_max >= U_ALERT:
            score += 10
        elif nivel_max >= U_PREC:
            score += 5

        score = max(0, min(100, score))

        if score >= 70:
            nivel_riesgo = "CRITICO"
        elif score >= 50:
            nivel_riesgo = "ALTO"
        elif score >= 30:
            nivel_riesgo = "MEDIO"
        elif score >= 10:
            nivel_riesgo = "BAJO"
        else:
            nivel_riesgo = "MINIMO"

        return {"nivel": nivel_riesgo, "score": score}

    def _estimar_lineal(self, nivel, tasa) -> float:
        if nivel >= U_PREC and tasa > 0.01 and nivel < U_EMER:
            return (U_EMER - nivel) / tasa
        if tasa > 0.01 and nivel < U_PREC:
            return (U_PREC - nivel) / tasa
        return 9999

    def _interpretar(self, nivel, tasa, acel, riesgo, minutos) -> str:
        nM = round(nivel / 100, 2)
        if nivel >= U_EMER:
            return f"EMERGENCIA ACTIVA. Rio en {nM}m — desbordamiento inminente o en curso."
        elif nivel >= U_ALERT:
            mins = round(minutos) if minutos < 9999 else None
            eta  = f" Estimado a emergencia: {mins} min." if mins else ""
            return f"Nivel en zona de alerta ({nM}m). Tasa: {round(tasa,2)} cm/min.{eta} Activar protocolo de evacuacion."
        elif nivel >= U_PREC:
            mins = round(minutos) if minutos < 9999 else None
            eta  = f" Estimado a emergencia: {mins} min." if mins else ""
            return f"Nivel en precaucion ({nM}m). Monitoreo intensivo requerido.{eta}"
        elif tasa > 0.5 and minutos < 9999:
            return f"Nivel normal pero subiendo a {round(tasa,2)} cm/min. Riesgo score: {riesgo['score']}/100. Estimado a precaucion: {round(minutos)} min."
        elif tasa < -0.5:
            return f"Nivel bajando ({round(tasa,2)} cm/min). Situacion mejorando. Riesgo: {riesgo['nivel']}."
        else:
            return f"Nivel estable en {nM}m. Riesgo: {riesgo['nivel']} (score: {riesgo['score']}/100)."


modelo_rf = ModeloRF()
