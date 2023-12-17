import RPi.GPIO as GPIO
import sys
import time
import random
import socket
from socket import *
import matplotlib.pyplot as plt
from collections import Counter
import datetime
import json

VERSIONNUMBER = 6
# packet type definitions
LIGHT_UPDATE_PACKET = 0
RESET_SWARM_PACKET = 1
CHANGE_TEST_PACKET = 2 # Not Implemented
RESET_ME_PACKET = 3
DEFINE_SERVER_LOGGER_PACKET = 4
LOG_TO_SERVER_PACKET = 5
MASTER_CHANGE_PACKET = 6
BLINK_BRIGHT_LED = 7
MYPORT = 5005
SWARMSIZE = 6

photoresistorValue = 0
swarmIP = None

swarmIndexArray = [] # Stores swarm Ip
swarmTimeArray = [0 for x in range(SWARMSIZE)]
logContent = {
    "masterTenure": [],
    "rawData": []
}

startFlag = False

color = ""
previousColor = ""
masters = []
ips = []
photoresistorValues = []
seconds = 0

pressed = False

# set up sockets for UDP
s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
s.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
s.bind(('',MYPORT))
s.setblocking(False)

sendSocket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)

LSBFIRST = 1
MSBFIRST = 2
# define the pins connect to 74HC595
dataPin   = 18      # DS Pin of 74HC595
latchPin  = 16      # ST_CP Pin of 74HC595
clockPin = 12       # SH_CP Pin of 74HC595
num = (0xc0,0xf9,0xa4,0xb0,0x99,0x92,0x82,0xf8,0x80,0x90)
digitPin = (11,33,15,19)    # Define the pin of 7-segment display common end

matrixDataPin = 7      # DS Pin of 74HC595(Pin14)
matrixLatchPin = 29      # ST_CP Pin of 74HC595(Pin12)
matrixClockPin = 37       # SH_CP Pin of 74HC595(Pin11)

def setup():
    GPIO.setmode(GPIO.BOARD)     # use PHYSICAL GPIO Numbering
    GPIO.setup(dataPin, GPIO.OUT)       # Set pin mode to OUTPUT
    GPIO.setup(latchPin, GPIO.OUT)
    GPIO.setup(clockPin, GPIO.OUT)
    for pin in digitPin:
        GPIO.setup(pin,GPIO.OUT)
    GPIO.setup(matrixDataPin, GPIO.OUT)
    GPIO.setup(matrixLatchPin, GPIO.OUT)
    GPIO.setup(matrixClockPin, GPIO.OUT)

def shiftOut(dPin,cPin,order,val):
    for i in range(0,8):
        GPIO.output(cPin,GPIO.LOW);
        if(order == LSBFIRST):
            GPIO.output(dPin,(0x01&(val>>i)==0x01) and GPIO.HIGH or GPIO.LOW)
        elif(order == MSBFIRST):
            GPIO.output(dPin,(0x80&(val<<i)==0x80) and GPIO.HIGH or GPIO.LOW)
        GPIO.output(cPin,GPIO.HIGH)

def outData(data):      # function used to output data for 74HC595
    GPIO.output(latchPin,GPIO.LOW)
    shiftOut(dataPin,clockPin,MSBFIRST,data)
    GPIO.output(latchPin,GPIO.HIGH)

def selectDigit(digit): # Open one of the 7-segment display and close the remaining three, the parameter digit is optional for 1,2,4,8
    GPIO.output(digitPin[0],GPIO.LOW if ((digit&0x08) == 0x08) else GPIO.HIGH)
    GPIO.output(digitPin[1],GPIO.LOW if ((digit&0x04) == 0x04) else GPIO.HIGH)
    GPIO.output(digitPin[2],GPIO.LOW if ((digit&0x02) == 0x02) else GPIO.HIGH)
    GPIO.output(digitPin[3],GPIO.LOW if ((digit&0x01) == 0x01) else GPIO.HIGH)

def display(dec):   # display function for 7-segment display
    outData(0xff)   # eliminate residual display
    selectDigit(0x01)   # Select the first, and display the single digit
    outData(num[dec%10])
    time.sleep(0.003)   # display duration
    outData(0xff)
    selectDigit(0x02)   # Select the second, and display the tens digit
    outData(num[dec%100//10])
    time.sleep(0.003)
    outData(0xff)
    selectDigit(0x04)   # Select the third, and display the hundreds digit
    outData(num[dec%1000//100])
    time.sleep(0.003)
    outData(0xff)
    selectDigit(0x08)   # Select the fourth, and display the thousands digit
    outData(num[dec%10000//1000])
    time.sleep(0.003)

def createLogFile():
    global logFilePath, logContent
    if logFilePath != "":
        with open(logFilePath, "w") as outfile:
            json.dump(logContent, outfile)

    basePath = "/home/tjay/Documents/logs/"
    curTime = datetime.datetime.now()
    logFilePath = basePath + curTime.strftime("%Y-%m-%d %H:%M:%S") + ".json"

def SendRESET_SWARM_PACKET(s):
    print("RESET_SWARM_PACKET Sent")
    s.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
    s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    #s.settimeout(0.2)
    data= [0x00 for i in range(8)]
    data[0] = 0xF0
    data[1] = RESET_SWARM_PACKET
    data[2] = 0xFF
    data[3] = VERSIONNUMBER
    data[4] = 0x00
    data[5] = 0x00
    data[6] = 0x00
    data[7] = 0x0F
    #bytesData = bytearray(data)
    s.sendto(bytes(data), ('<broadcast>', MYPORT))

# def button_callback(channel): # channel is the button GPIO port
def button_callback():
    # Send reset message to ESP to reset them
    print("Button pressed")
    global logContent, swarmIndexArray, swarmTimeArray, photoresistorValue, swarmIP, t0, graphTime, startFlag, pwmRed, pwmGreen, pwmWhite, color, previousColor, masters, ips, photoresistorValues, bars, seconds, axs

    if startFlag:
        # Calculate current master's tenure so far
        swarmTimeArray[swarmIndexArray.index(swarmIP)] += round(time.perf_counter() - t0)
        for i in range(len(swarmIndexArray)):
            logContent["masterTenure"].append({"ip": str(swarmIndexArray[i]), "time": int(swarmTimeArray[i])})
    
    createLogFile()

    photoresistorValue = 0
    swarmIP = None
    swarmIndexArray = []
    swarmTimeArray = [0 for x in range(SWARMSIZE)]
    logContent = {}
    time.sleep(3)
    for i in range(2):
        SendRESET_SWARM_PACKET(sendSocket)
        time.sleep(0.5)
    t0 = time.perf_counter()
    graphTime = time.perf_counter()
    color = ""
    previousColor = ""
    masters = []
    ips = []
    photoresistorValues = []
    bars = []
    seconds = 0
    startFlag = True

setup()

GPIO.setwarnings(False)
GPIO.setup(31, GPIO.IN, pull_up_down=GPIO.PUD_UP) # GPIO 6 for button

matrixData = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,0xFF, 0x7F, 0x3F, 0x1F, 0x0F, 0x07, 0x03, 0x01, 0x00, 0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F]

while(1) :
    display(555)

    for k in range(0,len(matrixData)-8): #len(matrixData) total number of "0-F" columns
        for j in range(0,400): # times of repeated displaying LEDMatrix in every frame, the bigger the "j", the longer the display time.
            x=0x80      # Set the column information to start from the first column
            for i in range(k,k+8):
                GPIO.output(matrixLatchPin,GPIO.LOW)
                shiftOut(matrixDataPin,matrixClockPin,MSBFIRST,matrixData[i])
                shiftOut(matrixDataPin,matrixClockPin,MSBFIRST,~x)
                GPIO.output(matrixLatchPin,GPIO.HIGH)
                time.sleep(0.001)
                x>>=1

    if not GPIO.input(31):
        button_callback()

    if startFlag == False:
        continue
    # Receive
    #SendRESET_SWARM_PACKET(s)
    try:
        d = s.recvfrom(1024)
        message = d[0]
        addr = d[1]
        if (len(message) == 8):
            if (message[1] == LOG_TO_SERVER_PACKET):
                photoresistorValue = message[5] * 256 + message[6]
                if message[2] not in swarmIndexArray:
                    swarmIndexArray.append(message[2])
                if swarmIP != None and swarmIP != message[2]: # New master, calculate old master's tenure
                    swarmTimeArray[swarmIndexArray.index(swarmIP)] += round(time.perf_counter() - t0)
                    t0 = time.perf_counter()
                swarmIP = message[2]

                logContent["rawData"].append({"ip": str(swarmIP), "value": int(photoresistorValue)})

        else:
            print(f"error message length = {len(message)}")
    except BlockingIOError:
        pass