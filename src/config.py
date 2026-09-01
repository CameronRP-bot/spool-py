## PIN CONFIGURATION ##

# H bridge driver pins
PIN_H_IN_1 = 12
PIN_H_IN_2 = 13

# Rotary encoder pins
PIN_ROT_ENC_1 = 8
PIN_ROT_ENC_2 = 3
PIN_ROT_ENC_4 = 7
PIN_ROT_ENC_8 = 4

# I2C pins
PIN_SDA = 14
PIN_SCL = 15
I2C_BUS_ID = 1

# PIR pins
PIR_APIR = 26
PIN_PIR_EXTERNAL = 22

# Buzzer Pin
PIN_BUZZER = 1

# Night time switch
PIN_SW_NIGHT_ONLY = 0 # Setup with pull-up

# Photo interrupter pins
PIN_EN_PHOTO_INTERRUPTER = 9
PIN_PHOTO_INTERRUPTER_HOME = 10
PIN_PHOTO_INTERRUPTER_RESET = 11

# Electromagnet
PIN_ELECTROMAGNET_RELEASE = 21

# UART pins
PIN_UART_TX_IN = 16
PIN_UART_RX_IN = 17
UART_IN_ID = 0
PIN_UART_TX_OUT = 24
PIN_UART_RX_OUT = 25
UART_OUT_ID = 1

# Switch pins
PIN_SW_1 = 2
PIN_SW_2 = 5

# Spool reed switch pin
PIN_SPOOL_RESET = 6

# Servo pins
PIN_EN_6V = 18
PIN_SERVO_1 = 19
PIN_SERVO_2 = 20

# Extra GPIO pin
PIN_GPIO_EXTRA = 23

# INA219 shunt resistor resistance in Ω
SHUNT_OHMS = 0.1

# Ratchet Door Servo
RATCHET_CYCLES = 8 # How many times to ratchet the door to open it fully
SERVO_DOOR_DOWN_RATCHET = 600 # Down ratchet position
SERVO_DOOR_UP_RATCHET = 1500 # Up ratchet position
SERVO_DOOR_HOLD = 1700 # Hold position (ready to release)
SERVO_DOOR_RELEASE = 2000 # Release the door

# Error codes
ERROR_TIME_NOT_SET = 3
ERROR_NO_PROGRAM_FOUND = 4
ERROR_MOVEMENT_TIMEOUT = 5
ERROR_FAILED_TO_RESET = 6
ERROR_OVER_CURRENT = 7
ERROR_RUNTIME_ERROR = 8
ERROR_SPOOL_NOT_RELEASING = 9

# This is used so when resetting the first time it knows how long each "step" should be.
HOME_TO_RESET_DURATION = 13

class UserConfig():
    def __init__(self):
        self.apir_d_threshold = 0.3
        self.apir_dt_threshold = 450
        self.max_current = 1000
        self.spool_reset_delay_minutes = 10
        self.latitude = -43.532055
        self.longitude = 172.636230
        self.test_loop_interval = 180
        self.switch_1_disable = "IGNORE"
        self.switch_2_disable = "IGNORE"
        self.switch_logic = "OR"
        self.observation_mode = False
        self.motion_message_gap = 10
        self.post_reset_cooldown_seconds = 1
        self.spool_reed_check = False
        self.manual_mode_timeout_minutes = 30
        self.program = 1

        self._load_user_config()

    def _load_user_config(self):
        try:
            import json
            with open("config.json") as f:
                user_cfg = json.load(f)
            for key, value in user_cfg.items():
                if hasattr(self, key):
                    setattr(self, key, value)
        except (OSError, ValueError):
            pass
