# This file is just to test the functionality of the PCB
#
# Run over the REPL. Each test prompts before starting so you can get ready.
# Press Enter to run a test, or type "s" then Enter to skip it.
# A summary of PASS/FAIL/SKIP is printed at the end.

import time

from machine import ADC, I2C, PWM, UART, Pin

from config import *

MAX_U16 = 65535

# Known I2C addresses on the PCB
I2C_ADDR_INA219 = 0x40
I2C_ADDR_EEPROM = 0x50
I2C_ADDR_RTC = 0x51

results = {}


def record(name, passed):
    results[name] = "PASS" if passed else "FAIL"
    print("--> {}: {}".format(name, results[name]))


def run_test(name, func):
    print("")
    print("======== {} ========".format(name))
    answer = input("Press Enter to run, 's' to skip: ").strip().lower()
    if answer == "s":
        results[name] = "SKIP"
        print("--> {}: SKIP".format(name))
        return
    try:
        record(name, func())
    except KeyboardInterrupt:
        # Ctrl+C aborts just this test
        record(name, False)
    except Exception as e:
        print("Test raised an exception:", e)
        record(name, False)


def wait_for_toggles(pin, description, toggles=4, timeout_s=30):
    # Watch a digital input and count state changes.
    # Passes once we have seen `toggles` transitions.
    print("{} (need {} state changes, {}s timeout)".format(description, toggles, timeout_s))
    last = pin.value()
    print("Initial state: {}".format(last))
    count = 0
    start = time.ticks_ms()
    while count < toggles:
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            print("Timed out after {} of {} state changes".format(count, toggles))
            return False
        value = pin.value()
        if value != last:
            count += 1
            last = value
            print("State changed to {} ({}/{})".format(value, count, toggles))
        time.sleep_ms(20) # debounce
    return True


# Testing night/day time switch
def test_night_switch():
    pin = Pin(PIN_SW_NIGHT_ONLY, Pin.IN, Pin.PULL_UP)
    return wait_for_toggles(pin, "Switch the night/day switch back and forth a few times")


# Testing Buzzer
def test_buzzer():
    print("Making some beeps...")
    buzzer = PWM(Pin(PIN_BUZZER))
    try:
        for freq in [800, 1000, 1500, 2000]:
            buzzer.freq(freq)
            buzzer.duty_u16(MAX_U16 // 2)
            time.sleep(0.3)
            buzzer.duty_u16(0)
            time.sleep(0.2)
    finally:
        buzzer.duty_u16(0)
    answer = input("Did you hear the beeps? (y/n): ").strip().lower()
    return answer == "y"


# Test switch 1
def test_switch_1():
    pin = Pin(PIN_SW_1, Pin.IN, Pin.PULL_UP)
    return wait_for_toggles(pin, "Switch switch 1 back and forth a few times")


# Test switch 2
def test_switch_2():
    pin = Pin(PIN_SW_2, Pin.IN, Pin.PULL_UP)
    return wait_for_toggles(pin, "Switch switch 2 back and forth a few times")


# Test spool reed
def test_spool_reed():
    pin = Pin(PIN_SPOOL_RESET, Pin.IN, Pin.PULL_UP)
    return wait_for_toggles(pin, "Open and close the spool reed switch (use a magnet)")


# Test encoder
def test_encoder():
    pin_1 = Pin(PIN_ROT_ENC_1, Pin.IN, Pin.PULL_UP)
    pin_2 = Pin(PIN_ROT_ENC_2, Pin.IN, Pin.PULL_UP)
    pin_4 = Pin(PIN_ROT_ENC_4, Pin.IN, Pin.PULL_UP)
    pin_8 = Pin(PIN_ROT_ENC_8, Pin.IN, Pin.PULL_UP)

    def position():
        return 15 - pin_1.value() - 2 * pin_2.value() - 4 * pin_4.value() - 8 * pin_8.value()

    print("Rotate the encoder to position 0, then 1, then 2, up to 9 (60s timeout)")
    expected = 0
    last = None
    start = time.ticks_ms()
    while True:
        if time.ticks_diff(time.ticks_ms(), start) > 60 * 1000:
            print("Timed out waiting for position {}".format(expected))
            return False
        pos = position()
        if pos != last:
            last = pos
            print("Position: {}".format(pos))
            if pos == expected:
                if expected == 9:
                    return True
                print("Got {}, now go to {}".format(expected, expected + 1) if expected < 9 else "Got 9, done")
                expected += 1
        time.sleep_ms(10)


# Test photo interrupters
def test_photo_interrupters():
    en = Pin(PIN_EN_PHOTO_INTERRUPTER, Pin.OUT)
    home = Pin(PIN_PHOTO_INTERRUPTER_HOME, Pin.IN)
    reset_pi = Pin(PIN_PHOTO_INTERRUPTER_RESET, Pin.IN)
    en.on()
    time.sleep_ms(10)
    try:
        print("Block and unblock each photo interrupter")
        ok_home = wait_for_toggles(home, "Home photo interrupter", toggles=2)
        ok_reset = wait_for_toggles(reset_pi, "Reset photo interrupter", toggles=2)
    finally:
        en.off()
    return ok_home and ok_reset


# Test motor driver
def test_motor():
    # Plain digital signals to the H bridge:
    # LOW/LOW = stopped, LOW/HIGH = one direction, HIGH/LOW = other direction, HIGH/HIGH = stopped
    h_in1 = Pin(PIN_H_IN_1, Pin.OUT, value=0)
    h_in2 = Pin(PIN_H_IN_2, Pin.OUT, value=0)

    # The INA219 is needed to report motor current, fail if it can't be found.
    try:
        from ina219 import INA219
        i2c = I2C(I2C_BUS_ID, scl=Pin(PIN_SCL), sda=Pin(PIN_SDA))
        ina = INA219(SHUNT_OHMS, i2c)
        ina.configure(gain=INA219.GAIN_8_320MV)
    except Exception as e:
        print("INA219 init failed:", e)
        return False

    def drive(in1, in2, description):
        print(description)
        h_in1.value(in1)
        h_in2.value(in2)
        for _ in range(6):
            time.sleep(0.5)
            try:
                print("Current: {:.1f} mA".format(ina.current()))
            except Exception as e:
                print("ina error", e)

    try:
        drive(1, 0, "Driving forward for 3 seconds...")
        h_in1.value(0)
        h_in2.value(0)
        time.sleep(1)
        drive(0, 1, "Driving backward for 3 seconds...")
    finally:
        h_in1.value(0)
        h_in2.value(0)
    answer = input("Did the motor run forward and backward? (y/n): ").strip().lower()
    return answer == "y"


# Test I2C
def test_i2c():
    # Check RTC, EEPROM and current sensor can be found on the I2C bus
    i2c = I2C(I2C_BUS_ID, scl=Pin(PIN_SCL), sda=Pin(PIN_SDA))
    found = i2c.scan()
    print("I2C scan found: {}".format([hex(a) for a in found]))
    all_found = True
    for addr, name in [
        (I2C_ADDR_INA219, "INA219 current sensor"),
        (I2C_ADDR_EEPROM, "EEPROM"),
        (I2C_ADDR_RTC, "PCF8563 RTC"),
    ]:
        if addr in found:
            print("Found {} at {}".format(name, hex(addr)))
        else:
            print("MISSING {} at {}".format(name, hex(addr)))
            all_found = False

    return all_found


# Test UART
def test_uart():
    # UART0 is the "in" port (RPi side), UART1 is the "out" port.
    print("Jumper UART OUT to UART IN (TX_OUT GPIO{}->RX_IN GPIO{}, TX_IN GPIO{}->RX_OUT GPIO{}), or connect to a device that echoes.".format(
        PIN_UART_TX_OUT, PIN_UART_RX_IN, PIN_UART_TX_IN, PIN_UART_RX_OUT))
    uart_in = UART(UART_IN_ID, baudrate=9600, tx=Pin(PIN_UART_TX_IN), rx=Pin(PIN_UART_RX_IN))
    uart_out = UART(UART_OUT_ID, baudrate=9600, tx=Pin(PIN_UART_TX_OUT), rx=Pin(PIN_UART_RX_OUT))
    try:
        ok = True
        for tx_uart, rx_uart, description in [
            (uart_out, uart_in, "OUT -> IN"),
            (uart_in, uart_out, "IN -> OUT"),
        ]:
            message = b"uart-test"
            while rx_uart.any():
                rx_uart.read()
            tx_uart.write(message)
            time.sleep(0.2)
            received = rx_uart.read()
            print("{}: sent {}, received {}".format(description, message, received))
            if received != message:
                ok = False
        return ok
    finally:
        uart_in.deinit()
        uart_out.deinit()


def _sweep_servo(pin_number):
    en_6v = Pin(PIN_EN_6V, Pin.OUT)
    en_6v.on()
    time.sleep_ms(10)   # wait for 6V to stabilize
    servo = PWM(Pin(pin_number), freq=50)
    try:
        # 0 degrees ~= 0.5ms pulse, 180 degrees ~= 2.5ms pulse (of a 20ms period)
        for description, pulse_ms in [("0", 0.5), ("180", 2.5), ("90", 1.5)]:
            print("Driving to {} degrees".format(description))
            servo.duty_u16(int(pulse_ms / 20 * MAX_U16))
            time.sleep(1.5)
    finally:
        servo.duty_u16(0)
        en_6v.off()
    answer = input("Did the servo sweep? (y/n): ").strip().lower()
    return answer == "y"


# Test Servo 1
def test_servo_1():
    return _sweep_servo(PIN_SERVO_1)


# Test Servo 2
def test_servo_2():
    return _sweep_servo(PIN_SERVO_2)


# Test electromagnet release
def test_electromagnet():
    electromagnet = Pin(PIN_ELECTROMAGNET_RELEASE, Pin.OUT)
    try:
        for i in range(3):
            print("Electromagnet ON")
            electromagnet.on()
            time.sleep(0.5)
            print("Electromagnet OFF")
            electromagnet.off()
            time.sleep(1)
    finally:
        electromagnet.off()
    answer = input("Did the electromagnet pulse 3 times? (y/n): ").strip().lower()
    return answer == "y"


# Test analog PIR
def test_apir():
    # Check that we are getting an analog voltage from the sensor that is
    # about 0.5 of the full range.
    adc = ADC(PIR_APIR)
    print("Printing analog PIR level for 5 seconds, wave your hand in front of it to check it changes...")
    samples = []
    for _ in range(50):
        value = adc.read_u16()
        samples.append(value)
        print("{:5.1f}%".format(value / MAX_U16 * 100))
        time.sleep_ms(100)
    avg = sum(samples) / len(samples)
    print("Min: {:.1f}%, Max: {:.1f}%, Avg: {:.1f}%".format(
        min(samples) / MAX_U16 * 100, max(samples) / MAX_U16 * 100, avg / MAX_U16 * 100))
    answer = input("Did the level change when you waved, and idle around 50%? (y/n): ").strip().lower()
    return answer == "y"


tests = [
    ("Night/day switch", test_night_switch),
    ("Buzzer", test_buzzer),
    ("Switch 1", test_switch_1),
    ("Switch 2", test_switch_2),
    ("Spool reed", test_spool_reed),
    ("Encoder", test_encoder),
    ("Photo interrupters", test_photo_interrupters),
    ("Motor driver", test_motor),
    ("I2C", test_i2c),
    # ("UART", test_uart),
    ("Servo 1", test_servo_1),
    ("Servo 2", test_servo_2),
    ("Electromagnet release", test_electromagnet),
    ("Analog PIR", test_apir),
]

print("PCB hardware test")
print("Press Enter to run each test, 's' to skip. Ctrl+C fails the current test.")
for name, func in tests:
    run_test(name, func)

print("")
print("======== Summary ========")
failed = 0
for name, _ in tests:
    result = results.get(name, "SKIP")
    if result == "FAIL":
        failed += 1
    print("{:24s} {}".format(name, result))
print("")
if failed:
    print("{} test(s) FAILED".format(failed))
else:
    print("All run tests passed")
