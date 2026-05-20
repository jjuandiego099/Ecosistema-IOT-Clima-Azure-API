"""
collector.py
============
Sistema IoT - Monitoreo Meteorológico Bucaramanga
Fuentes: Azure Maps Weather API (1 dispositivo real) + 9 Digital Twins

Escribe datos en InfluxDB cada 60 segundos.
Genera 7 días de histórico al arrancar (--backfill).

Uso:
    pip install influxdb-client requests numpy
    python collector.py                  # modo normal
    python collector.py --backfill       # genera 7 días de histórico primero
"""

import argparse
import json
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import requests
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ──────────────────────────────────────────────
# CONFIGURACIÓN GENERAL
# ──────────────────────────────────────────────

# Azure Maps Weather API
AZURE_KEY = ""
AZURE_URL = "https://atlas.microsoft.com/weather/currentConditions/json"

# Bucaramanga coordenadas (centro)
BUC_LAT = 7.1254
BUC_LON = -73.1198

# InfluxDB
INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "")
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "iot-buc")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "weather")

# Archivo de control (retroceso)
CONTROL_FILE = "control.json"

# Intervalo de muestreo en segundos
DEFAULT_INTERVAL = 60

# ──────────────────────────────────────────────
# DEFINICIÓN DE DISPOSITIVOS
# ──────────────────────────────────────────────

# offset_zona: diferencia típica de temperatura respecto al centro
# sigma: desviación estándar del ruido gaussiano
DEVICES = [
    {
        "id": "EST-BUC-API",
        "name": "Centro (Referencia API)",
        "type": "API_Real",
        "zona": "Centro",
        "offset_temp": 0.0,
        "offset_hum":  0.0,
        "offset_pres": 0.0,
        "sigma": 0.0,   # sin ruido, dato real
    },
    {
        "id": "DT-BUC-CAB",
        "name": "Cabecera",
        "type": "Digital_Twin",
        "zona": "Cabecera",
        "offset_temp":  1.2,
        "offset_hum":  -3.0,
        "offset_pres":  0.5,
        "sigma": 0.4,
    },
    {
        "id": "DT-BUC-LAG",
        "name": "Lagos del Cacique",
        "type": "Digital_Twin",
        "zona": "Lagos",
        "offset_temp":  0.5,
        "offset_hum":   5.0,
        "offset_pres": -0.3,
        "sigma": 0.5,
    },
    {
        "id": "DT-BUC-FLO",
        "name": "Floridablanca",
        "type": "Digital_Twin",
        "zona": "Floridablanca",
        "offset_temp": -1.5,
        "offset_hum":   8.0,
        "offset_pres":  2.1,
        "sigma": 0.6,
    },
    {
        "id": "DT-BUC-GIR",
        "name": "Girón",
        "type": "Digital_Twin",
        "zona": "Giron",
        "offset_temp":  2.8,
        "offset_hum":  -5.0,
        "offset_pres": -1.0,
        "sigma": 0.7,
    },
    {
        "id": "DT-BUC-PIE",
        "name": "Piedecuesta",
        "type": "Digital_Twin",
        "zona": "Piedecuesta",
        "offset_temp": -2.0,
        "offset_hum":   6.0,
        "offset_pres":  3.5,
        "sigma": 0.5,
    },
    {
        "id": "DT-BUC-NOR",
        "name": "Norte (UIS)",
        "type": "Digital_Twin",
        "zona": "Norte",
        "offset_temp":  0.8,
        "offset_hum":  -1.5,
        "offset_pres":  0.2,
        "sigma": 0.3,
    },
    {
        "id": "DT-BUC-ORI",
        "name": "Oriental",
        "type": "Digital_Twin",
        "zona": "Oriental",
        "offset_temp":  1.5,
        "offset_hum":   2.0,
        "offset_pres": -0.8,
        "sigma": 0.6,
    },
    {
        "id": "DT-BUC-MOV",
        "name": "Estación Móvil",
        "type": "Digital_Twin",
        "zona": "Movil",
        "offset_temp":  0.3,
        "offset_hum":   1.0,
        "offset_pres":  0.0,
        "sigma": 1.2,   # más ruido por ser móvil
    },
    {
        "id": "DT-BUC-ALT",
        "name": "Alto de Mejoras",
        "type": "Digital_Twin",
        "zona": "AltoMejoras",
        "offset_temp": -4.0,
        "offset_hum":  12.0,
        "offset_pres":  8.0,  # más presión a mayor altitud
        "sigma": 0.8,
    },
]

# ──────────────────────────────────────────────
# ESTADO GLOBAL DE CONTROL (retroceso)
# ──────────────────────────────────────────────

device_state = {
    d["id"]: {
        "active": True,
        "calibration_offset": 0.0,
        "interval": DEFAULT_INTERVAL,
        "muted": False,
    }
    for d in DEVICES
}


def load_control_file():
    """Lee el archivo control.json y aplica comandos pendientes."""
    if not os.path.exists(CONTROL_FILE):
        return
    try:
        with open(CONTROL_FILE, "r") as f:
            cmds = json.load(f)
        for cmd in cmds:
            did = cmd.get("device")
            action = cmd.get("cmd")
            if did not in device_state:
                continue
            if action == "off":
                device_state[did]["active"] = False
                print(f"[CONTROL] {did} → APAGADO")
            elif action == "on":
                device_state[did]["active"] = True
                print(f"[CONTROL] {did} → ENCENDIDO")
            elif action == "calibrate":
                device_state[did]["calibration_offset"] = float(cmd.get("offset", 0))
                print(f"[CONTROL] {did} → CALIBRADO offset={cmd.get('offset')}")
            elif action == "interval":
                device_state[did]["interval"] = int(cmd.get("value", DEFAULT_INTERVAL))
                print(f"[CONTROL] {did} → INTERVALO={cmd.get('value')}s")
            elif action == "mute":
                device_state[did]["muted"] = True
                print(f"[CONTROL] {did} → ALERTAS SILENCIADAS")
            elif action == "unmute":
                device_state[did]["muted"] = False
                print(f"[CONTROL] {did} → ALERTAS ACTIVAS")
            elif action == "restart":
                device_state[did]["active"] = True
                device_state[did]["calibration_offset"] = 0.0
                device_state[did]["interval"] = DEFAULT_INTERVAL
                device_state[did]["muted"] = False
                print(f"[CONTROL] {did} → REINICIADO")
        # Limpiar archivo tras procesar
        with open(CONTROL_FILE, "w") as f:
            json.dump([], f)
    except Exception as e:
        print(f"[ERROR] control.json: {e}")


# ──────────────────────────────────────────────
# AZURE MAPS API
# ──────────────────────────────────────────────

def fetch_azure_weather():
    """Llama Azure Maps y retorna dict con variables meteorológicas."""
    params = {
    "api-version": "1.0",
    "query": f"{BUC_LAT},{BUC_LON}",
    "subscription-key": AZURE_KEY,
    "language": "es-MX",
    }
    try:
        r = requests.get(AZURE_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        cur = data["results"][0]
        return {
            "temperature":    cur["temperature"]["value"],
            "humidity":       cur["relativeHumidity"],
            "wind_speed":     cur["wind"]["speed"]["value"],
            "wind_direction": cur["wind"]["direction"]["degrees"],
            "uv_index":       cur.get("uvIndex", 0),
            "rain_mm":        cur.get("precipitationSummary", {}).get("pastHour", {}).get("value", 0.0),
            "pressure":       cur.get("pressure", {}).get("value", 1013.0),
            "cloud_cover":    cur.get("cloudCover", 0),
            "visibility":     cur.get("visibility", {}).get("value", 10.0),
            "feels_like":     cur.get("realFeelTemperature", {}).get("value", cur["temperature"]["value"]),
        }
    except Exception as e:
        print(f"[ERROR] Azure Maps API: {e}")
        # Valor de respaldo basado en clima típico de Bucaramanga
        return {
            "temperature":    28.0,
            "humidity":       65.0,
            "wind_speed":     12.0,
            "wind_direction": 90.0,
            "uv_index":       6,
            "rain_mm":        0.0,
            "pressure":       1008.0,
            "cloud_cover":    40,
            "visibility":     10.0,
            "feels_like":     30.0,
        }


# ──────────────────────────────────────────────
# GENERADOR DE DIGITAL TWINS
# ──────────────────────────────────────────────

def generate_dt_values(device: dict, base: dict, ts: datetime) -> dict:
    """
    Genera valores para un Digital Twin a partir del dato real (base).
    Aplica offset de zona + ruido gaussiano + calibración de retroceso.
    """
    sigma = device["sigma"]
    cal   = device_state[device["id"]]["calibration_offset"]

    def noisy(val, offset=0.0):
        return round(val + offset + cal + np.random.normal(0, sigma), 2)

    # CO₂ simulado (no viene de la API): base ~400 ppm, varía con hora del día
    hour = ts.hour
    co2_base = 400 + 30 * math.sin((hour - 6) * math.pi / 12)  # pico a mediodía
    co2 = round(co2_base + np.random.normal(0, 10), 1)

    # Batería simulada para estación móvil (descarga lenta)
    battery = None
    if device["id"] == "DT-BUC-MOV":
        # ciclo de 24h: 100% al amanecer, ~60% al anochecer
        battery = round(100 - (hour / 24) * 40 + np.random.normal(0, 1), 1)

    return {
        "temperature":    noisy(base["temperature"],    device["offset_temp"]),
        "humidity":       min(100, max(0, noisy(base["humidity"],       device["offset_hum"]))),
        "wind_speed":     max(0,  noisy(base["wind_speed"],     0.0)),
        "wind_direction": round((base["wind_direction"] + np.random.normal(0, 10)) % 360, 1),
        "uv_index":       max(0,  round(base["uv_index"] + np.random.normal(0, 0.3), 1)),
        "rain_mm":        max(0,  round(base["rain_mm"] + np.random.normal(0, 0.1), 2)),
        "pressure":       noisy(base["pressure"],       device["offset_pres"]),
        "cloud_cover":    max(0, min(100, int(base["cloud_cover"] + np.random.normal(0, 5)))),
        "visibility":     max(0, round(base["visibility"] + np.random.normal(0, 0.3), 1)),
        "feels_like":     noisy(base["feels_like"],     device["offset_temp"]),
        "co2_ppm":        co2,
        "battery_pct":    battery,
    }


# ──────────────────────────────────────────────
# ESCRITURA EN INFLUXDB
# ──────────────────────────────────────────────

def build_point(device: dict, values: dict, ts: datetime) -> Point:
    """Construye un Point de InfluxDB con todas las variables del dispositivo."""
    p = (
        Point("weather_station")
        .tag("device_id",   device["id"])
        .tag("device_name", device["name"])
        .tag("device_type", device["type"])
        .tag("zona",        device["zona"])
        .tag("city",        "Bucaramanga")
        .time(ts, write_precision='s')
    )
    for key, val in values.items():
        if val is not None:
            p = p.field(key, float(val))

    # Estado del dispositivo como campo
    state = device_state[device["id"]]
    p = p.field("is_active",    int(state["active"]))
    p = p.field("cal_offset",   float(state["calibration_offset"]))
    p = p.field("interval_sec", int(state["interval"]))
    return p


def write_points(write_api, points: list):
    try:
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
        print(f"[OK] {len(points)} puntos escritos en InfluxDB — {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[ERROR] InfluxDB write: {e}")


# ──────────────────────────────────────────────
# BACKFILL — 7 DÍAS DE HISTÓRICO
# ──────────────────────────────────────────────

def backfill_7_days(write_api):
    """
    Genera 7 días de datos históricos simulados (un punto cada 15 min).
    Usa valores típicos de Bucaramanga con variación diurna realista.
    """
    print("[BACKFILL] Generando 7 días de histórico...")
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    step = timedelta(minutes=15)
    ts = start
    batch = []

    while ts <= now:
        hour = ts.hour
        # Variación diurna típica Bucaramanga
        temp_base  = 22 + 8 * math.sin((hour - 6) * math.pi / 12)
        hum_base   = 80 - 20 * math.sin((hour - 6) * math.pi / 12)
        uv_base    = max(0, 8 * math.sin((hour - 6) * math.pi / 12))
        wind_base  = 5 + 10 * abs(math.sin(hour * math.pi / 12))
        rain_base  = 2.0 if 14 <= hour <= 17 else 0.0  # lluvia vespertina típica
        pres_base  = 1008.0 + 2 * math.sin(hour * math.pi / 12)
        cloud_base = 30 + 40 * math.sin((hour - 10) * math.pi / 12)

        api_base = {
            "temperature":    round(temp_base + np.random.normal(0, 1.0), 1),
            "humidity":       round(min(100, max(40, hum_base + np.random.normal(0, 3))), 1),
            "wind_speed":     round(max(0, wind_base + np.random.normal(0, 2)), 1),
            "wind_direction": round(random.uniform(60, 180), 1),
            "uv_index":       round(max(0, uv_base + np.random.normal(0, 0.5)), 1),
            "rain_mm":        round(max(0, rain_base + np.random.normal(0, 0.5)), 2),
            "pressure":       round(pres_base + np.random.normal(0, 0.5), 1),
            "cloud_cover":    int(max(0, min(100, cloud_base + np.random.normal(0, 8)))),
            "visibility":     round(max(1, 10 - rain_base * 0.5 + np.random.normal(0, 0.3)), 1),
            "feels_like":     round(temp_base + 2 + np.random.normal(0, 1), 1),
        }

        for device in DEVICES:
            if device["type"] == "API_Real":
                vals = {**api_base, "co2_ppm": None, "battery_pct": None}
            else:
                vals = generate_dt_values(device, api_base, ts)

            batch.append(build_point(device, vals, ts))

            if len(batch) >= 500:
                write_points(write_api, batch)
                batch = []

        ts += step

    if batch:
        write_points(write_api, batch)

    print("[BACKFILL] ✅ Histórico completado.")


# ──────────────────────────────────────────────
# LOOP PRINCIPAL
# ──────────────────────────────────────────────

def run_collector():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    print("[START] Colector IoT Bucaramanga iniciado.")
    print(f"        InfluxDB → {INFLUX_URL} | Bucket: {INFLUX_BUCKET}")
    print(f"        Dispositivos: {len(DEVICES)}")
    print()

    while True:
        load_control_file()

        ts = datetime.now(timezone.utc)
        base = fetch_azure_weather()
        print(f"[API] Temp={base['temperature']}°C  Hum={base['humidity']}%  "
              f"Viento={base['wind_speed']}km/h  UV={base['uv_index']}")

        points = []
        for device in DEVICES:
            if not device_state[device["id"]]["active"]:
                print(f"[SKIP] {device['id']} está APAGADO")
                continue

            if device["type"] == "API_Real":
                vals = {**base, "co2_ppm": None, "battery_pct": None}
            else:
                vals = generate_dt_values(device, base, ts)

            points.append(build_point(device, vals, ts))

        write_points(write_api, points)

        # Usar el intervalo del primer dispositivo activo como referencia
        interval = DEFAULT_INTERVAL
        for did, state in device_state.items():
            if state["active"]:
                interval = state["interval"]
                break

        print(f"[WAIT] Próxima lectura en {interval}s...\n")
        time.sleep(interval)


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Colector IoT - Bucaramanga")
    parser.add_argument("--backfill", action="store_true",
                        help="Genera 7 días de histórico antes de iniciar el loop")
    args = parser.parse_args()

    if args.backfill:
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        backfill_7_days(write_api)

    run_collector()
