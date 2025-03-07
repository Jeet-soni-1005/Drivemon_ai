from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import serial
import pynmea2
import threading
import time
import requests
from pushbullet import Pushbullet
import os
from dotenv import load_dotenv
load_dotenv()

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

app = Flask(__name__)
socketio = SocketIO(app)

pb = Pushbullet(ACCESS_TOKEN)

def send_push_notification(message):
    push = pb.push_note("Vehicle Alert", message)

gps_data = {
    "latitude": None,
    "longitude": None,
    "speed_kph": 0.0,
    "timestamp": None,
    "object_distance": None  # Added object distance field
}

# Function to read GPS data
def track_gps_data():
    port = "COM3"  
    baudrate = 9600
    try:
        with serial.Serial(port, baudrate, timeout=1) as gps_serial:
            print("Reading GPS data...")
            while True:
                line = gps_serial.readline().decode('ascii', errors='replace').strip()
                if line.startswith('$GPRMC'):
                    try:
                        rmc_data = pynmea2.parse(line)
                        latitude = rmc_data.latitude
                        longitude = rmc_data.longitude
                        speed_knots = rmc_data.spd_over_grnd
                        speed_kph = speed_knots * 1.852 if speed_knots else 0.0

                        gps_data.update({
                            "latitude": latitude,
                            "longitude": longitude,
                            "speed_kph": speed_kph,
                            "timestamp": time.time()
                        })
                        socketio.emit("updateData", gps_data)
                        print(f"GPS Data: {gps_data}")

                        # Speed Alert
                        if gps_data["speed_kph"] > 40:
                            send_push_notification(f"Speed Alert: {gps_data['speed_kph']} km/h")

                        # Close Object Alert (Check if object distance is updated from camera)
                        if gps_data["object_distance"] and gps_data["object_distance"] < 100 and gps_data["speed_kph"] > 40:
                            send_push_notification(f"Warning! Object detected at {gps_data['object_distance']} cm ahead while speed is {gps_data['speed_kph']} km/h")

                    except pynmea2.ParseError:
                        continue

    except serial.SerialException as e:
        print(f"Serial error: {e}")

@socketio.on("distance_update")
def update_distance(data):
    gps_data["object_distance"] = data["distance"]
    print(f"Object Distance Updated: {gps_data['object_distance']} cm")

@app.route("/")
def index():
    return render_template('index.html')

if __name__ == "__main__":
    gps_thread = threading.Thread(target=track_gps_data, daemon=True)
    gps_thread.start()
    socketio.run(app, host="0.0.0.0", port=5000)
