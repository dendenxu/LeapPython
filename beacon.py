from hand import Hand
from log import log
import serial
import threading


class Beacon:
    def __init__(self, port="COM6", baudrate=115200):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baudrate
        self.ser.timeout = None
        self.ser.write_timeout = 0
        self.ser.open()
        log.info(f"Serial on {port}, baudrate {baudrate}, open: {self.ser.is_open}")
        log.info(f"Serial status: {str(self.ser)}")

    def send(self, signal):
        self.ser.write(signal.encode())

    def read(self):
        return self.ser.readline()

    def close(self):
        self.ser.close()
