from flask import Flask, render_template, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_cors import CORS
import csv
from io import StringIO

app = Flask(__name__)
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "mysql+pymysql://root:@localhost/food_spoilage_db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# --- MODELS ---
class ThresholdProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    mq135_crit = db.Column(db.Float, default=300)
    temp_crit = db.Column(db.Float, default=35)


class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(50), default="New Device")
    is_active = db.Column(db.Boolean, default=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("threshold_profile.id"))
    profile = db.relationship("ThresholdProfile")


class Reading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), db.ForeignKey("device.device_id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    food_name = db.Column(db.String(50), default="Unknown")
    mq135 = db.Column(db.Float)
    temp = db.Column(db.Float)
    humidity = db.Column(db.Float)
    r = db.Column(db.Integer, default=0)
    g = db.Column(db.Integer, default=0)
    b = db.Column(db.Integer, default=0)
    fqi = db.Column(db.Integer)
    status = db.Column(db.String(20))
    estimated_life = db.Column(db.String(50), default="-")


# --- DETEKSI JAMUR (Visual) ---
def is_mold_detected(r, g, b, food_name):
    # Hitung kecerahan rata-rata
    avg_brightness = (r + g + b) / 3

    # 1. CEK OBJEK KOSONG / GELAP
    if avg_brightness < 20:
        return False

    # 2. LOGIKA NASI (Putih vs Hijau/Biru)
    if "Nasi" in food_name:
        if g > r + 20:
            return True
        if b > r + 20:
            return True
        if avg_brightness < 60 and avg_brightness > 20:
            return True

    # 3. LOGIKA ROTI
    if "Roti" in food_name:
        if g > r + 15 or b > r + 15:
            return True

    # 4. LOGIKA TEMPE
    if "Tempe" in food_name:
        if avg_brightness < 40 and avg_brightness > 15:
            return True

    # 5. LOGIKA DAGING/AYAM
    if "Daging" in food_name:
        return False
    return False


# --- ESTIMASI SISA WAKTU  ---
def calculate_remaining_time(fqi, current_temp, profile):
    if fqi <= 50:
        return "0 Jam (Basi)"

    points_left = fqi - 50
    decay_rate = 1.5
    temp_diff = profile.temp_crit - current_temp

    temp_factor = 1.0
    if temp_diff <= 0:
        temp_factor = 10.0
    elif temp_diff <= 10:
        temp_factor = 1.0 + (10 - temp_diff) * 0.5

    decay_rate = decay_rate * temp_factor

    # 4. Faktor Jenis Makanan
    p_name = profile.name.lower()

    if "tahu" in p_name:
        decay_rate *= 2.0
    elif "susu" in p_name:
        decay_rate *= 1.8
    elif "daging" in p_name:
        decay_rate *= 1.5
    elif "sayur" in p_name:
        decay_rate *= 1.2

    # 5. Hitung Estimasi
    hours_left = points_left / decay_rate

    # Format Tampilan
    if hours_left < 1:
        minutes = int(hours_left * 60)
        return f"± {max(1, minutes)} Menit"
    elif hours_left > 48:
        days = int(hours_left / 24)
        return f"> {days} Hari"
    else:
        return f"± {round(hours_left, 1)} Jam"


# --- LOGIKA FQI ---
def calculate_fqi(mq, temp, hum, r, g, b, profile):
    status_msg = "Segar"

    # 1. Cek Jamur (Visual)
    if is_mold_detected(r, g, b, profile.name):
        return 0, "BASI (Visual)"

    # 2. Cek Gas
    mq_ratio = mq / profile.mq135_crit

    if mq_ratio >= 1.0:
        return 0, "BASI (Gas)"
    elif mq_ratio >= 0.8:
        return 55, "Mulai Basi"

    # 3. Cek Suhu
    if temp >= profile.temp_crit:
        return 52, "Rusak (Panas)"

    # 4. Hitung Skor
    risk_mq = min((mq - 50) / (profile.mq135_crit - 50), 1)
    risk_mq = max(0, risk_mq)

    hum_penalty = 0
    if hum > 90:
        hum_penalty = 15

    final_score = 100 - (risk_mq * 100) - hum_penalty

    if final_score <= 50:
        status_msg = "BASI"
    elif final_score < 75:
        status_msg = "Mulai Basi"
        if final_score <= 50:
            final_score = 51

    return int(max(0, final_score)), status_msg


# --- ROUTES ---
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/readings", methods=["POST"])
def receive_reading():
    data = request.json
    dev_id = data.get("device_id")

    device = Device.query.filter_by(device_id=dev_id).first()
    if not device:
        default_profile = ThresholdProfile.query.first()
        device = Device(device_id=dev_id, name="New Device", profile=default_profile)
        db.session.add(device)
        db.session.commit()

    command = "ON" if device.is_active else "OFF"
    if not device.is_active:
        return (
            jsonify({"message": "Device OFF", "status": "OFFLINE", "command": "OFF"}),
            200,
        )

    r = data.get("r", 0)
    g = data.get("g", 0)
    b = data.get("b", 0)

    fqi, status = calculate_fqi(
        data["mq135"], data["temp"], data["humidity"], r, g, b, device.profile
    )
    est_time = calculate_remaining_time(fqi, data["temp"], device.profile)

    new_reading = Reading(
        device_id=dev_id,
        food_name=device.profile.name,
        mq135=data["mq135"],
        temp=data["temp"],
        humidity=data["humidity"],
        r=r,
        g=g,
        b=b,
        fqi=fqi,
        status=status,
        estimated_life=est_time,
        timestamp=datetime.now(),
    )
    db.session.add(new_reading)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Saved",
                "status": status,
                "fqi": fqi,
                "est_time": est_time,
                "command": command,
            }
        ),
        201,
    )


@app.route("/api/latest/<device_id>", methods=["GET"])
def get_latest(device_id):
    device = Device.query.filter_by(device_id=device_id).first()
    reading = (
        Reading.query.filter_by(device_id=device_id)
        .order_by(Reading.timestamp.desc())
        .first()
    )
    if reading and device:
        return jsonify(
            {
                "timestamp": reading.timestamp.strftime("%H:%M:%S"),
                "mq135": reading.mq135,
                "temp": reading.temp,
                "fqi": reading.fqi,
                "status": reading.status,
                "estimated_life": reading.estimated_life,
                "current_profile": device.profile.name,
                "is_active": device.is_active,
            }
        )
    return jsonify({}), 404


@app.route("/api/history/<device_id>", methods=["GET"])
def get_history(device_id):
    readings = (
        Reading.query.filter_by(device_id=device_id)
        .order_by(Reading.timestamp.desc())
        .limit(50)
        .all()
    )
    output = []
    for r in readings:
        output.append(
            {
                "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "food_name": r.food_name,
                "mq135": r.mq135,
                "temp": r.temp,
                "fqi": r.fqi,
                "status": r.status,
                "estimated_life": r.estimated_life,
            }
        )
    return jsonify(output)


@app.route("/api/export/<device_id>", methods=["GET"])
def export_csv(device_id):
    readings = (
        Reading.query.filter_by(device_id=device_id)
        .order_by(Reading.timestamp.asc())
        .all()
    )
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(
        [
            "Timestamp",
            "Device ID",
            "Jenis Makanan",
            "Gas",
            "Temp",
            "FQI",
            "Status",
            "Estimasi",
        ]
    )
    for r in readings:
        cw.writerow(
            [
                r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                r.device_id,
                r.food_name,
                r.mq135,
                r.temp,
                r.fqi,
                r.status,
                r.estimated_life,
            ]
        )
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = (
        f"attachment; filename=laporan_{device_id}.csv"
    )
    output.headers["Content-type"] = "text/csv"
    return output


@app.route("/api/profiles", methods=["GET"])
def get_profiles():
    profiles = ThresholdProfile.query.all()
    return jsonify([{"id": p.id, "name": p.name} for p in profiles])


@app.route("/api/device/<device_id>/set_profile", methods=["POST"])
def set_device_profile(device_id):
    data = request.json
    device = Device.query.filter_by(device_id=device_id).first()
    if device:
        device.profile_id = data.get("profile_id")
        db.session.commit()
        return jsonify({"message": "Updated"}), 200
    return jsonify({"message": "Not found"}), 404


@app.route("/api/device/<device_id>/toggle", methods=["POST"])
def toggle_device(device_id):
    device = Device.query.filter_by(device_id=device_id).first()
    if device:
        device.is_active = not device.is_active
        db.session.commit()
        return jsonify({"status": "success", "is_active": device.is_active})
    return jsonify({"error": "Device not found"}), 404


# --- SEED DATABASE YANG AMAN ---
def init_db():
    with app.app_context():
        db.create_all()

        profiles_data = [
            {"name": "Nasi Putih", "mq": 250, "temp": 35},
            {"name": "Daging Sapi/Ayam", "mq": 800, "temp": 32},
            {"name": "Tahu", "mq": 350, "temp": 30},
            {"name": "Tempe", "mq": 650, "temp": 32},
            {"name": "Roti", "mq": 300, "temp": 30},
            {"name": "Sayuran Hijau", "mq": 350, "temp": 25},
            {"name": "Susu/Dairy", "mq": 300, "temp": 20},
        ]

        print("🔄 Sinkronisasi Database Profil...")

        for p_data in profiles_data:
            profile = ThresholdProfile.query.filter_by(name=p_data["name"]).first()
            if profile:
                if (
                    profile.mq135_crit != p_data["mq"]
                    or profile.temp_crit != p_data["temp"]
                ):
                    profile.mq135_crit = p_data["mq"]
                    profile.temp_crit = p_data["temp"]
                    print(f"   -> Profil '{p_data['name']}' DIUPDATE.")
            else:
                new_profile = ThresholdProfile(
                    name=p_data["name"],
                    mq135_crit=p_data["mq"],
                    temp_crit=p_data["temp"],
                )
                db.session.add(new_profile)
                print(f"   -> Profil '{p_data['name']}' DITAMBAHKAN.")

        db.session.commit()
        print("✅ Database Siap & Aman.")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
