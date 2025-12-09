import requests
import time
import random

url = "http://localhost:5000/api/readings"
device_id = "ESP32_SIMULATOR"

print("Simulasi dimulai. Tekan Ctrl+C untuk berhenti.")

mq_val = 120
temp_val = 28.0

while True:
    # Simulasi data naik perlahan (seolah-olah membusuk)
    mq_val += random.randint(-5, 10)
    temp_val += random.uniform(-0.1, 0.2)

    payload = {
        "device_id": device_id,
        "mq135": mq_val,
        "temp": round(temp_val, 1),
        "humidity": 60,
        "r": 0,
        "g": 0,
        "b": 0,
    }

    try:
        r = requests.post(url, json=payload)
        print(
            f"Kirim Data: MQ={mq_val}, Temp={temp_val:.1f} -> Respon: {r.status_code}"
        )
    except Exception as e:
        print("Error:", e)

    time.sleep(3)  # Kirim tiap 3 detik
