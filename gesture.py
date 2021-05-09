from hand import Hand
from log import log
import serial

class GestureHelper:
    def __init__(self):
        self.hand_pool = [Hand(), Hand()]

    def open_serial(self, port="COM4", baudrate=115200):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baudrate
        self.ser.open()
        log.info(f"Serial on {port}, baudrate {baudrate} status: {self.ser.is_open}")

    def update(self, msg, index):
        if msg["hands"][index]["type"] == "left":
            self.hand_pool[0].store_pos(msg, index)
        else:
            self.hand_pool[1].store_pos(msg, index)

