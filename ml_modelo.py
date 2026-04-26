import numpy as np
from typing import Optional

# ─── Constantes ───────────────────────────────────────────────
# Umbrales de DISTANCIA en cm
# A MENOR distancia = MAYOR peligro
DIST_NORMAL     = 300.0  # Rio en estiaje normal
DIST_PRECAUCION = 200.0  # Rio subio ~1 metro
DIST_ALERTA     = 100.0  # Rio subio ~2 metros
DIST_EMERGENCIA =  50.0  # Agua casi al sensor


def extraer_features(mediciones: list) -> Optional[dict]:
    """
    Calcula las 6 características del modelo.
    nivel_cm aqui es la DISTANCIA al agua.
    A menor distancia = mayor peligro.
    """
    validas = [m for m in mediciones if m.nivel_cm < 900]
    if len(validas) < 4:
        return None

    distancias = [m.nivel_cm for m in validas]
    timestamps = [m.timestamp for m in validas]

    dist_actual = distancias[-1]

    # Tasa de cambio (negativa = distancia bajando = rio subiendo = peligro)
    deltas = []
    for i in range(max(0, len(distancias)-3), len(distancias)-1):
        dt = (timestamps[i+1] - timestamps[i]).total_seconds() / 60
        if dt > 0:
            deltas.append((distancias[i+1] - distancias[i]) / dt)
    tasa_cambio = np.mean(deltas) if deltas else 0.0

    # Aceleracion (negativa = rio subiendo cada vez mas rapido)
    aceleracion = 0.0
    if len(deltas) >= 2:
        aceleracion = deltas[-1] - deltas[-2]

    # Distancia minima reciente (la mas peligrosa)
    dist_min = min(distancias[-6:]) if len(distancias) >= 6 else min(distancias)

    # Diferencia con promedio
    dist_promedio = np.mean(distancias)
    diff_promedio = dist_actual - dist_promedio

    voltaje = validas[-1].voltaje_bateria if hasattr(validas[-1], 'voltaje_bateria') else 12.0

    return {
        "dist_actual":   dist_actual,
        "tasa_cambio":   round(tasa_cambio, 4),
        "aceleracion":   round(aceleracion, 4),
        "dist_min":      dist_min,
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

                # Target: minutos hasta que distancia baje de DIST_PRECAUCION
                target = None
                for j in range(i, min(i + 60, len(validas))):
                    if validas[j].nivel_cm <= DIST_PRECAUCION:
                        dt_min = (validas[j].timestamp - validas[i].timestamp).total_seconds() / 60
                        target = dt_min
                        break

                if target is None:
                    tasa = features["tasa_cambio"]
                    dist = features["dist_actual"]
                    if tasa < -0.01 and dist > DIST_PRECAUCION:
                        target = (dist - DIST_PRECAUCION) / abs(tasa)
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
        dist  = features["dist_actual"]
        tasa  = features["tasa_cambio"]
        acel  = features["aceleracion"]
        d_min = features["dist_min"]

        riesgo = self._clasificar_riesgo(dist, tasa, acel, d_min)

        if self.entrenado and self.rf is not None:
            try:
                X             = [list(features.values())]
                minutos_pred  = float(self.rf.predict(X)[0])
                metodo        = "Random Forest (scikit-learn)"
                importancias  = dict(zip(
                    ["dist_actual", "tasa_cambio", "aceleracion",
                     "dist_min", "diff_promedio", "voltaje"],
                    [round(float(v), 4) for v in self.rf.feature_importances_]
                ))
            except Exception:
                minutos_pred = self._estimar_lineal(dist, tasa)
                metodo       = "Regresion lineal (fallback)"
                importancias = {}
        else:
            minutos_pred = self._estimar_lineal(dist, tasa)
            metodo       = f"Regresion lineal (acumulando datos: {self.n_muestras}/20)"
            importancias = {}

        return {
            "dist_actual_cm":       round(dist, 1),
            "tasa_cambio_cm_min":   round(tasa, 3),
            "aceleracion":          round(acel, 4),
            "dist_min_cm":          round(d_min, 1),
            "riesgo":               riesgo["nivel"],
            "riesgo_score":         riesgo["score"],
            "minutos_a_precaucion": None if minutos_pred >= 9999 else round(minutos_pred),
            "umbral_objetivo":      "EMERGENCIA (<50cm)" if dist <= DIST_ALERTA else "PRECAUCION (<200cm)",
            "metodo":               metodo,
            "modelo_entrenado":     self.entrenado,
            "n_muestras":           self.n_muestras,
            "importancia_features": importancias,
            "interpretacion":       self._interpretar(dist, tasa, acel, riesgo, minutos_pred),
        }

    def _clasificar_riesgo(self, dist, tasa, acel, d_min) -> dict:
        score = 0

        # Factor 1: Distancia actual (menor = mas peligro)
        if dist <= DIST_EMERGENCIA:
            score += 40
        elif dist <= DIST_ALERTA:
            score += 30
        elif dist <= DIST_PRECAUCION:
            score += 20
        else:
            score += int(max(0, (DIST_NORMAL - dist) / DIST_NORMAL) * 10)

        # Factor 2: Tasa de cambio (negativa = rio subiendo = peligro)
        if tasa < -5:
            score += 25
        elif tasa < -2:
            score += 15
        elif tasa < -0.5:
            score += 8
        elif tasa < 0:
            score += 3
        elif tasa > 2:
            score -= 10  # Rio bajando rapido = menos peligro

        # Factor 3: Aceleracion (negativa = sube cada vez mas rapido)
        if acel < -1:
            score += 15
        elif acel < -0.5:
            score += 8
        elif acel < 0:
            score += 3

        # Factor 4: Distancia minima reciente
        if d_min <= DIST_EMERGENCIA:
            score += 20
        elif d_min <= DIST_ALERTA:
            score += 10
        elif d_min <= DIST_PRECAUCION:
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

    def _estimar_lineal(self, dist, tasa) -> float:
        # Rio subiendo (tasa negativa) y aun no llego a precaucion
        if tasa < -0.01 and dist > DIST_PRECAUCION:
            return (dist - DIST_PRECAUCION) / abs(tasa)
        # Ya en precaucion, estimar tiempo a emergencia
        if tasa < -0.01 and dist > DIST_EMERGENCIA:
            return (dist - DIST_EMERGENCIA) / abs(tasa)
        return 9999

    def _interpretar(self, dist, tasa, acel, riesgo, minutos) -> str:
        if dist <= DIST_EMERGENCIA:
            return f"EMERGENCIA ACTIVA. Agua a solo {dist:.0f}cm del sensor. Desbordamiento inminente."
        elif dist <= DIST_ALERTA:
            mins = round(minutos) if minutos < 9999 else None
            eta  = f" Estimado a emergencia: {mins} min." if mins else ""
            return f"Nivel en zona de alerta. Agua a {dist:.0f}cm. Tasa: {tasa:.2f} cm/min.{eta}"
        elif dist <= DIST_PRECAUCION:
            mins = round(minutos) if minutos < 9999 else None
            eta  = f" Estimado a alerta: {mins} min." if mins else ""
            return f"Precaucion. Agua a {dist:.0f}cm del sensor.{eta}"
        elif tasa < -0.5 and minutos < 9999:
            return f"Rio subiendo a {abs(tasa):.2f} cm/min. Agua a {dist:.0f}cm. Estimado a precaucion: {round(minutos)} min."
        elif tasa > 0.5:
            return f"Rio bajando ({tasa:.2f} cm/min). Distancia al agua: {dist:.0f}cm. Sin riesgo inmediato."
        else:
            return f"Nivel estable. Agua a {dist:.0f}cm del sensor. Riesgo: {riesgo['nivel']} (score: {riesgo['score']}/100)."


modelo_rf = ModeloRF()
