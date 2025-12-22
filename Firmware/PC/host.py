import serial
from time import sleep, monotonic
import dotenv
import os
import requests
from enum import Enum, auto
import paho.mqtt.client as mqtt

dotenv.load_dotenv()

#------------ Setup Variables ------------#

# Hackpad port
COM_PORT = "COM11"

# MQTT
MQTT_BROKER = "192.168.1.186"
MQTT_PORT = 1883
MQTT_USERNAME = "mqtt-user"
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

#-----------------------------------------#

class ServerState(Enum):
    OFF = auto()
    STARTING = auto()
    RUNNING = auto()
    PEOPLE_ONLINE = auto()
    ERROR = auto()

state = None
ser = None

# ------------- MQTT Setup ------------- #
MQTT_TOPICS = [
    ("minecraft/chat", 0),
    ("minecraft/log", 0),
    ("minecraft/players", 0),
    ("minecraft/status", 0),
]

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Connected")
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos)
            print(f"[MQTT] Subscribed to {topic}")
    else:
        print(f"[MQTT] Connection failed: {rc}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="ignore")
    print(f"[MQTT EVENT] {msg.topic}: {payload}")

    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # place logic here to handle events from MQTT
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

client = mqtt.Client()

client.username_pw_set(
    username=MQTT_USERNAME,
    password=MQTT_PASSWORD
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

print("[SYSTEM] Listening for MQTT events...")
client.loop_start()

# ------------------------------------- #

def send(cmd: str):
    ser.write((cmd + "\n").encode())

def read():
    if ser.in_waiting:
        return ser.readline().decode().strip()
    return None

def ACK_handler(data: str):
    if data:
        print("Acknowledged: ", data)
    else:
        print("Unknown ACK message")

def start_minecraft_server():
    """Start server via MQTT command."""
    global state
    client.publish("hackpad/command/start_server", "press")
    state = ServerState.STARTING
    print("Minecraft server start command sent via MQTT")
    print("Minecraft server started")

def BUTTON_handler(data: str):
    data_parts = data.split(" ")
    button = data_parts[0] if len(data_parts) > 0 else ""
    press_type = data_parts[1] if len(data_parts) > 1 else ""

    print(f"Button {button} was {press_type} pressed")

    if button == "START" and press_type == "LONG":
        print("Starting Minecraft server via Home Assistant")
        start_minecraft_server()
        

def ERR_handler(data: str):
    if data:
        print("Error: ", data)
    else:
        print("Unknown ERR message")

def process_msg(msg: str):
    parts = msg.split(" ", 1)
    command_type = parts[0]
    data = parts[1] if len(parts) > 1 else ""

    command_handlers = {
        "ACK": ACK_handler,
        "BUTTON": BUTTON_handler,
        "ERR": ERR_handler,
    }
    
    if command_type in command_handlers:
        command_handlers[command_type](data)
    else:
        print("Unrecognized message: ", msg)

def wait_for_device_ready():
    send("START")
    retries = 100
    while retries > 0:
        msg = read()
        if msg:
            parts = msg.split(" ", 1)
            command_type = parts[0]
            if command_type == "STATUS" and len(parts) > 1 and parts[1] == "READY":
                return True
            
            print("Waiting for device... Received: ", msg)
                
        retries -= 1
        sleep(0.1)
    return False

def wait_for_device_connected():
    global ser
    while True:
        try:
            ser = serial.Serial(COM_PORT, 115200, timeout=0)
            print("Found device on", COM_PORT)
            return
        except serial.serialutil.SerialException:
            sleep(1)

def main():
    wait_for_device_connected()

    if not wait_for_device_ready():
        print("Device not ready, exiting...")
        return
    
    print("Device ready")
    
    while True:
        msg = read()
        if msg:
            process_msg(msg)

        sleep(0.05)

if __name__ == "__main__":
    main()