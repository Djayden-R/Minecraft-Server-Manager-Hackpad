# Minecraft Server Manager Hackpad

This is a hackpad designed to control a Minecraft server. It has keys to interact with the server and device: a start key and two keys to switch between modes. It will indicate the state of the server using a status LED and has a screen that displays the live chat and other information about the server.

![Overall Hackpad](Images/assembled-hackpad.png)

## Why did I make it?

I have a Minecraft server with my friends and often don't notice it when my friends are online, so I wanted to make this device to show when my friends go online.

Couldn't I just make a Discord bot to ping me when my friends go online? Yeah, but it wouldn't be as fun as making a special device for on my desk that also shows the Minecraft chat live.

## How does it work?

The main logic of checking the server status and the chat isn't done on the Hackpad itself, but instead on the computer it is connected to. To make this work the pc will need to run the ```host.py```. This is going to connect with Home Assistant via MQTT and will gather and process all the information.

The program can send the following to the Hackpad (over USB):

- LED [COLOR] (not implemented yet)
- LCD [LINE] [TEXT] (also not implemented yet)

The Hackpads only task is to control the LCD, LED and send the button presses (either LONG or SHORT):

- START
- MODE_NEXT
- MODE_PREV

## Hardware

Schematic                               |  PCB                   |   Case
:--------------------------------------:|:----------------------:|:-------------------------:
![Schematic](Images/wire-schematic.png) | ![PCB](Images/pcb.png) | ![Case](Images/case.png)

## BOM

- 3x Cherry MX Switches
- 3x DSA Keycaps
- 1x SK6812 MINI-E LED
- 1x 0.91" 128x32 OLED Display
- 1x XIAO RP2040
- 1x Case (2 printed parts)
