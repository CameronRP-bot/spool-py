import _thread
import binascii
import datetime
import hashlib
import io
import json
import os
import sys
import time

import deflate
from machine import ADC, I2C, PWM, UART, Pin, reset

import pcf8563
import timezone
from config import *
from ina219 import INA219

MAX_U16 = 65535

sw_ignore = "ignore"
sw_open = "open"
sw_closed = "closed"
sw_and = "and"
sw_or = "or"

user_config = UserConfig()

i2c = I2C(I2C_BUS_ID, scl=Pin(PIN_SCL), sda=Pin(PIN_SDA))

class Spool:
    def __init__(self, rpi_uart=None):
        # H-Bridge driver pins, set frequency and set to 0
        self.h_in1 = PWM(Pin(PIN_H_IN_1), freq=20000)
        self.h_in1.duty_u16(0)
        self.h_in2 = PWM(Pin(PIN_H_IN_2), freq=20000)
        self.h_in2.duty_u16(0)
        self.direction = "stop"
        self.rpi_uart = rpi_uart
        self.spool_reset_pin = Pin(PIN_SPOOL_RESET, Pin.IN, Pin.PULL_UP)

        # Photointerrupter pins, set power to off.
        self.en_photo_interrupter = Pin(PIN_EN_PHOTO_INTERRUPTER, Pin.OUT)
        self.en_photo_interrupter.off()
        self.photo_interrupter_home = Pin(PIN_PHOTO_INTERRUPTER_HOME, Pin.IN)
        self.photo_interrupter_reset = Pin(PIN_PHOTO_INTERRUPTER_RESET, Pin.IN)

        # Electromagnet pins, set to off
        self.electromagnet_en_pin = Pin(PIN_ELECTROMAGNET_RELEASE, Pin.OUT)
        self.electromagnet_en_pin.off()

        # First guess for reset duration.
        self.home_to_reset_duration = HOME_TO_RESET_DURATION

        # _at_home is set to True when the spool reaches home and will only be unset when the spool is moved away from home.
        # This is to prevent slight movement in the spool making the photo interrupter think it is not at home anymore, preventing 
        # the trap from triggering.
        self._at_home = False

        # Current sensor
        self.ina219 = INA219(SHUNT_OHMS, i2c)
        self.ina219.configure(gain = INA219.GAIN_8_320MV)

        # Buzzer
        self.buzzer = Buzzer()

    def stop(self):
        # Writing both values to high will set the motor driver into "break/stop" mode.
        self.h_in1.duty_u16(0)
        self.h_in2.duty_u16(0)
        self.speed = 0
        self.direction = "stop"

    def enable_check(self):
        if self.at_home():
            return True, ""
        else:
            return False, "spool not home"

    # _drive_cw is towards reset
    def _drive_cw(self, speed=100):
        self._at_home = False
        if self.at_reset():
            self.stop()
            return
        if self.direction == "cw" and self.speed == speed:
            # Nothing to do here. Don't set the duty cycle again, 
            # setting it multiple times in quick succession can have a bad affect
            return
        self.h_in1.duty_u16(int(speed * MAX_U16 / 100))
        self.h_in2.duty_u16(0)
        self.speed = speed
        self.direction = "cw"

    # _drive_ccw is towards home
    def _drive_ccw(self, speed=100):
        self._at_home = False
        if self.at_home():
            self.stop()
            return
        if self.direction == "ccw" and self.speed == speed:
            # Nothing to do here. Don't set the duty cycle again, 
            # setting it multiple times in quick succession can have a bad affect
            return
        self.h_in2.duty_u16(int(speed * MAX_U16 / 100))
        self.h_in1.duty_u16(0)
        self.speed = speed
        self.direction = "ccw"

    def at_home(self):
        # If we are already at home, don't check the photo interrupter
        if self._at_home:
            return True

        self._at_home = self._check_position(self.photo_interrupter_home)

        return self._at_home

    def at_reset(self):
        return self._check_position(self.photo_interrupter_reset)

    def _check_position(self, position):
        # If the photo interrupter is off it can give a false positive, 
        # but not a false negative so we check the negative first.

        # First check if we are not at the position, this can't be a false negative.
        if position.value() == 0:
            return False

        # Turn on photo interrupter and check
        self.en_photo_interrupter.on()
        time.sleep_us(100)
        at_position = position.value() == 1
        self.en_photo_interrupter.off()
        return at_position

    def spool_is_reset(self):
        # When the spool is reset the reed switch will be close pulling the pin low
        return self.spool_reset_pin.value() == 0

    def reset_sequence(self, steps=4):
        print("======== Running reset sequence ========")
        
        # Stop and then move to home to start the reset sequence.
        self.stop()
        time.sleep(0.5)
        self.move_to_home()
        time.sleep(0.5)

        # Check if the spool is already reset.
        if user_config.spool_reed_check and self.spool_is_reset():
            print("Spool already reset")
            return

        # For the reset sequence rather than making it move directly to reset we make multiple 
        # "steps", each time returning back to home and then moving further next time.
        # This is to help clear out the blinds of dirt and such.
        step_size = self.home_to_reset_duration/steps
        steps = steps -1 # -1 because we always do the last step (to reset)
        for i in range(steps):
            sleep_duration = step_size*(i+1)
            self.move_to_reset(timeout=sleep_duration, timeout_error=False)
            time.sleep(0.5)
            self.move_to_home()
            time.sleep(0.5)

        start_time = time.time()
        self.move_to_reset(timeout=self.home_to_reset_duration+5, timeout_error=True) # Give it 5 more seconds than expected in case it is a bit slow for some reason
        self.home_to_reset_duration = time.time() - start_time  # Update how long it takes to move from home to reset
        print("Time to reset spool: ", self.home_to_reset_duration)
        time.sleep(0.5)

        # Move back to home and check if the reed switch shows that it didn't latch properly.
        print("Moving to home, checking the spool stays reset.")
        self._drive_ccw()
        self._wait_to_stop_spool(
            self.at_home, # Check if it has got to the target
            self.home_to_reset_duration+5, # Give it 5 more seconds than expected in case it is a bit slow for some reason
            True, # Error if it takes longer than expected
            reed_check=user_config.spool_reed_check) # Check reed switch if configured to do so.

        # Make event that the trap has been released
        if self.rpi_uart is not None:
            self.rpi_uart.send_message(Message(0, "SPOOL_RESET"))
        print("Finished reset sequence =================")

    def move_to_reset(self, timeout: float = 15, timeout_error=True):
        print("Moving to reset")
        if self.at_reset():
            print("Already at reset")
            return True
        self._drive_cw()
        return self._wait_to_stop_spool(self.at_reset, timeout, timeout_error)

    def move_to_home(self, timeout=15, timeout_error=True):
        print("Moving to home")
        if self.at_home():
            print("Already at home")
            return True
        self._drive_ccw()
        return self._wait_to_stop_spool(self.at_home, timeout, timeout_error)

    def release(self):
        # It is only safe to trigger the trap if the spool has made it back to the home position.
        if not self.at_home():
            return False

        # At home position so it is safe to release the trap.
        self.electromagnet_en_pin.on()
        time.sleep(0.5)
        self.electromagnet_en_pin.off()

        # Make event that the trap has been released
        if self.rpi_uart is not None:
            self.rpi_uart.send_message(Message(0, "TRIGGERED"))

        if user_config.spool_reed_check and self.spool_is_reset():
            # The reset reed should not read it as still being reset
            error_code(ERROR_SPOOL_NOT_RELEASING)

        return True

    def _check_manual_mode(self):
        # Raise ManualMode if a request has come in over UART. The spool is stopped
        # first, as the sequence is unwound from wherever it is up to and would
        # otherwise leave the motor driving.
        if self.rpi_uart is None:
            return
        try:
            check_manual_mode(self.rpi_uart.shared_dict)
        except ManualMode:
            self.stop()
            self.ina219.sleep()
            raise

    def _wait_to_stop_spool(self, checker_function, timeout, error_on_timeout, reed_check=False):
        start_time = time.time()
        self.ina219.wake()
        avg = RingAvg(30)
        max_avg_current = 0
        max_current = 0
        while True:
            # Check if it has got to the target
            if checker_function():
                self.stop()
                print("Finished move. Reason: Got to target")
                self.ina219.sleep()
                print("Max current ", max_current)
                print("Max average current ", max_avg_current)
                return True

            # Timeout on moving.
            if time.time() - start_time > timeout:
                self.stop()
                print("Finished move. Reason: Timed out")
                if error_on_timeout:
                    error_code(ERROR_MOVEMENT_TIMEOUT)
                self.ina219.sleep()
                return False

            # Check if we have been asked to take manual control of the trap.
            self._check_manual_mode()
            
            # Check reed switch
            if reed_check:
                # We want to check that spool is staying reset.
                if not self.spool_is_reset():
                    print("Spool didn't reset properly.")
                    self.stop()
                    error_code(ERROR_FAILED_TO_RESET)
                    self.ina219.sleep()
                    return False

            # Check current
            try:
                current = self.ina219.current()
                if current > max_current:
                    max_current = current
                avg.add(abs(current))
                avg_current = avg.avg()
                if avg_current > max_avg_current:
                    max_avg_current = avg_current
            except Exception as e:
                print("ina error", e)
            if avg.avg() > user_config.max_current:
                self.stop()
                print("Finished move. Reason: Over current")
                error_code(ERROR_OVER_CURRENT)
                self.ina219.sleep()
                return False

class Switches:
    def __init__(self):
        # Init switches. The switches when closed will connect them to ground. So we set them up with PULL_UP
        self.sw1 = Pin(PIN_SW_1, Pin.IN, Pin.PULL_UP)
        self.sw2 = Pin(PIN_SW_2, Pin.IN, Pin.PULL_UP)
        self.sw1_disable_when = user_config.switch_1_disable.lower()
        self.sw2_disable_when = user_config.switch_2_disable.lower()
        self.sw_logic = user_config.switch_logic.lower()
        # Check valid configuration.
        if self.sw1_disable_when not in [sw_closed, sw_open, sw_ignore]:
            raise ValueError("SWITCH1_DISABLE must be either 'OPEN', 'CLOSED', or 'IGNORE'")
        if self.sw2_disable_when not in [sw_closed, sw_open, sw_ignore]:
            raise ValueError("SWITCH2_DISABLE must be either 'OPEN' or 'CLOSED' or 'IGNORE'")
        if self.sw_logic not in [sw_and, sw_or]:
            raise ValueError("SWITCH_LOGIC must be either 'AND' or 'OR'")

    def enable_check(self):
        # Check if switch 1 wants trap to be disabled
        sw1_disabled = False
        if self.sw1_disable_when != sw_ignore:
            sw1_state = self.sw1.value()
            if sw1_state == 1 and self.sw1_disable_when == sw_open:
                sw1_disabled = True
            if sw1_state == 0 and self.sw1_disable_when == sw_closed:
                sw1_disabled = True
        # Check if switch 2 wants trap to be disabled
        sw2_disabled = False
        if self.sw2_disable_when != sw_ignore:
            sw2_state = self.sw2.value()
            if sw2_state == 1 and self.sw1_disable_when == sw_open:
                sw2_disabled = True
            if sw2_state == 0 and self.sw1_disable_when == sw_closed:
                sw2_disabled = True
        # Check if the trap should be disabled based on switch logic
        if self.sw_logic == sw_and:
            disabled = sw1_disabled and sw2_disabled
        if self.sw_logic == sw_or:
            disabled = sw1_disabled or sw2_disabled
        if disabled:
            return False, "switches"

        # If we get here then nothing is disabling the trap
        return True, ""


class RingAvg:
    def __init__(self, size):
        assert size > 0
        self.size = size
        self.buf = [0.0] * size   # preallocate (use array('f') if you like)
        self.sum = 0.0
        self.count = 0            # how many valid samples (<= n)
        self.idx = 0              # next write index

    def add(self, x):
        x = float(x)
        if self.count < self.size:
            # still filling
            self.buf[self.idx] = x
            self.sum += x
            self.count += 1
        else:
            # overwrite oldest
            old = self.buf[self.idx]
            self.buf[self.idx] = x
            self.sum += x - old
        self.idx += 1
        if self.idx == self.size:    # faster than % in many ports
            self.idx = 0

    def avg(self):
        return self.sum / self.size

class Buzzer:
    def __init__(self):
        self.pwm_instance = PWM(Pin(PIN_BUZZER))
        self.off()

    def on(self):
        self.pwm(1000, 50)

    def off(self):
        self.pwm(1000, 0)

    def pwm(self, freq, duty):
        self.pwm_instance.freq(freq)
        self.pwm_instance.duty_u16(int(duty * MAX_U16 / 100))

    def beep_trap_ready(self):
        for i in range(5):
            time.sleep(0.5)
            self.on()
            time.sleep(0.5)
            self.off()
        print("Trap is ready.")

class RotaryEncoder:
    def __init__(self):
        self.pin_1 = Pin(PIN_ROT_ENC_1, Pin.IN, Pin.PULL_UP)
        self.pin_2 = Pin(PIN_ROT_ENC_2, Pin.IN, Pin.PULL_UP)
        self.pin_4 = Pin(PIN_ROT_ENC_4, Pin.IN, Pin.PULL_UP)
        self.pin_8 = Pin(PIN_ROT_ENC_8, Pin.IN, Pin.PULL_UP)

    def position(self):
        return 15 - self.pin_1.value() - 2*self.pin_2.value() - 4*self.pin_4.value() - 8*self.pin_8.value()

class Clock:
    def __init__(self, i2c=i2c):
        self.r = pcf8563.PCF8563(i2c)
        self.latitude = user_config.latitude
        self.longitude = user_config.longitude
        dst = timezone.time_change_rule(-1, 6, 9, 2, 780)
        st = timezone.time_change_rule(0, 6, 4, 2, 720)
        self.nz_tz = timezone.timezone(dst, st)
        self.night_only = Pin(PIN_SW_NIGHT_ONLY, Pin.IN, Pin.PULL_UP)

    def get_local_time(self, utc_time=None):
        if utc_time is None:
            utc_time = self.get_utc_time()
        return self.nz_tz.get_local_time(utc_time)

    def write_time(self, **kwargs):
        self.r.write_all(**kwargs)

    def get_utc_time(self):
        year, month, date, day, hour, minute, second = self.r.datetime()
        return datetime.datetime(
            year=year + 2000,
            month=month,
            day=date,
            hour=hour,
            minute=minute,
            second=second,
        )

    def is_night(self):
        utc = self.get_utc_time()
        local_time = self.get_local_time(utc)
        tz = self.nz_tz.get_current_tz(utc).timezone  # pyright: ignore[reportOptionalMemberAccess]
        sunrise = timezone.get_sunrise(utc, user_config.latitude, user_config.longitude, tz)
        sunset = timezone.get_sunset(utc, user_config.latitude, user_config.longitude, tz)
        return local_time.time() < sunrise or sunset < local_time.time()

    def in_active_window(self):
        # If night time mode is enabled check if it is night, else return true.
        if self.night_only.value() == 1:
            return self.is_night()
        return True

    def enable_check(self):
        if self.in_active_window():
            return True, ""
        else:
            return False, "time window"

    def check_low_voltage(self):
        return self.r.check_low_voltage()

# class PIRs:
#     def __init__(self, i2c=i2c):
#         self.i2c = i2c
#         self.pir_1 = Pin(PIN_PIR_1, Pin.IN)
#         self.pir_2 = Pin(PIN_PIR_2, Pin.IN)
#         self.set_pir_sensitivity(PIR_SENSITIVITY)

#     def read(self):
#         return self.pir_1.value() or self.pir_2.value()

#     def read_sensitivity(self):
#         return self.pir_sensitivity.read()

#     def set_pir_sensitivity(self, value):
#         value = 127 - value
#         bytearray(0) + bytearray([value])
#         if value >= 128:
#             value = 128
#         if value < 0:
#             value = 0
#         # Writing to a programmable POT as a way to set the sensitivity for the PIRs
#         self.i2c.writeto(0x3E, bytes([0, value]))

class SharedDict:
    def __init__(self):
        self._data = {}
        self._lock = _thread.allocate_lock()

    def get(self, key, default=None):
        self._lock.acquire()
        try:
            return self._data.get(key, default)
        finally:
            self._lock.release()

    def set(self, key, value, new_key=False):
        self._lock.acquire()
        try:
            if key not in self._data and not new_key:
                return False
            self._data[key] = value
            return True
        finally:
            self._lock.release()


    def contains(self, key):
        self._lock.acquire()
        try:
            return key in self._data
        finally:
            self._lock.release()

    def enable_check(self):
        if self.get("enable", default=False):
            return True, "Camera set trap to enabled"
        else:
            return False, "Camera set trap to disabled"

class RPi_UART:
    def __init__(self, shared_dict: SharedDict, i2c = None):
        self.shared_dict = shared_dict
        self._running = True
        self.uart = UART(0, baudrate=9600, tx=Pin(PIN_UART_TX_IN), rx=Pin(PIN_UART_RX_IN))
        self.i2c = i2c
        _thread.start_new_thread(self._uart_loop, ())

    def close(self):
        self._running = False
        self.uart.deinit()

    def _uart_loop(self):
        while self._running:
            try:
                # Get a new message
                message = self.check_for_message()

                # Ignore if no message
                if message is None:
                    continue

                print(f"Received {message.type} message")

                # Process the message
                if message.type == "ACK":
                    # TODO figure out what we want to do in this situation.
                    continue
                
                elif message.type == "NACK":
                    # TODO figure out what we want to do in this situation.
                    continue

                elif message.type == "ENABLE":
                    # We will write to the shared dict to set enable to true.
                    if self.shared_dict.set("enable", True):
                        self.send_ack(message.id)
                    else:
                        self.send_bad_key(message.id)

                elif message.type == "DISABLE":
                    # We will write to the shared dict to set enable to false.
                    if self.shared_dict.set("enable", False):
                        self.send_ack(message.id)
                    else:
                        self.send_bad_key(message.id)

                elif message.type in (
                    "STOP",
                    "RELEASE_SPOOL",
                    "RESET_SPOOL",
                    "OPEN_DOOR_1",
                    "CLOSE_DOOR_1",
                    "OPEN_DOOR_2",
                    "CLOSE_DOOR_2",
                ):
                    # Only record the request. It is run by the main thread, which puts
                    # the trap into manual mode. The ACK means the request was accepted,
                    # not that it has finished, the SPOOL_RESET/TRIGGERED and
                    # DOOR_OPENED/DOOR_CLOSED messages report that. Programs opt in to
                    # manual control by seeding the "request" key.
                    # A request also interrupts one that is already running, which is how
                    # STOP stops a spool or door that is part way through moving.
                    if self.shared_dict is not None and self.shared_dict.set("request", message.type):
                        self.send_ack(message.id)
                    else:
                        self.send_bad_key(message.id)

                elif message.type == "RESTART":
                    print("Restarting..")
                    self.send_ack(message.id)
                    time.sleep(1)
                    reset()

                elif message.type == "LS":
                    # TODO: Only get wanted files
                    if message.payload == "":
                        all_files = get_file_hashes()
                        payload = json.dumps(all_files)
                        print(payload)
                        self.send_message(Message(message.id, "LS", payload))
                        continue

                    files = get_file_hashes(target_files=message.payload.split(","))
                    payload = json.dumps(files)
                    print(payload)
                    self.send_message(Message(message.id, "LS", payload))

                elif message.type == "READ_TIME":
                    if self.i2c is None:
                        self.send_nack(message.id, "No shared I2C object")
                        continue
                    clock = Clock(self.i2c)
                    utc_time = clock.get_utc_time().isoformat()
                    local_time = clock.get_local_time().isoformat()
                    self.send_message(DictMessage(message.id, "READ_TIME_R", {"UTC": utc_time, "Local": local_time}))

                elif message.type == "WRITE_TIME":
                    if self.i2c is None:
                        self.send_nack(message.id, "No shared I2C object")
                        continue
                    clock = Clock(self.i2c)
                    try: 
                        dt = datetime.datetime.fromisoformat(message.payload)
                        print(dt.isoformat())
                        clock.write_time(
                            year= dt.year%1000,
                            month= dt.month,
                            date= dt.day,
                            hours= dt.hour,
                            minutes= dt.minute,
                            seconds= dt.second
                        )
                        self.send_ack(message.id)
                    except Exception as e:
                        print(get_err_str(e))
                        self.send_nack(message.id, "Invalid time format")

                elif message.type == "READ":
                    parts = message.payload.split(",")
                    filename = parts[0]
                    offset = int(parts[1])
                    count = int(parts[2])
                    lines = read_file(filename, offset, count)
                    self.send_message(Message(message.id, "READ", json.dumps(lines)))

                elif message.type == "WRITE":
                    parts = message.payload.split(",", 1)
                    filename = parts[0]
                    lines = json.loads(parts[1])

                    with open(filename, "a") as f:
                        for line in lines:
                            f.write(line+"\n")
                    self.send_ack(message.id)

                elif message.type == "DELETE":
                    filename = message.payload
                    os.remove(filename)
                    self.send_ack(message.id)

                elif message.type == "DELETE_TMP":
                    # Discard a half finished transfer: the counterpart of COMMIT,
                    # which renames the same files instead of deleting them.
                    try:
                        for f in os.listdir():
                            if f.endswith(".tmp"):
                                print("Deleting", f)
                                os.remove(f)
                        self.send_ack(message.id)
                    except Exception as e:
                        print("DELETE_TMP failed:", e)
                        self.send_nack(message.id)

                elif message.type == "DECOMPRESS":
                    parts = message.payload.split(",")
                    src = parts[0]
                    dst = parts[1]
                    bin_src = src + ".bin"
                    try:
                        # Decode base64 line by line to avoid holding all data in memory at once
                        with open(src, "rb") as f_in, open(bin_src, "wb") as f_out:
                            for line in f_in:
                                line = line.strip()
                                if line:
                                    f_out.write(binascii.a2b_base64(line))
                        # Stream decompress directly to the destination
                        with open(bin_src, "rb") as f_in, open(dst, "wb") as f_out:
                            try:
                                with deflate.DeflateIO(f_in, deflate.RAW, 8) as d:  # pyright: ignore[reportGeneralTypeIssues]
                                    while True:
                                        chunk = d.read(256)
                                        if not chunk:
                                            break
                                        f_out.write(chunk)
                            except EOFError:
                                pass
                        # Only remove temp files after successful decompression
                        os.remove(src)
                        os.remove(bin_src)
                        self.send_ack(message.id)
                    except Exception as e:
                        print("DECOMPRESS failed:", e)
                        # Remove partial output and binary temp, but keep src so the retry can reuse it
                        for path in [bin_src, dst]:
                            try:
                                os.remove(path)
                            except:
                                pass
                        self.send_nack(message.id)

                elif message.type == "MV":
                    parts = message.payload.split(",")
                    src = parts[0]
                    dst = parts[1]
                    os.rename(src, dst)
                    self.send_ack(message.id)

                elif message.type == "COMMIT":
                    try:
                        for f in os.listdir():
                            if f.endswith(".tmp"):
                                os.rename(f, f[:-4])
                        self.send_ack(message.id)
                    except Exception as e:
                        print("COMMIT failed:", e)
                        self.send_nack(message.id)

                # TODO: Run program (filename) -> ACK

                # TODO: Testing
                elif message.type == "PING":
                    self.send_ack(message.id)

                else:
                    print("Received unknown message type: {}".format(message.type))
                    self.send_nack(message.id)

            except Exception as e:
                print(get_err_str(e))

    def check_for_message(self):
        # Check to see if there is any data in the UART buffer, if not return None
        if not self.uart.any():
            return None
        
        # There is some data so lets read the full line.
        # TODO: Timeout of reading the whole line
        line_raw = bytearray()
        while True:
            if self.uart.any():
                char = self.uart.read(1)
                if char == b"\n":
                    break
                if char != None:
                    line_raw.extend(char)
        try:
            line = line_raw.decode('utf-8')
        except:
            self.send_nack(payload="Failed to decode line")
            return None
        
        # Split from the last '>' to get the message and the checksum
        last_index = line.rfind('>')
        if last_index < 0:
            self.send_nack(payload="Invalid message format")
            return None
        message_str = line[:last_index+1]
        checksum = line[last_index+1:]
        
        # Check the checksum
        try:
            if self._compute_checksum(message_str) != int(checksum):
                self.send_nack(payload="Invalid checksum")
                return None
        except ValueError:
            self.send_nack(payload="Failed to send message")
            return None



        # Check that we get the message in the correct format "<id|type|payload>"
        if not message_str.startswith('<') or message_str.count('|') < 2 or not message_str.endswith('>'):
            print(f"Invalid message format {message_str}")
            self.send_nack(payload="Invalid message format")
            return None
        
        message_str = message_str[1:-1] # Remove the < and >
        parts = message_str.split("|") # Split the message into components
        id = int(parts[0])    # Get the ID
        type = parts[1]       # Get the type
        payload = '|'.join(parts[2:]) # Get the payload, joining back in any split '|'

        message = Message(id, type, payload)
        return message        

    CHUNK_SIZE = 256

    def send_message(self, message):
        message_str = f"<{message.id}|{message.type}|{message.payload}>"
        checksum = self._compute_checksum(message_str)
        line = f"{message_str}{checksum}\n"
        print(f"Sending: {line}")
        for i in range(0, len(line), self.CHUNK_SIZE):
            self.uart.flush()
            self.uart.write(line[i:i+self.CHUNK_SIZE])

    def _compute_checksum(self, message):
        return sum(message.encode()) % 256

    def send_nack(self, message_id=0, payload=""):
        self.send_message(Message(message_id, "NACK", payload))
    
    def send_ack(self, message_id=0):
        self.send_message(Message(message_id, "ACK"))
    
    def send_error_code(self, error_id):
        self.send_message(Message(0, "ERROR", error_id))
    
    def send_bad_key(self, message_id=0):
        self.send_message(Message(message_id, "BAD_KEY"))

class Message():
    def __init__(self, id, type, payload = ""):
        self.id = id
        self.type = type
        self.payload = payload
        print("New message, id: {}, type: {}, payload: {}".format(self.id, self.type, self.payload))

class DictMessage(Message):
    # A Message whose payload is a dict. The wire format only carries strings,
    # so the dict is JSON encoded here rather than at each call site.
    def __init__(self, id, type, payload: dict):
        super().__init__(id, type, json.dumps(payload))

def motion_message():
    return Message(0, "MOTION")

class RatchetDoor():
    # NOTE: Both doors share the one PIN_EN_6V rail, so only ever move one at a time.
    # Manual mode serves a single request at a time, and each move powers the rail down
    # before returning, so the two doors never contend for it.
    def __init__(self, pin, number, rpi_uart=None):
        self.number = number
        self.en_6v = Pin(PIN_EN_6V, Pin.OUT)
        self.en_6v.off()
        self.servo = PWM(Pin(pin), freq=50)
        self.servo.duty_u16(0)
        self.rpi_uart = rpi_uart

    def _move_to(self, pulse_us):
        self.servo.duty_u16(int(pulse_us / 20_000 * MAX_U16))

    def _power_on(self):
        self.en_6v.on()
        time.sleep_ms(10)  # wait for 6V to stabilize

    def _power_off(self):
        self.servo.duty_u16(0)
        self.en_6v.off()

    # stop cuts the power to the door, leaving it wherever it has got to.
    def stop(self):
        self._power_off()

    def _shared_dict(self):
        return self.rpi_uart.shared_dict if self.rpi_uart is not None else None

    def _check_stop(self):
        # Raise ManualMode if a request (a STOP, or anything else) is waiting, so a move
        # that takes tens of seconds doesn't have to be waited out. The power off in the
        # caller's finally block leaves the door where it stopped.
        check_manual_mode(self._shared_dict())

    def _sleep(self, seconds):
        sleep_checking_manual_mode(seconds, self._shared_dict(), slice_seconds=0.1)

    # reset() is the "open" movement: it ratchets the door up and holds it there.
    def reset(self):
        print("Opening ratchet door", self.number)
        self._power_on()
        try:
            # Move the servo up and down to ratchet the door open
            for _ in range(RATCHET_CYCLES):
                self._check_stop()
                self._move_to(SERVO_DOOR_DOWN_RATCHET)
                self._sleep(1)
                self._move_to(SERVO_DOOR_UP_RATCHET)
                self._sleep(1)

            # Slowly move to the hold positions to prevent a accidental release
            steps = 100
            for i in range(steps):
                self._sleep(0.02)
                position = SERVO_DOOR_UP_RATCHET + (SERVO_DOOR_HOLD - SERVO_DOOR_UP_RATCHET) * i / steps
                self._move_to(position)
            self._move_to(SERVO_DOOR_HOLD)
            self._sleep(0.6)
        finally:
            self._power_off()

        # Make event that the door has been opened
        if self.rpi_uart is not None:
            self.rpi_uart.send_message(Message(0, "DOOR_OPENED", str(self.number)))
        print("Finished opening ratchet door", self.number)

    # release() is the "close" movement: it lets the ratchet go and the door drops.
    def release(self):
        print("Closing ratchet door", self.number)
        self._power_on()
        try:
            self._move_to(SERVO_DOOR_RELEASE)
            time.sleep(0.6)
            self._move_to(SERVO_DOOR_HOLD)
            time.sleep(0.6)
        finally:
            self._power_off()

        # Make event that the door has been closed
        if self.rpi_uart is not None:
            self.rpi_uart.send_message(Message(0, "DOOR_CLOSED", str(self.number)))
        print("Finished closing ratchet door", self.number)

class APIR():
    def __init__(self):
        self.AnalogPin = ADC(PIR_APIR)
        self.min = 0
        self.max = 43_000
        self.avg = (self.min + self.max)/2
        self.displacement_threshold = (self.max - self.min)/2*user_config.apir_d_threshold # 50%
        self.gradient_threshold = user_config.apir_dt_threshold
        self.previous_value = self.AnalogPin.read_u16()
        self.last_time = time.time_ns()
        self.displacement_triggered = False
        self.gradient_triggered = False
        self.d_val = 0
        self.dt_val = 0

    def motion(self):
        # Prevent updating too frequently, 0.5ms
        if time.time_ns() - self.last_time < 1_000_000:
            return self.displacement_triggered or self.gradient_triggered

        new_value = self.AnalogPin.read_u16()
        # print(new_value)
        new_time = time.time_ns()

        # Check if the new value meets the displacement threshold
        self.d_val = abs(new_value - self.avg)
        self.displacement_triggered = self.d_val > self.displacement_threshold

        # Check if the new value meets the gradient threshold
        self.dt_val = abs((new_value - self.previous_value) / (new_time - self.last_time) * 1_000_000)
        self.gradient_triggered = self.dt_val > self.gradient_threshold
        # print(gradient)
        # print(self.gradient_triggered)

        self.previous_value = new_value
        self.last_time = new_time

        # Return if there was motion
        return self.displacement_triggered or self.gradient_triggered
  
class ManualMode(Exception):
    """Raised when a request to control the trap has come in over UART.

    Requests are only recorded by the UART thread, never acted on there, as the spool
    must only be driven from the main thread. Raising from the sequence unwinds it to
    a single handler in run_sequence, so no part of the sequence has to know what to
    do with a request. See manual_mode().
    """
    pass


def check_manual_mode(shared_dict):
    # Raise ManualMode if a request is waiting to be handled.
    if shared_dict is not None and shared_dict.get("request") is not None:
        raise ManualMode()


def sleep_checking_manual_mode(seconds, shared_dict, slice_seconds=0.5):
    # time.sleep, but in slices, so a request doesn't have to wait out the full sleep.
    # Timed with ticks_ms as time.time() only has second resolution, which would make
    # sleeps of a second or less either return straight away or run long.
    total_ms = int(seconds * 1000)
    slice_ms = max(1, int(slice_seconds * 1000))
    start = time.ticks_ms()
    while True:
        remaining_ms = total_ms - time.ticks_diff(time.ticks_ms(), start)
        if remaining_ms <= 0:
            return
        check_manual_mode(shared_dict)
        time.sleep_ms(min(slice_ms, remaining_ms))


def check_checks(enable_checks):
    failed_reasons = []
    all_passed = True
    for check in enable_checks:
        check_passed, reason = check()
        if not check_passed:
            all_passed = False
            failed_reasons.append(reason)
    return all_passed, ', '.join(failed_reasons)

# run_sequence takes the spool, motion_check, enable_checks, rpi_uart and from that can run
# through a trap sequence.
# This sequence is:
# 1) Reset spool
# 2) Wait for motion check and all enable checks to pass.
#   2a) If motion is detected or the enable checks failing change then make a event reporting this.
# 3) Release spool.
# 4) Wait for SPOOL_RESET_DELAY_MINUTES
# 5) Back to step 1, resetting the spool
def run_sequence(
    spool: Spool,
    motion_check,
    enabled_checks,
    rpi_uart=None,
    apir=None
    ):
    shared_dict = rpi_uart.shared_dict if rpi_uart is not None else None
    try:
        _run_sequence(spool, motion_check, enabled_checks, shared_dict, rpi_uart, apir)
    except ManualMode:
        # A request came in over UART. Hand the trap over to manual mode, which doesn't
        # return, so the sequence is abandoned rather than resumed part way through.
        manual_mode(spool, shared_dict, rpi_uart=rpi_uart)

def _run_sequence(
    spool: Spool,
    motion_check,
    enabled_checks,
    shared_dict,
    rpi_uart=None,
    apir=None
    ):
    while True:
        # Step 1: Reset spool
        print("Resetting spool.")
        spool.reset_sequence()
        print(f"Waiting {user_config.post_reset_cooldown_seconds}s until running trap checks.")
        sleep_checking_manual_mode(user_config.post_reset_cooldown_seconds, shared_dict)

        # Step 2: Wait for motion check and all enable checks to pass.
        print("Waiting for motion check and all enable checks to pass.")
        last_motion_message = -user_config.motion_message_gap
        old_enabled = None  # Track previous enabled state so we can log changes.
        old_state = None
        old_failed_check_reasons = None
        apir_max_dt = 0
        apir_max_d = 0
        apir_min = float('inf')
        apir_max = 0
        while True:
            # Check if we have been asked to take manual control of the trap.
            check_manual_mode(shared_dict)

            # Check for motion.
            motion = motion_check()

            # Send a motion message if one hasn't been sent recently.
            now = time.time()
            if motion and last_motion_message + user_config.motion_message_gap < now:
                if rpi_uart:
                    rpi_uart.send_message(motion_message())
                last_motion_message = now

            # Check the enabled state
            enabled, failed_check_reasons = check_checks(enabled_checks)

            if old_enabled != enabled:
                if enabled:
                    # Going from disabled to enabled, or first check while enabled.
                    apir_max_dt = 0
                    apir_max_d = 0
                    apir_min = float('inf')
                    apir_max = 0
                    if rpi_uart:
                        rpi_uart.send_message(Message(0, "ENABLED"))
                elif old_enabled is not None:
                    # Going from enabled to disabled
                    if rpi_uart and apir:
                        rpi_uart.send_message(Message(0, "MAX_MOTION", f"[{apir_max_dt}, {apir_max_d}, {apir_min}, {apir_max}]"))
            old_enabled = enabled

            if enabled and apir:
                apir_max_dt = max(apir_max_dt, apir.dt_val)
                apir_max_d = max(apir_max_d, apir.d_val)
                apir_min = min(apir_min, apir.previous_value)
                apir_max = max(apir_max, apir.previous_value)

            # Send message if the disabled reasons change changed
            if not enabled and failed_check_reasons != old_failed_check_reasons:
                if rpi_uart:
                    rpi_uart.send_message(Message(0, "DISABLED", failed_check_reasons))
                else:
                    print(failed_check_reasons)
            old_failed_check_reasons = failed_check_reasons


            if motion and enabled:
                # Break out of loop to trigger spool release
                break
            
            # Print a change in state
            state = f"Motion: {motion}, Enabled: {enabled}"
            if state != old_state:
                print(state)
                old_state = state
            
        # Step 3: Release spool.
        print("Releasing spool.")
        spool.release()

        # Step 4: Wait for SPOOL_RESET_DELAY_MINUTES
        print(f"Waiting {user_config.spool_reset_delay_minutes} minutes until resetting.")
        sleep_checking_manual_mode(user_config.spool_reset_delay_minutes * 60, shared_dict)

        # Step 5: Back to step 1, resetting the spool

# manual_mode takes over from the trap sequence when a request comes in over UART.
# The sequence is not resumed: requests are served until the trap is restarted, either
# by a RESTART message or by the manual mode timeout, both of which reboot back into
# the program from a known state.
def manual_mode(spool: Spool, shared_dict, rpi_uart=None):
    # The sequence could have been unwound from anywhere, so put the spool in a known
    # state before doing anything else.
    spool.stop()

    # Doors are built the first time one is asked for, so a trap that never gets a door
    # request doesn't claim the servo pins or the 6V enable.
    doors = {}

    def get_door(number):
        if number not in doors:
            pin = PIN_SERVO_1 if number == 1 else PIN_SERVO_2
            doors[number] = RatchetDoor(pin, number, rpi_uart=rpi_uart)
        return doors[number]

    def stop_all():
        # Stop anything that could still be moving. Doors that have never been asked for
        # are not built, so only the ones that exist need powering down.
        spool.stop()
        for door in doors.values():
            door.stop()

    print("======== Entering manual mode ========")
    if rpi_uart:
        rpi_uart.send_message(Message(0, "MANUAL_MODE"))

    timeout = user_config.manual_mode_timeout_minutes * 60
    last_request = time.time()

    while True:
        request = shared_dict.get("request")

        if request is None:
            # Reboot back into the sequence so the trap isn't left disarmed after
            # someone has finished with it.
            if timeout > 0 and time.time() - last_request > timeout:
                print("No requests for {} minutes, restarting.".format(user_config.manual_mode_timeout_minutes))
                if rpi_uart:
                    rpi_uart.send_message(Message(0, "MANUAL_MODE_TIMEOUT"))
                    time.sleep(1)
                reset()
            time.sleep(0.1)
            continue

        # Clear the request before running it so a new request coming in while it runs
        # is not lost, and so it doesn't get run twice.
        shared_dict.set("request", None)
        last_request = time.time()
        print("Manual request: " + str(request))

        try:
            if request == "STOP":
                # Whatever was running has already stopped on its way out, as the request
                # that interrupted it unwinds through a power off. This makes sure nothing
                # is left driven, and covers a STOP that arrives while nothing is moving.
                stop_all()
                if rpi_uart:
                    rpi_uart.send_message(Message(0, "STOPPED"))
            elif request == "RELEASE_SPOOL":
                if not spool.release():
                    manual_error(rpi_uart, "spool is not at home so it can't be released")
            elif request == "RESET_SPOOL":
                spool.reset_sequence()
            elif request == "OPEN_DOOR_1":
                # Ratchets the door up and holds it. This runs for RATCHET_CYCLES * ~2s,
                # and is not interrupted by a new request, which waits in the shared
                # dict until this returns.
                get_door(1).reset()
            elif request == "CLOSE_DOOR_1":
                get_door(1).release()
            elif request == "OPEN_DOOR_2":
                get_door(2).reset()
            elif request == "CLOSE_DOOR_2":
                get_door(2).release()
            else:
                manual_error(rpi_uart, "unknown request " + str(request))
        except ManualMode:
            # A new request came in while running this one. Stop what we are doing and
            # pick the new request up on the next time around.
            print("Request interrupted by a new request.")
            stop_all()
        except Exception as e:
            print(get_err_str(e))
            manual_error(rpi_uart, get_err_str(e))
            stop_all()

def manual_error(rpi_uart, reason):
    # Report a request that couldn't be run. Not using error(), as that reboots the trap
    # and a failed request should leave it in manual mode.
    # Messages are a single line, so a multi line reason (a traceback) has to be flattened.
    reason = str(reason).replace("\n", " ")
    print("Manual request failed: " + reason)
    if rpi_uart:
        rpi_uart.send_message(Message(0, "MANUAL_ERROR", reason))

def error_code(code, extra=None):
    print(f"ERROR_CODE: {code}")
    # Beep the error code 3 times
    buzzer = Buzzer()
    for _ in range(3):
        for _ in range(3):
            buzzer.on()
            time.sleep(0.2)
            buzzer.pwm(800, 50)
            time.sleep(0.2)
        buzzer.off()
        time.sleep(1)
        for i in range(code):
            buzzer.on()
            time.sleep(0.2)
            buzzer.off()
            time.sleep(0.2)
        time.sleep(1)
    if extra:
        error("ERROR_CODE", f"{code}: {extra}")
    else:
        error("ERROR_CODE", code)

def get_err_str(exception):
    buf = io.StringIO()
    sys.print_exception(exception, buf)  # pyright: ignore[reportAttributeAccessIssue]
    return buf.getvalue()

def error_exception(exception):
    buf = io.StringIO()
    sys.print_exception(exception, buf)  # pyright: ignore[reportAttributeAccessIssue]
    exception_str = get_err_str(exception)
    print("EXCEPTION:", exception_str)
    error("EXCEPTION", exception_str.splitlines())

def error(type, payload, rpi_uart=None):
    # Try to send the error via UART
    message = Message(0, type, payload)
    try:
        # If not given a rpi_uart, try to create one
        if not rpi_uart:
            rpi_uart = RPi_UART(SharedDict())
        rpi_uart.send_message(message)
    except:
        print("Failed to send error via UART. Saving error to file")
        with open("error.json", "w") as f:
            json.dump({"type": type, "payload": payload}, f)

    # Restart the system
    time.sleep(5)
    reset()

def get_file_hashes(target_files=None):
    files = {}
    for entry in os.ilistdir("/"):  # pyright: ignore[reportAttributeAccessIssue]
        name = entry[0]
        if target_files and name not in target_files:
            continue
        h = hashlib.sha256()
        with open("/" + name, "rb") as f:
            while True:
                chunk = f.read(512)
                if not chunk:
                    break
                h.update(chunk)
        files[name] = binascii.hexlify(h.digest()).decode()[:10]
    return files

def read_file(filename, offset, count):
    with open(filename, "r") as f:
        for _ in range(offset):
            if not f.readline():
                break
        lines = []
        for _ in range(count):
            line = f.readline()
            if not line:
                break
            lines.append(line.rstrip('\n'))
    return lines
