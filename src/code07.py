# Program 7 will run the trap triggering from the Analog PIRs. Can be set to only trigger at night.

import time

from machine import Pin

from config import PIN_SW_1, PIN_SW_2
from util import APIR, Clock, RPi_UART, SharedDict, Spool, i2c

shared_dict = SharedDict()
rpi_uart = RPi_UART(shared_dict, i2c=i2c)
spool = Spool(rpi_uart=rpi_uart)
apir = APIR()
clock = Clock()

# Green LED
led1 = Pin(PIN_SW_1, Pin.OUT)
led1.low()

# Blue LED
led2 = Pin(PIN_SW_2, Pin.OUT)
led2.low()

led1_off_time = 0
led2_off_time = 0

while True:
    # print("======")
    apir.motion()
    now = time.time()

    if apir.displacement_triggered:
        led1_off_time = now + 1
    led1.high() if now < led1_off_time else led1.low()

    if apir.gradient_triggered:
        led2_off_time = now + 1
    led2.high() if now < led2_off_time else led2.low()
