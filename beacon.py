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

        self.last_msg = None

    def send(self, signal):
        if self.last_msg is None or signal != self.last_msg:
            log.info(f"To serial: {signal.encode()}")
            self.ser.write(signal.encode())
            self.last_msg = signal

    def read(self):
        return self.ser.readline()

    def close(self):
        self.ser.close()

    @property
    def out_waiting(self):
        return self.ser.out_waiting
