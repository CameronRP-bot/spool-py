# Program 6 will run the trap triggering from the APIRs.

from util import *

shared_dict = SharedDict()
rpi_uart = RPi_UART(shared_dict, i2c=i2c)
spool = Spool(rpi_uart=rpi_uart)
apir = APIR()
clock = Clock()
switches = Switches()

# Function to run to check if there is motion
motion_check = apir.motion

# All enable checks need to pass for the trap to be able to trigger
enabled_checks = [
    spool.enable_check,        # Check that the spool is at the home position
    clock.enable_check,        # Check that it can trigger at the current time
    switches.enable_check,     # Check that the switches shouldn't disable the trap
]

print("Running trap sequence.")
run_sequence(spool, motion_check, enabled_checks, rpi_uart=rpi_uart, apir=apir)
