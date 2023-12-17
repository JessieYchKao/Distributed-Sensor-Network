/*
# Original code by Prof. Shovic, SwitchDoc Labs, August 2015
# Source: https://github.com/switchdoclabs/LightSwarm/blob/master/LightSwarm.ino
# Modified by Jessie Kao for LgihtSwarm, November 2023
*/

#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include "WiFiCredentials.h"
#include <FastLED.h>

#undef DEBUG
#define VERSIONNUMBER 28

#define SWARMSIZE 3
#define SWARMTOOOLD 30000 // 30 seconds is too old - it must be dead
#define NETWORKSILENT 200 // 200 ms is too silent, broadcast

long lastReceiveTime = 0; // Last time receive UDP packet
int mySwarmID = 0;

// Packet Types
#define LIGHT_UPDATE_PACKET 0
#define RESET_SWARM_PACKET 1
#define CHANGE_TEST_PACKET 2
#define RESET_ME_PACKET 3
#define DEFINE_SERVER_LOGGER_PACKET 4
#define LOG_TO_SERVER_PACKET 5
#define MASTER_CHANGE_PACKET 6
#define BLINK_BRIGHT_LED 7

#define PHOTORES_PIN A0
#define MASTER_LED BUILTIN_LED

#define LED_PIN     D7  // Connect the data input pin to GPIO D7
// Number of LEDs on Freenove rgb LED module
#define NUM_LEDS    8
CRGB leds[NUM_LEDS];

unsigned int localPort = 5005;      // local port to listen for UDP packets
// variables for photoresistor
int light;

// master variables
bool masterState = true; // True if I'm the master, False if not
int swarmLights[SWARMSIZE]; // The light sensor data for all swarms
int swarmVersion[SWARMSIZE];
int swarmState[SWARMSIZE]; // The slave/master state for all swarms, 0 for slave, 1 for master
long swarmTimeStamp[SWARMSIZE];   // Stores the last time of packet received from the swarms. -1: init, 1: myself, 0: too old (>SWARMTOOOLD)

IPAddress serverAddress = IPAddress(0, 0, 0, 0); // default no IP Address (Will send log to server)
IPAddress broadcastAddress = IPAddress(192, 168, 0, 255);

int swarmAddresses[SWARMSIZE];  // Swarm addresses

int dutyCycle = 255;

const int PACKET_SIZE = 8; // Light Update Packet
const int BUFFERSIZE = 1024;

byte packetBuffer[BUFFERSIZE]; // Buffer to hold incoming and outgoing packets

WiFiUDP udp; // A UDP instance to let us send and receive packets over UDP


IPAddress localIP;

void setup() {
  Serial.begin(9600);

  pinMode(MASTER_LED, OUTPUT); // MASTER_LED as OUTPUT
  digitalWrite(MASTER_LED, HIGH); // Turn on LED to show that I'm a master

  FastLED.addLeds<WS2812, LED_PIN, GRB>(leds, NUM_LEDS);
  for (int i = 0; i < NUM_LEDS; i++) {
    leds[i] = CRGB::Green;
  }
  FastLED.setBrightness(2);
  FastLED.show();

  // everybody starts at 0 and changes from there
  mySwarmID = 0;

  // We start by connecting to a WiFi network
  Serial.print("LightSwarm Instance: ");
  Serial.println(mySwarmID);

  Serial.print("Connecting to ");
  WiFi.begin(WIFI_SSID, WIFI_PWD);
  // initialize Swarm Address - we start out as swarmID of 0
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  digitalWrite(MASTER_LED, LOW); // Turn on LED to show that I'm a master
  Serial.println("");

  Serial.println("WiFi connected, IP address: ");
  Serial.println(WiFi.localIP());


  udp.begin(localPort);

  // initialize light sensor and arrays
  for (int i = 0; i < SWARMSIZE; i++) {
    swarmAddresses[i] = 0;
    swarmLights[i] = 0;
    swarmTimeStamp[i] = -1;
  }
  swarmVersion[mySwarmID] = VERSIONNUMBER;
  swarmTimeStamp[mySwarmID] = 1;   // I am always in time to myself
  swarmState[mySwarmID] = masterState;

  // set SwarmID based on IP address 
  localIP = WiFi.localIP();
  
  swarmAddresses[mySwarmID] =  localIP[3]; // 192.168.0.xx Set xx to represent swarm address
}

void loop() {
  light = analogRead(PHOTORES_PIN);
  Serial.println(light);
  int level = light / (1024/NUM_LEDS); // Calculate level of brightness

  for (int i = 0; i < NUM_LEDS; i++) {
    if (i < level) {
      leds[i] = CRGB::Green;  // Light up LEDs up to the calculated level
    } else {
      leds[i] = CRGB::Black;  // Turn off LEDs beyond the calculated level
    }
  }
  FastLED.setBrightness(2);
  FastLED.show();

  swarmLights[mySwarmID] = light;
  
  sendLogToServer();

  if (isNetworkSilent()) {
    swarmLights[mySwarmID] = light;
    sendLightUpdatePacket(broadcastAddress);
    lastReceiveTime = millis();
  }
  
  getUDPPacket();
  delay(50);
}

void getUDPPacket() {
  int packetSize = udp.parsePacket();
  if (packetSize) {
    Serial.println("Get UDP");
    //receive incoming UDP packets
    int len = udp.read(packetBuffer, PACKET_SIZE);
    if (len > 0) {
      lastReceiveTime = millis();
      if (packetBuffer[1] == LIGHT_UPDATE_PACKET) {
        int swarmAddr = packetBuffer[2];
        int swarmIdx = setAndReturnMySwarmIndex(swarmAddr);
        int light = packetBuffer[5] * 256 + packetBuffer[6];

        // record the incoming swarm data
        swarmLights[swarmIdx] = light;
        swarmVersion[swarmIdx] = packetBuffer[4];
        swarmState[swarmIdx] = 0; // Re-assign master
        swarmTimeStamp[swarmIdx] = millis();

        // Check to see if I am master!
        checkAndSetIfMaster();
      } else if (packetBuffer[1] == DEFINE_SERVER_LOGGER_PACKET) {
          Serial.println(">>>>>>>>> DEFINE_SERVER_LOGGER_PACKET Recieved");
          serverAddress = IPAddress(packetBuffer[4], packetBuffer[5], packetBuffer[6], packetBuffer[7]);
          Serial.print("Server address received: ");
          Serial.println(serverAddress);
      } else if (packetBuffer[1] == RESET_SWARM_PACKET) {
        Serial.println(">>>>>>>>> RESET_SWARM_PACKET Recieved");
        masterState = true;
        digitalWrite(MASTER_LED, LOW);
        // initialize light sensor and arrays
        for (int i = 0; i < SWARMSIZE; i++) {
          swarmAddresses[i] = 0;
          swarmLights[i] = 0;
          swarmTimeStamp[i] = -1;
        }
        swarmAddresses[mySwarmID] =  localIP[3];
        swarmVersion[mySwarmID] = VERSIONNUMBER;
        swarmTimeStamp[mySwarmID] = 1;   // I am always in time to myself
        swarmState[mySwarmID] = masterState;
        IPAddress serverAddress = IPAddress(0, 0, 0, 0);
        Serial.println(serverAddress);
        Serial.println("Reset Swarm:  I just BECAME Master (and everybody else!)");
        digitalWrite(0, LOW);
      }
    }
  }
  delay(1);
}

bool isNetworkSilent() {
  return (millis() - lastReceiveTime) > NETWORKSILENT;
}

// send a LIGHT Packet request to the swarms at the given address
void sendLightUpdatePacket(IPAddress & address) {
  // Serial.println("Network too silent, send a packet");
  // set all bytes in the buffer to 0
  memset(packetBuffer, 0, PACKET_SIZE);
  // Initialize values needed to form Light Packet
  // (see URL above for details on the packets)
  packetBuffer[0] = 0xF0;   // StartByte
  packetBuffer[1] = LIGHT_UPDATE_PACKET;     // Packet Type
  packetBuffer[2] = localIP[3];     // Sending Swarm Number
  packetBuffer[3] = masterState;  // 0 = slave, 1 = master
  packetBuffer[4] = VERSIONNUMBER;  // Software Version
  int light = swarmLights[mySwarmID];
  packetBuffer[5] = (light & 0xFF00) >> 8; // light High Byte
  packetBuffer[6] = (light & 0x00FF); // light Low Byte
  packetBuffer[7] = 0x0F;  //End Byte

  // all Light Packet fields have been given values, now
  // you can send a packet requesting coordination
  udp.beginPacketMulticast(address,  localPort, WiFi.localIP());
  udp.write(packetBuffer, PACKET_SIZE);
  udp.endPacket();
}

// Update swamrs life status, check if I'm the master and turn on/off MASTER_LED
void checkAndSetIfMaster() {
  // Swarm is too old, clear data and change to dead
  for (int i = 0; i < SWARMSIZE; i++) {
    int swarmTS = swarmTimeStamp[i];
    if (swarmTS != -1 && swarmTS != 0 && swarmTS != 1 && (millis() - swarmTimeStamp[i] > SWARMTOOOLD)) {
      // Serial.print("Swarm #");Serial.print(i);Serial.println(" is dead.");
      swarmTimeStamp[i] = 0;
      swarmLights[i] = 0;
      swarmState[i] = 0;
    }
  }

  int myLight = swarmLights[mySwarmID];
  int masterIdx = 0;

  // Find the new master
  for (int i = 0; i < SWARMSIZE; i++) {
    if (swarmLights[i] > swarmLights[masterIdx]) masterIdx = i;
  }
  swarmState[masterIdx] = 1;  // Re-assign master here
  if ((masterIdx == mySwarmID) && !masterState) {
    masterState = true;
    Serial.println("I BECOME A MASTER");
    digitalWrite(MASTER_LED, LOW);
  }
  else if ((masterIdx != mySwarmID) && masterState) {
    masterState = false;
    Serial.println("I BECOME A SLAVE");
    digitalWrite(MASTER_LED, HIGH);
  }
  delay(10);
}

// Find swarmIndex from incoming ID in UDP packet
int setAndReturnMySwarmIndex(int incomingID) {
  for (int i = 0; i< SWARMSIZE; i++) {
    if (swarmAddresses[i] == incomingID) return i;
    else if (swarmAddresses[i] == 0) { // not in the system, so put it in
      swarmAddresses[i] = incomingID;
      Serial.println("New swarm added!!");
      return i;
    }
  }  
  
  // if we get here, then we have a new swarm member.   
  // Delete the oldest swarm member and add the new one in 
  // (this will probably be the one that dropped out)
  int oldSwarmID;
  long oldTime;
  oldTime = millis();
  for (int i = 0;  i < SWARMSIZE; i++) {
    if (oldTime > swarmTimeStamp[i]) {
      oldTime = swarmTimeStamp[i];
      oldSwarmID = i;
    }
  }
  // remove the old one and put this one in....
  swarmAddresses[oldSwarmID] = incomingID;
  // the rest will be filled in by Light Packet Receive
  return oldSwarmID;
}

void sendLogToServer()
{
  if (masterState == true)
  {
    if ((serverAddress[0] == 0) && (serverAddress[1] == 0)) return; // Server address undefined
    else {
      // set all bytes in the buffer to 0
      memset(packetBuffer, 0, BUFFERSIZE);

      packetBuffer[0] = 0xF0;   // StartByte
      packetBuffer[1] = LOG_TO_SERVER_PACKET;     // Packet Type
      packetBuffer[2] = localIP[3];     // Sending Swarm Number
      packetBuffer[3] = setAndReturnMySwarmIndex(localIP[3]);  // 0 = slave, 1 = master
      packetBuffer[4] = VERSIONNUMBER;  // Software Version
      packetBuffer[5] = (light & 0xFF00) >> 8; // photoresistor value High Byte
      packetBuffer[6] = (light & 0x00FF); // photoresistor value Low Byte
      packetBuffer[7] = 0x0F;  //End Byte
      udp.beginPacket(serverAddress,  localPort);
      udp.write(packetBuffer, PACKET_SIZE);
      udp.endPacket();
    }
  }
}
