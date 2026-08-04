# Program 3 will run the trap triggering from the PIRs.
# It is disabled by:
#   Night time option
#   External Switches
#   Camera not enabling it (by default it is disabled and needs to be enabled)

from util import *


shared_dict = SharedDict()
rpi_uart = RPi_UART(shared_dict, i2c=i2c)
shared_dict.set("enable", False, new_key=True)
spool = Spool(rpi_uart=rpi_uart)
apir = APIR()
clock = Clock()
switches = Switches()

# Motion from the PIRs
def motion_check():
    return apir.motion()

# Enable checks for spool, clock and switches
enabled_checks = [
    spool.enable_check,        # Check that the spool is at the home position
    shared_dict.enable_check,  # Check that enable is True in the shared dict
    clock.enable_check,        # Check that it can trigger at the current time
    switches.enable_check,     # Check that the switches shouldn't disable the trap
]

print("Running trap sequence.")
run_sequence(spool, motion_check, enabled_checks, rpi_uart=rpi_uart)
