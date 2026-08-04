# Program 2 will run the trap triggering from the PIRs when it is enabled through the comms port.
# This is just a simple HIGH for enable and LOW for disable of the trap on the RP2040 Rx pin.

from util import *

spool = Spool()
apir = APIR()
clock = Clock()
switches = Switches()

# We are just using a digital read from the RX pin, for this reason we can't use the UART
rx_pin = Pin(PIN_UART_RX, Pin.IN, Pin.PULL_DOWN)

# Motion from the PIRs
def motion_check():
    return apir.motion()

def pin_enable_check():
    if rx_pin.value() == 1:
        return True, ""
    return False, "enable pin is low"

# Enable checks for spool, clock and switches
enabled_checks = [
    spool.enable_check,        # Check that the spool is at the home position
    pin_enable_check,          # Check that the enable pin is high
    switches.enable_check,     # Check that the switches shouldn't disable the trap
]

print("Running trap sequence.")
run_sequence(spool, motion_check, enabled_checks)
