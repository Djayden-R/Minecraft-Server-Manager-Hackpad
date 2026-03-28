import serial
from time import sleep, monotonic
import dotenv
import os
from enum import Enum, auto
import paho.mqtt.client as mqtt
import threading
from queue import Queue

SERIAL_EXCEPTION = getattr(serial, "SerialException", None)
if SERIAL_EXCEPTION is None:
    serialutil = getattr(serial, "serialutil", None)
    SERIAL_EXCEPTION = getattr(serialutil, "SerialException", OSError) if serialutil else OSError

SERIAL_EXCEPTION_TYPES = [OSError, AttributeError]
if isinstance(SERIAL_EXCEPTION, type):
    SERIAL_EXCEPTION_TYPES.insert(0, SERIAL_EXCEPTION)
SERIAL_EXCEPTIONS = tuple(SERIAL_EXCEPTION_TYPES)

dotenv.load_dotenv()

#------------ Setup Variables ------------#

# Hackpad port
COM_PORT = "COM5"

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

current_mode = Mode.STATUS
state = ServerState.OFF
ser = None
ser_lock = threading.Lock()
server_started_at = None
last_status_sent_at = 0.0
last_led_sent_at = 0.0
led_blink_on = True

server_info = {
    "status": ServerState.OFF,
    "players": 0,
    "version": "unknown",
    "chat_lines": [],
    "log_lines": []
}



# ------------- MQTT Setup ------------- #
MQTT_TOPICS = [
    ("minecraft/chat", 0),
    ("minecraft/log", 0),
    ("minecraft/players", 0),
    ("minecraft/version", 0),
    ("minecraft/server_state", 0),
]

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT")
        for topic, qos in MQTT_TOPICS:
            client.subscribe(topic, qos)
    else:
        print(f"Connecting to MQTT failed: {rc}")

def sanitize_token(value) -> str:
    text = str(value) if value is not None else "unknown"
    return text.replace(" ", "_")

def format_uptime() -> str:
    if server_started_at is None:
        return "0s"

    seconds = int(monotonic() - server_started_at)
    if seconds < 60:
        return f"{seconds}s"

    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{secs}s"

    hours, mins = divmod(minutes, 60)
    return f"{hours}h{mins}m"

def mode_name(mode: Mode) -> str:
    return mode.name

def pretty_status(state_value: ServerState | None) -> str:
    if state_value is None:
        return "Unknown"

    if state_value == ServerState.PEOPLE_ONLINE:
        return "People Online"

    return state_value.name.title()

def set_mode(mode: Mode):
    global current_mode
    current_mode = mode
    send(f"MODE {mode_name(mode)}")

    if mode == Mode.STATUS:
        update_status_display()
    elif mode == Mode.CHAT and server_info["chat_lines"]:
        update_chat_display(server_info["chat_lines"][-1])
    elif mode == Mode.LOG and server_info["log_lines"]:
        update_log_display(server_info["log_lines"][-1])

def update_status_display():
    global last_status_sent_at

    status_name = pretty_status(server_info["status"])

    players = server_info["players"] if server_info["players"] is not None else 0
    version = server_info["version"] if server_info["version"] is not None else "unknown"
    uptime = format_uptime()

    send(
        "STATUS "
        + sanitize_token(status_name)
        + " "
        + sanitize_token(players)
        + " "
        + sanitize_token(version)
        + " "
        + sanitize_token(uptime)
    )
    last_status_sent_at = monotonic()

def update_chat_display(new_line: str):
    send("CHAT " + new_line)

def update_log_display(new_line: str):
    send("LOG " + new_line)

def current_server_state() -> ServerState:
    status = server_info["status"]
    if isinstance(status, ServerState):
        return status
    return ServerState.OFF

def update_led(force: bool = False):
    global last_led_sent_at, led_blink_on

    now = monotonic()
    state_value = current_server_state()

    # Blink while booting or when players are online.
    should_blink = state_value in (ServerState.STARTING, ServerState.PEOPLE_ONLINE)
    interval = 0.5 if should_blink else 1.0

    if not force and (now - last_led_sent_at) < interval:
        return

    if should_blink:
        led_blink_on = not led_blink_on
    else:
        led_blink_on = True

    if state_value == ServerState.OFF:
        color = (48, 0, 0)  # red
    elif state_value == ServerState.STARTING:
        color = (255, 110, 0) if led_blink_on else (0, 0, 0)  # amber blink
    elif state_value == ServerState.RUNNING:
        color = (0, 40, 120)  # blue
    else:
        color = (0, 180, 0) if led_blink_on else (0, 20, 0)  # green pulse

    send(f"LED {color[0]} {color[1]} {color[2]}")
    last_led_sent_at = now

def on_message(client, userdata, msg):
    global server_started_at

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
            if server_started_at is None:
                server_started_at = monotonic()
        elif player_amount == "unavailable":
            server_info["status"] = ServerState.OFF
            server_info["players"] = 0
            server_started_at = None

        update_status_display()
        update_led(force=True)

    elif msg.topic == "minecraft/log": # Check if mode is log and draw log line to screen
        log_message = payload
        server_info["log_lines"].append(log_message)
        update_log_display(log_message)

    elif msg.topic == "minecraft/chat":
        chat_message = payload
        server_info["chat_lines"].append(chat_message)
        update_chat_display(chat_message)

    elif msg.topic == "minecraft/version":
        version_number = payload
        if version_number != "unavailable":
            if version_number != server_info["version"]:
                server_info["version"] = version_number
            update_status_display()
        else:
            server_info["version"] = "unknown"
            update_status_display()
    elif msg.topic == "minecraft/server_state":
        state_text = payload.strip().lower()

        if state_text in ("off", "offline", "unavailable", "stopped"):
            server_info["status"] = ServerState.OFF
            server_info["players"] = 0
            server_started_at = None
        elif state_text in ("booting", "starting", "startup"):
            server_info["status"] = ServerState.STARTING
            if server_started_at is None:
                server_started_at = monotonic()
        elif state_text in ("running", "online", "on"):
            server_info["status"] = ServerState.RUNNING
            if server_started_at is None:
                server_started_at = monotonic()

        update_status_display()
        update_led(force=True)

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
    if ser is None:
        return

    with ser_lock:
        ser.write((cmd + "\n").encode())

def read():
    if ser is None:
        return None

    if ser.in_waiting:
        return ser.readline().decode(errors="ignore").strip()
    return None

def start_minecraft_server():
    global state
    client.publish("minecraft/start_server", "press")
    state = ServerState.STARTING
    server_info["status"] = ServerState.STARTING
    update_status_display()
    update_led(force=True)
    print("Minecraft server started")

def cycle_mode(direction: int):
    modes = [Mode.STATUS, Mode.CHAT, Mode.LOG]
    idx = modes.index(current_mode)
    next_idx = (idx + direction) % len(modes)
    set_mode(modes[next_idx])

def BUTTON_handler(data: str):
    data_parts = data.split(" ")
    button = data_parts[0] if len(data_parts) > 0 else ""
    press_type = data_parts[1] if len(data_parts) > 1 else ""

    print(f"Button {button} was {press_type} pressed")

    if press_type == "SHORT":
        if button == "NEXT":
            cycle_mode(1)
        elif button == "PREV":
            cycle_mode(-1)
        elif button == "START":
            set_mode(Mode.STATUS)

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

def STATUS_handler(data: str):
    parts = data.split(" ", 1)
    status_type = parts[0] if len(parts) > 0 else ""
    status_value = parts[1] if len(parts) > 1 else ""

    if status_type == "MODE" and status_value:
        print(f"Device mode set to {status_value}")
    elif status_type == "READY":
        print("Device is ready")
    elif data:
        print(f"STATUS {data}")
    else:
        print("Unknown STATUS message")

def process_msg(msg: str):
    parts = msg.split(" ", 1)
    command_type = parts[0]
    data = parts[1] if len(parts) > 1 else ""

    command_handlers = {
        "BUTTON": BUTTON_handler,
        "ERR": ERR_handler,
        "STATUS": STATUS_handler,
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
        except SERIAL_EXCEPTIONS:
            sleep(1)

def input_thread(input_queue):
    """Read user input in a separate thread"""
    while True:
        try:
            user_input = input("Send command: ").strip()
            if user_input:
                input_queue.put(user_input)
        except EOFError:
            break

def main():
    wait_for_device_connected()

    if not wait_for_device_ready():
        print("Hackpad not ready, exiting...")
        return
    
    print("Hackpad ready")
    set_mode(Mode.STATUS)
    update_status_display()
    update_led(force=True)
    
    # Start input thread
    input_queue = Queue()
    thread = threading.Thread(target=input_thread, args=(input_queue,), daemon=True)
    thread.start()
    
    while True:
        now = monotonic()
        msg = read()
        if msg:
            process_msg(msg)

        # Keep uptime live on the OLED even when no MQTT events are arriving.
        if server_info["status"] in (ServerState.RUNNING, ServerState.PEOPLE_ONLINE):
            if now - last_status_sent_at >= 1.0:
                update_status_display()

        update_led()

        # Check if there's user input without blocking
        if not input_queue.empty():
            user_input = input_queue.get()
            send(user_input)

        sleep(0.05)

if __name__ == "__main__":
    main()