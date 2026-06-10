import serial

ser = serial.Serial("/dev/ttyUSB0", 115200)

# envie de me flusher le buffer
# ~ Eric Lecktackone (100% j'ai mal écrit ça)
while ser.in_waiting:
    print(ser.readLine())

print("writing")
l=ser.write(bytearray("I\n", encoding="ascii"))
print(f'Sent {l}')

print("reading..")
while True:
    print(ser.readline())

