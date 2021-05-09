from hand import Hand
from log import log
import serial


class Beacon:
    def __init__(self, port="COM4", baudrate=115200):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baudrate
        self.ser.timeout = 0
        self.ser.write_timeout = 0
        self.ser.open()
        log.info(f"Serial on {port}, baudrate {baudrate}, open: {self.ser.is_open}")
        log.info(f"Serial status: {str(self.ser)}")

    def send(self, signal):
        self.ser.write(signal.encode())
