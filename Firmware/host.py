import serial
from time import sleep, monotonic
import dotenv
import os
import requests
from enum import Enum, auto

dotenv.load_dotenv()

#------------ Setup Variables ------------#

# Hackpad port
COM_PORT = "COM11"

# Home Assistant credentials
HA_URL = "http://192.168.1.186:8123"
HA_TOKEN = os.getenv("HA_TOKEN")
SERVER_START_ENTITY = "button.wake_on_lan"

#-----------------------------------------#

class ServerState(Enum):
    OFF = auto()
    STARTING = auto()
    RUNNING = auto()
    PEOPLE_ONLINE = auto()
    ERROR = auto()

state = None

ser = serial.Serial(COM_PORT, 115200, timeout=0)
sleep(1)

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
    global state
    url = f"{HA_URL}/api/services/button/press"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"entity_id": SERVER_START_ENTITY}
    r = requests.post(url, json=payload, headers=headers, timeout=5)
    r.raise_for_status()
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

def get_player_count():
    url = f"{HA_URL}/api/states/sensor.192_168_1_242_19132_spelers_online"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }

    r = requests.get(url, headers=headers, timeout=5)
    r.raise_for_status()
    data = r.json()
    return data.get("state", "not_found")

def update_server_state():
    global state
    player_count: str = get_player_count()

    if player_count.isdigit():
        if int(player_count) == 0:
            new_state = ServerState.RUNNING
        elif int(player_count) > 0:
            new_state = ServerState.PEOPLE_ONLINE
    elif player_count == "unavailable":
        if state != ServerState.STARTING:
            new_state = ServerState.OFF
        else:
            new_state = state
    elif player_count == "not_found":
        new_state = ServerState.ERROR
    

    if new_state != state:
        if new_state == ServerState.OFF:
            send("LED OFF")
        elif new_state in (ServerState.STARTING, ServerState.RUNNING, ServerState.PEOPLE_ONLINE):
            send("LED ON")
        
        print(f"Server state changed from {state} to {new_state}")
        state = new_state

def main():
    if not HA_TOKEN:
        print("Missing HA_TOKEN. Set it in your environment or .env file.")
        return

    if not wait_for_device_ready():
        print("Device not ready, exiting...")
        return
    
    print("Device ready")
    poll_interval = 2.0
    last_poll_time = monotonic()
    
    while True:
        msg = read()
        if msg:
            process_msg(msg)
        
        if monotonic() - last_poll_time >= poll_interval:
            update_server_state()
            last_poll_time = monotonic()

        sleep(0.05)

if __name__ == "__main__":
    main()