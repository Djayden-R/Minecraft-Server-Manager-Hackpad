import sys
import select
from machine import Pin, SoftI2C
from time import sleep, ticks_ms
import ssd1306
from neopixel import NeoPixel

#------------ Connected components ------------#
rgb_led = NeoPixel(Pin(3), 1)

next_button = Pin(1, Pin.IN, Pin.PULL_UP) 
prev_button  = Pin(2, Pin.IN, Pin.PULL_UP)
start_button  = Pin(4, Pin.IN, Pin.PULL_UP)

i2c = None
lcd_display = None
#---------------------------------------------#

button_states = {
    "NEXT": False,
    "PREV": False,
    "START": False,
}

button_press_times = {
    "NEXT": 0,
    "PREV": 0,
    "START": 0,
}

MODE_STATUS = "STATUS"
MODE_CHAT = "CHAT"
MODE_LOG = "LOG"

current_mode = MODE_STATUS

latest_status = {
    "status": "UNKNOWN",
    "players": "0",
    "version": "N/A",
    "uptime": "0s",
}

chat_lines = []
log_lines = []

last_status = None

def send(msg: str):
    sys.stdout.write(msg + "\n")
    flush = getattr(sys.stdout, "flush", None)
    if flush is not None:
        try:
            flush()
        except OSError:
            pass

def init_display():
    bus = SoftI2C(sda=Pin(6), scl=Pin(7), freq=100000)
    addresses = bus.scan()

    if not addresses:
        send("ERR OLED_NOT_FOUND: no I2C devices detected")
        return bus, None

    oled_addr = None
    for candidate in (0x3C, 0x3D):
        if candidate in addresses:
            oled_addr = candidate
            break

    if oled_addr is None:
        oled_addr = addresses[0]

    try:
        display = ssd1306.SSD1306_I2C(128, 32, bus, addr=oled_addr)
        return bus, display
    except OSError as exc:
        send("ERR OLED_INIT_FAILED: " + str(exc))
        return bus, None

def chunk_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def read_line():
    # Create a poll object to check if stdin has data available
    poll_obj = select.poll()
    poll_obj.register(sys.stdin, select.POLLIN)
    
    # Check if data is available (0ms timeout = non-blocking)
    if poll_obj.poll(0):
        try:
            line = sys.stdin.readline()
            if line:
                return line.strip()
        except:
            pass
    return None

def trim_display_text(text: str, width: int = 21) -> str:
    if len(text) <= width:
        return text
    return text[:width]

def prettify_status_name(status: str) -> str:
    if not status:
        return "Unknown"

    return status.replace("_", " ").title()

def push_line(buffer, text: str, max_lines: int = 3):
    buffer.append(text)
    if len(buffer) > max_lines:
        del buffer[0]

def render_status():
    if lcd_display is None:
        return

    lcd_display.fill(0)
    pretty_status = prettify_status_name(latest_status["status"])

    lcd_display.text("Server", 0, 0)
    lcd_display.text(trim_display_text(pretty_status), 0, 8)
    lcd_display.text(trim_display_text("Players: " + latest_status["players"]), 0, 16)
    lcd_display.text(trim_display_text("U:" + latest_status["uptime"]), 0, 24)
    lcd_display.show()

def render_lines(title: str, lines):
    if lcd_display is None:
        return

    lcd_display.fill(0)
    lcd_display.text(title, 0, 0)

    visible = lines[-3:]
    y = 8
    for line in visible:
        lcd_display.text(trim_display_text(line), 0, y)
        y += 8

    lcd_display.show()

def render_current_mode():
    if current_mode == MODE_STATUS:
        render_status()
    elif current_mode == MODE_CHAT:
        render_lines("Chat", chat_lines)
    elif current_mode == MODE_LOG:
        render_lines("Log", log_lines)

def handle_led(data: str):
    # Expecting format: "RRGGBB" (hexadecimal)
    data_parts = data.split()
    if len(data_parts) == 3:
        try:
            r, g, b = data_parts[0:3]
            rgb_led[0] = (int(r), int(g), int(b))
            rgb_led.write()
        except ValueError:
            send("ERR INVALID_LED_CMD: RGB values must be integers")
    elif len(data_parts) == 1:
        if len(data_parts[0]) == 6:
            try:
                r, g, b = list(chunk_list(data_parts[0], 2))
                rgb_led[0] = (int(r, 16), int(g, 16), int(b, 16))
                rgb_led.write()
            except ValueError:
                send("ERR INVALID_LED_CMD: invalid hex color")
        else:
            send("ERR INVALID_LED_CMD: expected 6-char hex color")
    else:
        send(f"ERR INVALID_LED_CMD: {len(data_parts)} arguments")

def handle_status(data: str):
    global last_status
    parts = data.split()
    if len(parts) != 4:
        send(f"ERR INVALID_STATUS_CMD: should contain 4 arguments (contains {len(parts)})")
        return

    status, player_count, version_number, uptime = parts

    if parts != last_status:
        latest_status["status"] = status
        latest_status["players"] = player_count
        latest_status["version"] = version_number
        latest_status["uptime"] = uptime

        if current_mode == MODE_STATUS:
            render_status()

        last_status = parts

def handle_chat(data: str):
    message = data.strip()
    if not message:
        send("ERR INVALID_CHAT_CMD: missing message")
        return

    push_line(chat_lines, message)
    if current_mode == MODE_CHAT:
        render_lines("Chat", chat_lines)

def handle_log(data: str):
    message = data.strip()
    if not message:
        send("ERR INVALID_LOG_CMD: missing message")
        return

    push_line(log_lines, message)
    if current_mode == MODE_LOG:
        render_lines("Log", log_lines)

def handle_mode(data: str):
    global current_mode

    mode = data.strip().upper()
    if mode not in (MODE_STATUS, MODE_CHAT, MODE_LOG):
        send("ERR INVALID_MODE_CMD: expected STATUS|CHAT|LOG")
        return

    current_mode = mode
    render_current_mode()
    send("STATUS MODE " + mode)
    
def handle_start(data: str):
    send("STATUS READY")

def process_command(cmd: str):
    parts = cmd.split(" ", 1)
    command_type = parts[0]
    data = parts[1] if len(parts) > 1 else ""

    command_handlers = {
        "LED": handle_led,
        "START": handle_start,
        "STATUS": handle_status,
        "CHAT": handle_chat,
        "LOG": handle_log,
        "MODE": handle_mode,
    }

    if command_type in command_handlers:
        command_handlers[command_type](data)
    else:
        send("ERR UNKNOWN_CMD: " + command_type)

def check_button(button: Pin, name: str):
    was_pressed = button_states[name]
    is_pressed = not button.value()

    changed_to_pressed = is_pressed and not was_pressed
    changed_to_released = not is_pressed and was_pressed

    if changed_to_pressed:
        button_states[name] = True
        button_press_times[name] = ticks_ms()

    elif changed_to_released:
        button_states[name] = False
        press_duration = ticks_ms() - button_press_times[name]

        if press_duration > 400:
            print("BUTTON " + name + " LONG")
        else:
            print("BUTTON " + name + " SHORT")

if __name__ == "__main__":
    i2c, lcd_display = init_display()

    while True:

        command = read_line()
        if command:
            process_command(command)

        check_button(start_button, "START")
        check_button(prev_button, "PREV")
        check_button(next_button, "NEXT")
        sleep(0.01)
