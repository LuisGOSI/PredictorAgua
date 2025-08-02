from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

OPENWEATHER_API_KEY = "a2e8faa7f559a15ac820c4c0ec354645"

@app.get("/predict")
def predict(date: str):
    weather = get_weather_forecast(date)
    temp = weather["temp"]

    docs = db.collection("consumo_diario").stream()
    history = []
    for doc in docs:
        history.append(doc.to_dict())

    if not history:
        raise ValueError("No hay datos históricos en Firestore.")

    el_dorado_total = []
    manzanares_total = []
    el_dorado_poblacion = []
    manzanares_poblacion = []

    for h in history:
        el_dorado_total.append(h["El_dorado"]["total_litros"])
        manzanares_total.append(h["Manzanares"]["total_litros"])
        el_dorado_poblacion.append(h["El_dorado"]["poblacion"])
        manzanares_poblacion.append(h["Manzanares"]["poblacion"])

    avg_dorado = sum(el_dorado_total) / len(el_dorado_total)
    avg_manzanares = sum(manzanares_total) / len(manzanares_total)

    pop_dorado = sum(el_dorado_poblacion) / len(el_dorado_poblacion)
    pop_manzanares = sum(manzanares_poblacion) / len(manzanares_poblacion)

    factor = 1 + (temp - 25) * 0.02

    pred_dorado = avg_dorado * factor * (pop_dorado / pop_dorado)  # la población es base
    pred_manzanares = avg_manzanares * factor * (pop_manzanares / pop_manzanares)

    def check_alert(pred, avg):
        f = pred / avg
        if f > 1.1:
            return "ALTO CONSUMO"
        elif f < 0.9:
            return "BAJO CONSUMO"
        else:
            return "NORMAL"

    alert_dorado = check_alert(pred_dorado, avg_dorado)
    alert_manzanares = check_alert(pred_manzanares, avg_manzanares)

    return {
        "fecha": date,
        "temp_predecida": temp,
        "El_dorado": {
            "consumo_predecido": round(pred_dorado, 2),
            "alerta": alert_dorado,
            "poblacion": int(pop_dorado)
        },
        "Manzanares": {
            "consumo_predecido": round(pred_manzanares, 2),
            "alerta": alert_manzanares,
            "poblacion": int(pop_manzanares)
        }
    }

def get_weather_forecast(target_date: str):
    #lat, lon = 21.12, -101.68  # León
    lat, lon = 33.4484, -112.0740 # Arizona
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
    r = requests.get(url)
    data = r.json()

    if "list" not in data:
        raise ValueError(f"Error en OpenWeather: {data}")

    target = datetime.strptime(target_date, "%Y-%m-%d")

    closest = min(
        data["list"],
        key=lambda x: abs(
            datetime.fromtimestamp(x["dt"]).date() - target.date()
        )
    )

    temp = closest["main"]["temp"]
    print("Temperatura más cercana a", target_date, ":", temp)
    return {"temp": temp}


@app.get("/consumo_diario")
def consumo_diario():
    docs = db.collection("consumo_diario").stream()
    resultados = []
    for doc in docs:
        data = doc.to_dict()
        resultados.append({
            "date": data.get("date"),
            "El_dorado": data.get("El_dorado", {}).get("total_litros", 0),
            "Manzanares": data.get("Manzanares", {}).get("total_litros", 0)
        })
    resultados.sort(key=lambda x: x["date"])
    return resultados

@app.get("/temp_vs_consumo")
def temp_vs_consumo():
    docs = db.collection("consumo_diario").stream()
    resultados = []
    for doc in docs:
        data = doc.to_dict()
        total_litros = (
            data.get("El_dorado", {}).get("total_litros", 0)
            + data.get("Manzanares", {}).get("total_litros", 0)
        )
        resultados.append({
            "date": data.get("date"),
            "temperatura": data.get("temperatura", 0),
            "consumo_total": total_litros
        })
    resultados.sort(key=lambda x: x["date"])
    return resultados


@app.get("/participacion_vecindario")
def participacion_vecindario():
    docs = db.collection("consumo_diario").stream()
    total_dorado = 0
    total_manzanares = 0

    for doc in docs:
        data = doc.to_dict()
        total_dorado += data.get("El_dorado", {}).get("total_litros", 0)
        total_manzanares += data.get("Manzanares", {}).get("total_litros", 0)

    total_general = total_dorado + total_manzanares

    if total_general == 0:
        return {"error": "No hay datos suficientes."}

    participacion = {
        "El_dorado": round((total_dorado / total_general) * 100, 2),
        "Manzanares": round((total_manzanares / total_general) * 100, 2),
        "total_litros": total_general
    }

    return participacion
