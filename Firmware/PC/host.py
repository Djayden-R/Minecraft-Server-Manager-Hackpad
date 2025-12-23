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


class Mode(Enum):
    STATUS = auto()
    CHAT = auto()
    LOG = auto()

current_mode = None

server_info = {
    "status": None,
    "players": None,
    "version": None,
    "chat_lines": [],
    "log_lines": []
}



# ------------- MQTT Setup ------------- #
MQTT_TOPICS = [
    ("minecraft/chat", 0),
    ("minecraft/log", 0),
    ("minecraft/players", 0),
    ("minecraft/version", 0),
]

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT")
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos)
    else:
        print(f"Connecting to MQTT failed: {rc}")

def update_status_display():
    pass #ADD LATER

def update_chat_display(new_line: str):
    pass #ADD LATER

def update_log_display(new_line: str):
    pass #ADD LATER

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="ignore")
    print(f"[MQTT EVENT] {msg.topic}: {payload}")

    if msg.topic == "minecraft/players": # Update playercount and server state
        player_amount = payload
        if player_amount.isdigit():
            if int(player_amount) == 0:
                server_info["status"] = ServerState.RUNNING
            elif int(player_amount) > 0:
                server_info["status"] = ServerState.PEOPLE_ONLINE
            server_info["players"] = int(player_amount)
        elif player_amount == "unavailable":
            server_info["status"] = ServerState.OFF

    elif msg.topic == "minecraft/log": # Check if mode is log and draw log line to screen
        log_message = payload
        server_info["log_lines"].append(log_message)
        if current_mode == Mode.LOG:
            update_log_display(log_message)

    elif msg.topic == "minecraft/chat":
        chat_message = payload
        server_info["chat_lines"].append(chat_message)
        if current_mode == Mode.CHAT:
            update_chat_display(chat_message)

    elif msg.topic == "minecraft/version":
        version_number = payload
        if version_number != "unavailable":
            if version_number != server_info["version"]:
                server_info["version"] = version_number
                if current_mode == Mode.STATUS:
                    update_status_display()

client = mqtt.Client()

client.username_pw_set(
    username=MQTT_USERNAME,
    password=MQTT_PASSWORD
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
client.loop_start()

# ------------------------------------- #

def send(cmd: str):
    ser.write((cmd + "\n").encode())

def read():
    if ser.in_waiting:
        return ser.readline().decode().strip()
    return None

def start_minecraft_server():
    global state
    client.publish("minecraft/start_server", "press")
    state = ServerState.STARTING
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
        parts = data.split(":", 1)
        error_type = parts[0]
        error_info = parts[1] if len(parts) > 1 else ""
        print(f"{error_type} Error: {error_info}")
    else:
        print("Unknown ERR message")

def process_msg(msg: str):
    parts = msg.split(" ", 1)
    command_type = parts[0]
    data = parts[1] if len(parts) > 1 else ""

    command_handlers = {
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
            
            print("Waiting for Hackpad... Received: ", msg)
                
        retries -= 1
        sleep(0.1)
    return False

def wait_for_device_connected():
    global ser
    while True:
        try:
            ser = serial.Serial(COM_PORT, 115200, timeout=0)
            print("Found Hackpad on", COM_PORT)
            return
        except serial.serialutil.SerialException:
            sleep(1)

def main():
    wait_for_device_connected()

    if not wait_for_device_ready():
        print("Hackpad not ready, exiting...")
        return
    
    print("Hackpad ready")
    
    while True:
        msg = read()
        if msg:
            process_msg(msg)

        sleep(0.05)

if __name__ == "__main__":
    main()