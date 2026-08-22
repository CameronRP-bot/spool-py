# Program 8 will run through a reset, home, trigger, home cycle.

import time
from util import Spool

shared_dict = SharedDict()
rpi_uart = RPi_UART(shared_dict, i2c=i2c)
spool = Spool(rpi_uart=rpi_uart)

# It will go through the loop every `loop_time_seconds` amount of seconds.
loop_time_seconds = 60 * 3

print("Resetting")
spool.reset_sequence()
time.sleep(2)

while True:
    start_time = time.time() # Get start time in seconds

    print("Releasing.")
    spool.release()
    time.sleep(2)

    print("Resetting")
    spool.reset_sequence()
    time.sleep(2)

    elapsed_time = time.time() - start_time
    if elapsed_time < loop_time_seconds:
        sleep_duration = loop_time_seconds - elapsed_time
        print(f"Sleeping for {sleep_duration} seconds")
        time.sleep(sleep_duration)
    else:
        print("Complete loop in " + str(elapsed_time) + " seconds.")
