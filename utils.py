# Slave serial reader
import serial
ser = serial.Serial()
ser.port = "COM32"
ser.baudrate = 115200
ser.timeout = None
ser.open()
while True:
    d = ser.readline()
    print(d.decode())
