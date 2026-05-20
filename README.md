# Sistema IoT — Monitoreo Meteorológico Bucaramanga
## Red de 10 Estaciones (1 API Real + 9 Digital Twins)

---

## 📁 Archivos

| Archivo | Descripción |
|---|---|
| `collector.py` | Colector principal: llama Azure Maps API + simula DTs + escribe en InfluxDB |
| `control.py` | Panel de control (retroceso): apaga, calibra, ajusta frecuencia |
| `control.json` | Cola de comandos entre control.py y collector.py (auto-generado) |
| `requirements.txt` | Dependencias Python |

---

## ⚙️ Instalación

```bash
pip install -r requirements.txt
```

---
### Consideraciones

- Agregar el Azure KEY en el collector.py
- Agregar Influx Token en collector.py y docker-compose
- Crear el archvo .env
  Ejemplo:
  INFLUX_URL=
  INFLUX_TOKEN=
  INFLUX_ORG=
  INFLUX_BUCKET=


## 🚀 Uso

### 1. Configurar variables de entorno (InfluxDB)

```bash
export INFLUX_URL="http://localhost:8086"
export INFLUX_TOKEN="tu-token-influxdb"
export INFLUX_ORG="iot-buc"
export INFLUX_BUCKET="weather"
```

### 2. Generar 7 días de histórico + iniciar colector

```bash
python collector.py --backfill
```

### 3. Solo iniciar el colector (sin histórico)

```bash
python collector.py
```

### 4. Panel de control interactivo (retroceso)

```bash
python control.py
```

### 5. Comandos directos (para scripts/automatización)

```bash
# Apagar un dispositivo
python control.py --device DT-BUC-GIR --cmd off

# Encender
python control.py --device DT-BUC-GIR --cmd on

# Calibrar temperatura (+1.5°C de offset)
python control.py --device DT-BUC-CAB --cmd calibrate --offset 1.5

# Cambiar frecuencia a 30 segundos
python control.py --device DT-BUC-MOV --cmd interval --value 30

# Reiniciar (resetea calibración y frecuencia)
python control.py --device DT-BUC-ALT --cmd restart

# Silenciar alertas
python control.py --device EST-BUC-API --cmd mute
```

---

## 📡 Dispositivos

| ID | Tipo | Zona |
|---|---|---|
| EST-BUC-API | API Real (Azure Maps) | Centro |
| DT-BUC-CAB | Digital Twin | Cabecera |
| DT-BUC-LAG | Digital Twin | Lagos del Cacique |
| DT-BUC-FLO | Digital Twin | Floridablanca |
| DT-BUC-GIR | Digital Twin | Girón |
| DT-BUC-PIE | Digital Twin | Piedecuesta |
| DT-BUC-NOR | Digital Twin | Norte (UIS) |
| DT-BUC-ORI | Digital Twin | Oriental |
| DT-BUC-MOV | Digital Twin | Estación Móvil |
| DT-BUC-ALT | Digital Twin | Alto de Mejoras |

---

## 📊 Variables por dispositivo

| Variable | Unidad | Fuente |
|---|---|---|
| temperature | °C | API + DT |
| humidity | % | API + DT |
| wind_speed | km/h | API + DT |
| wind_direction | ° | API + DT |
| uv_index | 0-11 | API + DT |
| rain_mm | mm/h | API + DT |
| pressure | hPa | API + DT |
| cloud_cover | % | API + DT |
| visibility | km | API + DT |
| feels_like | °C | API + DT |
| co2_ppm | ppm | Solo DT |
| battery_pct | % | Solo DT-MOV |

---

## 🏗️ Stack Tecnológico

```
Azure Maps API ──┐
                 ├──▶  collector.py  ──▶  InfluxDB  ──▶  Grafana
Python DT sims ──┘

control.py ──▶ control.json ──▶ collector.py (retroceso)
```

---

## 📈 Grafana — Queries de ejemplo (Flux)

```flux
// Temperatura últimas 24h — todos los dispositivos
from(bucket: "weather")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "weather_station")
  |> filter(fn: (r) => r._field == "temperature")
  |> aggregateWindow(every: 15m, fn: mean, createEmpty: false)

// Máxima temperatura del día por zona
from(bucket: "weather")
  |> range(start: -24h)
  |> filter(fn: (r) => r._field == "temperature")
  |> group(columns: ["zona"])
  |> max()

// Alerta: temperatura > 35°C
from(bucket: "weather")
  |> range(start: -1h)
  |> filter(fn: (r) => r._field == "temperature")
  |> filter(fn: (r) => r._value > 35.0)
```
