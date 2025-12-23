import sys
import select
from machine import Pin, I2C
from time import sleep, ticks_ms
import ssd1306
from neopixel import NeoPixel

#------------ Connected components ------------#
# rgb_led = NeoPixel(Pin(11), 1)

next_button = Pin(10, Pin.IN, Pin.PULL_UP) 
prev_button  = Pin(20, Pin.IN, Pin.PULL_UP)
start_button  = Pin(21, Pin.IN, Pin.PULL_UP)

# i2c = I2C(sda=Pin(5), scl=Pin(6)) # Correct pinout for XIAO RP2040
# lcd_display = ssd1306.SSD1306_I2C(128, 64, i2c)
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

def send(msg: str):
    sys.stdout.write(msg + "\n")

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

def handle_led(data: str):
    # Expecting format: "R G B"
    data = data.split(" ")
    if len(data) > 3:
        r, g, b = data[0:3]
        # rgb_led[0] = (int(r), int(g), int(b))
        # rgb_led.write()
    else:
        send("ERR INVALID_LED_CMD")

def handle_display(data: str):
    pass # ADD LATER

def handle_start(data: str):
    send("STATUS READY")

def process_command(cmd: str):
    parts = cmd.split(" ", 1)
    command_type = parts[0]
    data = parts[1] if len(parts) > 1 else ""

    command_handlers = {
        # "LED": handle_led,
        "START": handle_start,
        # "DISPLAY": handle_display,
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
            send("BUTTON " + name + " LONG")
        else:
            send("BUTTON " + name + " SHORT")

if __name__ == "__main__":
    while True:

        command = read_line()
        if command:
            process_command(command)
        
        check_button(start_button, "START")
        check_button(prev_button, "PREV")
        check_button(next_button, "NEXT")

        sleep(0.01)
