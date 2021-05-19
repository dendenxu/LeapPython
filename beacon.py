from hand import Hand
from log import log
import serial
import threading


class Beacon:
    def __init__(self, port="COM6", baudrate=115200, enable=True):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baudrate
        self.ser.timeout = None
        self.ser.write_timeout = 0
        self.enable = enable
        if self.enable:
            self.ser.open()
        log.info(f"Serial on {port}, baudrate {baudrate}, open: {self.ser.is_open}")
        log.info(f"Serial status: {str(self.ser)}")

        self.last_msg = None

    def send(self, signal):
        if not self.enable:
            # log.error(f"Beacon is disabled")
            return
        if self.last_msg is None or signal != self.last_msg:
            # log.info(f"To serial: {signal.encode()}")
            self.ser.write(signal.encode())
            self.last_msg = signal
            return signal
        else:
            log.info(f"Duplicated message")
            return ""

    def readline(self):
        if not self.enable:
            # log.error(f"Beacon is disabled")
            return "DEVICE_READY_MESSAGE"
        return self.ser.readline().decode()

    def close(self):
        if not self.enable:
            # log.error(f"Beacon is disabled")
            return
        return self.ser.close()

    @property
    def out_waiting(self):
        return self.ser.out_waiting