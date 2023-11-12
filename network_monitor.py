'''
    LightSwarm Raspberry Pi Logger
    Original code by SwitchDoc Labs, December 2020
    Source: https://github.com/switchdoclabs/SDL_Pi_LightSwarm
    Modified by Jessie Kao for LightSwarm, November 2023
'''
import sys
import time
import random
import RPi.GPIO as GPIO

from netifaces import interfaces, ifaddresses, AF_INET

import threading
from socket import *
from guizero import App, Text, Picture, Box

lock = threading.Lock()

VERSIONNUMBER = 7
# packet type definitions
LIGHT_UPDATE_PACKET = 0
RESET_SWARM_PACKET = 1
CHANGE_TEST_PACKET = 2   # Not Implemented
RESET_ME_PACKET = 3
DEFINE_SERVER_LOGGER_PACKET = 4
LOG_TO_SERVER_PACKET = 5
MASTER_CHANGE_PACKET = 6
BLINK_BRIGHT_LED = 7

BUTTON_GPIO = 10
WHITE_LED_PIN = 16

MYPORT = 2901
SWARMSIZE = 3

LED = [11,13,15] # LED pins for the swarms
LEDInterval = 2
masterID = -1

logString = ""

seconds_300_round = time.time() + 300.0
seconds_120_round = time.time() + 120.0

# For GUI
NP = "/home/pi/mu_code/LightSwarm/state/Off-NotPresent.png"
MASTER = "/home/pi/mu_code/LightSwarm/state/On-Master.png"
SLAVE = "/home/pi/mu_code/LightSwarm/state/On-Slave.png"
TO = "/home/pi/mu_code/LightSwarm/state/Off-TimeOut.png"
guiPictures = []
guiIPs = []
guiStates = []
guiDatas = []
app = App(title="Swarm System", width=700, height=300)
reset = False
guiReset = Text(app, text="Reseting...", color="red", visible=False)

# UDP Commands and packets
def SendDEFINE_SERVER_LOGGER_PACKET(s):
    print("DEFINE_SERVER_LOGGER_PACKET Sent")
    s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1) # set socket options: socket, level, option_name
	# get IP address
    for ifaceName in interfaces():
            addresses = [i['addr'] for i in ifaddresses(ifaceName).setdefault(AF_INET, [{'addr':'No IP addr'}] )]
            #print('%s: %s' % (ifaceName, ', '.join(addresses)))

    # last interface (wlan0) grabbed
    myIP = addresses[0].split('.')
    data= ["" for i in range(14)]
    data[0] = int("F0", 16).to_bytes(1,'little')
    data[1] = int(DEFINE_SERVER_LOGGER_PACKET).to_bytes(1,'little')
    data[2] = int("FF", 16).to_bytes(1,'little') # swarm id (FF means not part of swarm)
    data[3] = int(VERSIONNUMBER).to_bytes(1,'little')
    data[4] = int(myIP[0]).to_bytes(1,'little') # 1 octet of ip
    data[5] = int(myIP[1]).to_bytes(1,'little') # 2 octet of ip
    data[6] = int(myIP[2]).to_bytes(1,'little') # 3 octet of ip
    data[7] = int(myIP[3]).to_bytes(1,'little') # 4 octet of ip
    data[8] = int(0x00).to_bytes(1,'little')
    data[9] = int(0x00).to_bytes(1,'little')
    data[10] = int(0x00).to_bytes(1,'little')
    data[11] = int(0x00).to_bytes(1,'little')
    data[12] = int(0x00).to_bytes(1,'little')
    data[13] = int(0x0F).to_bytes(1,'little')
    mymessage = ''.encode()  	
    s.sendto(mymessage.join(data), ('<broadcast>'.encode(), MYPORT))
	
def SendRESET_SWARM_PACKET(s):
    print("RESET_SWARM_PACKET Sent")
    s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    data= ["" for i in range(14)]
    data[0] = int("F0", 16).to_bytes(1,'little')
    data[1] = int(RESET_SWARM_PACKET).to_bytes(1,'little')
    data[2] = int("FF", 16).to_bytes(1,'little') # swarm id (FF means not part of swarm)
    data[3] = int(VERSIONNUMBER).to_bytes(1,'little')
    data[4] = int(0x00).to_bytes(1,'little')
    data[5] = int(0x00).to_bytes(1,'little')
    data[6] = int(0x00).to_bytes(1,'little')
    data[7] = int(0x00).to_bytes(1,'little')
    data[8] = int(0x00).to_bytes(1,'little')
    data[9] = int(0x00).to_bytes(1,'little')
    data[10] = int(0x00).to_bytes(1,'little')
    data[11] = int(0x00).to_bytes(1,'little')
    data[12] = int(0x00).to_bytes(1,'little')
    data[13] = int(0x0F).to_bytes(1,'little')
    mymessage = ''.encode()  	
    s.sendto(mymessage.join(data), ('<broadcast>'.encode(), MYPORT))
	
def parseLogPacket(message):
    incomingSwarmID = setAndReturnSwarmID((message[2]))
    logString = ""
    for i in range(0,(message[3])):
        logString = logString + chr((message[i+5]))
    # print("logString:", logString)	
    return logString, incomingSwarmID

# Change master and slave
def changeSwarmState(logString, incomingSwarmID):
    swarmList = logString.split("|")
    for i in range(0,SWARMSIZE):
        swarmElement = swarmList[i].split(",")
        # print("swamrID: %d \n" % int(swarmElement[5]))
        swarmID = setAndReturnSwarmID(int(swarmElement[5]))
        swarmStatus[swarmID][0] = "P" if swarmElement[4] == "PR" else swarmElement[4]# Update status
        swarmStatus[swarmID][1] = time.time() # Update timestamp
        swarmStatus[swarmID][2] = "M" if swarmElement[1] == "1" else "S" # Update state (M/S)
        swarmStatus[swarmID][6] = swarmElement[3]
        # This is the master
        if swarmStatus[swarmID][0] == "P" and swarmStatus[swarmID][2] == "M":
            global masterID, LEDInterval
            with lock:
                masterID = swarmID;
                LEDInterval = (1.0-float(swarmElement[3])/1023.0)*1.0
        else:
            GPIO.output(LED[swarmID], GPIO.LOW)

def setAndReturnSwarmID(incomingID):
    for i in range(0,SWARMSIZE):
        if (swarmStatus[i][5] == incomingID):
            return i
        else:
            if (swarmStatus[i][5] == 0):  # not in the system, so put it in
                swarmStatus[i][5] = incomingID;
                print("New swarm %d coming, " % incomingID)
                print("assigned #%d" % i)
                return i
    # if we get here, then we have a new swarm member.
    # Delete the oldest swarm member and add the new one in
    # (this will probably be the one that dropped out)

    oldTime = time.time();
    oldSwarmID = 0
    for i in range(0,SWARMSIZE):
        if (oldTime > swarmStatus[i][1]):
            ldTime = swarmStatus[i][1]
            oldSwarmID = i

    # remove the old one and put this one in....
    swarmStatus[oldSwarmID][5] = incomingID;
    # the rest will be filled in by Light Packet Receive
    print("Delete oldSwarmID %i" % oldSwarmID)

    return oldSwarmID

def getUDP():
    while True:
        if not reset:
            d = s.recvfrom(1024)
            message = d[0]
            addr = d[1]
            if (len(message) == 14):
                if (message[1] == LIGHT_UPDATE_PACKET):
                    incomingSwarmID = setAndReturnSwarmID((message[2]))
                    swarmStatus[incomingSwarmID][0] = "P"
                    swarmStatus[incomingSwarmID][1] = time.time()

                if ((message[1]) == RESET_SWARM_PACKET):
                    print("Swarm RESET_SWARM_PACKET Received")
                    print("received from addr:",addr)	

                if ((message[1]) == DEFINE_SERVER_LOGGER_PACKET):
                    print("Swarm DEFINE_SERVER_LOGGER_PACKET Received")
                    print("received from addr:",addr)	

            else:
                if ((message[1]) == LOG_TO_SERVER_PACKET):
                    # process the Log Packet
                    logString, masterID = parseLogPacket(message)
                    changeSwarmState(logString, masterID)

                else:
                    print("error message length = ",len(message))

            global seconds_120_round, seconds_300_round
            if (time.time() >  seconds_120_round):
                # do our 2 minute round
                print(">>>> doing 120 second task")
                sendTo = random.randint(0,SWARMSIZE-1)
                seconds_120_round = time.time() + 120.0	

            if (time.time() >  seconds_300_round):
                # do our 2 minute round
                print(">>>> doing 300 second task")
                SendDEFINE_SERVER_LOGGER_PACKET(s)
                seconds_300_round = time.time() + 300.0	
        time.sleep(0.02)

def flashLED():
    while True:
        if not reset:
            if masterID >= 0 and not reset:
                GPIO.output(LED[masterID], GPIO.HIGH)
                time.sleep(LEDInterval/2.0)
                GPIO.output(LED[masterID], GPIO.LOW)
                time.sleep(LEDInterval/2.0)
        time.sleep(0.001)

def resetBtnClick(channel):
    GPIO.output(WHITE_LED_PIN, GPIO.HIGH)
    SendRESET_SWARM_PACKET(s)
    for i in range(3):
        GPIO.output(LED[i], GPIO.LOW)
    for i in range(0,SWARMSIZE):
        swarmStatus[i][0] = "NP"
        swarmStatus[i][5] = 0
    global masterID, reset, LEDInterval
    with lock:
        masterID = -1
        LEDInterval = 2
        reset = True
    time.sleep(3)
    GPIO.output(WHITE_LED_PIN, GPIO.LOW)
    with lock:
        reset = False

def updateGUI():
    for i in range(0,SWARMSIZE):
        if swarmStatus[i][0] == "NP":
            guiPictures[i].image = NP
            guiIPs[i].value = "IP Address"
            guiStates[i].value = "Not Present"

        elif swarmStatus[i][0] == "TO":
            guiPictures[i].image = TO
            guiStates[i].value = "Time Out"
        elif swarmStatus[i][0] == "P" and swarmStatus[i][2] == "M":
            guiPictures[i].image = MASTER
            guiIPs[i].value = "192.168.0." + str(swarmStatus[i][5])
            guiStates[i].value = "Master"
            guiDatas[i].value = swarmStatus[i][6]
        elif swarmStatus[i][0] == "P" and swarmStatus[i][2] == "S":
            guiPictures[i].image = SLAVE
            guiIPs[i].value = "192.168.0." + str(swarmStatus[i][5])
            guiStates[i].value = "Slave"
            guiDatas[i].value = swarmStatus[i][6]
    if reset:
        guiReset.visible = True
    else:
        guiReset.visible = False

def displayGUI():
    device1 = Box(app, layout="grid", align="left", width="fill", grid=[0,0])
    Text(device1, text="ESP 1", grid=[0,0])
    guiPictures.append(Picture(device1, image=NP, grid=[0,1]))
    guiIPs.append(Text(device1, text="IP Address", grid=[0,2]))
    guiStates.append(Text(device1, text="Not Present", grid=[0,3]))
    guiDatas.append(Text(device1, text="No Data", grid=[0,4]))

    device2 = Box(app, layout="grid", align="left", width="fill", grid=[1,0])
    Text(device2, text="ESP 2", grid=[0,0])
    guiPictures.append(Picture(device2, image=NP, grid=[0,1]))
    guiIPs.append(Text(device2, text="IP Address", grid=[0,2]))
    guiStates.append(Text(device2, text="Not Present", grid=[0,3]))
    guiDatas.append(Text(device2, text="No Data", grid=[0,4]))

    device3 = Box(app, layout="grid", align="left", width="fill", grid=[2,0])
    Text(device3, text="ESP 3", grid=[0,0])
    guiPictures.append(Picture(device3, image=NP, grid=[0,1]))
    guiIPs.append(Text(device3, text="IP Address", grid=[0,2]))
    guiStates.append(Text(device3, text="Not Present", grid=[0,3]))
    guiDatas.append(Text(device3, text="No Data", grid=[0,4]))

    app.repeat(500, updateGUI)
    app.display()

if __name__ == '__main__':
    # set up sockets for UDP
    s=socket(AF_INET, SOCK_DGRAM)
    host = 'localhost';
    s.bind(('',MYPORT))

    # set up GPIO
    GPIO.setmode(GPIO.BOARD)
    for i in range(3):
        GPIO.setup(LED[i], GPIO.OUT)
        GPIO.output(LED[i], GPIO.LOW)
    GPIO.setup(WHITE_LED_PIN, GPIO.OUT)
    GPIO.output(WHITE_LED_PIN, GPIO.LOW)

    # set up button
    GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    # first send out DEFINE_SERVER_LOGGER_PACKET to tell swarm where to send logging information
    SendDEFINE_SERVER_LOGGER_PACKET(s)
    time.sleep(3)
    SendDEFINE_SERVER_LOGGER_PACKET(s)

    # swarmStatus
    swarmStatus = [[0 for x  in range(7)] for x in range(SWARMSIZE)]

    # 6 items per swarm item

    # 0 - NP  Not present, P = present, TO = time out
    # 1 - timestamp of last LIGHT_UPDATE_PACKET received
    # 2 - Master or slave status   M S
    # 3 - Current Test Item - 0 - CC 1 - Lux 2 - Red 3 - Green  4 - Blue
    # 4 - Current Test Direction  0 >=   1 <=
    # 5 - IP Address of Swarm
    # 6 - Sensor data

    for i in range(0,SWARMSIZE):
        swarmStatus[i][0] = "NP"
        swarmStatus[i][5] = 0
        swarmStatus[i][6] = 0

    # button event
    GPIO.add_event_detect(BUTTON_GPIO, GPIO.FALLING, callback=resetBtnClick, bouncetime=100)

    led_thread = threading.Thread(target=flashLED)
    led_thread.start()

    udpMonitor = threading.Thread(target=getUDP)
    udpMonitor.start()

    displayGUI()

    led_thread.join()
    udpMonitor.join()