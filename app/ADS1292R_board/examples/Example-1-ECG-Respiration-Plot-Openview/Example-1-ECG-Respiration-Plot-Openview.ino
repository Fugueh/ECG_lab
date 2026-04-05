//////////////////////////////////////////////////////////////////////////////////////////
//
//   Arduino Library for ADS1292R Shield/Breakout
//   用于上位机代码
  
//  |ads1292r 引脚名称 | Arduino 连接         |引脚功能          |
//  |----------------- |:--------------------:|-----------------:|
//  | VDD              | +5V                  |  Supply voltage  |
//  | PWDN/RESET       | D4                   |  Reset           |
//  | START            | D5                   |  Start Input     |
//  | DRDY             | D6                   |  Data Ready Outpt|
//  | CS               | D7                   |  Chip Select     |
//  | MOSI             | D11                  |  Slave In        |
//  | MISO             | D12                  |  Slave Out       |
//  | SCK              | D13                  |  Serial Clock    |
//  | GND              | Gnd                  |  Gnd             |
//
/////////////////////////////////////////////////////////////////////////////////////////


#include "sAds1292r.h"
#include "ecgRespirationAlgo.h"
#include <SPI.h>

volatile uint8_t globalHeartRate = 0;
volatile uint8_t globalRespirationRate=0;

//Pin declartion the other you need are controlled by the SPI library
const int ADS1292_DRDY_PIN = 6;
const int ADS1292_CS_PIN = 7;
const int ADS1292_START_PIN = 5;
const int ADS1292_PWDN_PIN = 4;

#define DEMO_SAMPLE_RATE_HZ      250
#define UART_PACKET_RATE_HZ      50
#define SAMPLES_PER_PACKET       5
#define PACKET_TIME_WINDOW_MS    20

#define RESP_MIN_BPM             6
#define RESP_MAX_BPM             40
#define RESP_INTERVAL_BUFFER_LEN 4

#define PACKET_HEADER_1          0xA5
#define PACKET_HEADER_2          0x5A
#define PACKET_TYPE_ECG_RESP     0x01
#define PACKET_TAIL_1            0x55
#define PACKET_TAIL_2            0xAA

#define PACKET_PAYLOAD_LEN       25
#define PACKET_TOTAL_LEN         30

int16_t ecgWaveBuff, ecgFilterout;
int16_t resWaveBuff,respFilterout;

ads1292r ADS1292R;
ecg_respiration_algorithm ECG_RESPIRATION_ALGORITHM;

struct RespirationRateEstimator
{
  int32_t baseline;
  int32_t smooth;
  int32_t amplitude;
  int16_t previousCentered;
  uint32_t sampleCounter;
  uint32_t lastBreathSample;
  uint16_t breathIntervals[RESP_INTERVAL_BUFFER_LEN];
  uint8_t intervalIndex;
  uint8_t intervalCount;
  uint8_t respirationRate;
  bool armed;
};

RespirationRateEstimator respRateEstimator = {0, 0, 0, 0, 0, 0, {0}, 0, 0, 0, false};

struct EcgRespSampleFrame
{
  int16_t ecg;
  int16_t resp;
};

EcgRespSampleFrame samplePacketBuffer[SAMPLES_PER_PACKET];
uint8_t samplePacketIndex = 0;
uint8_t packetSequence = 0;

static void writeInt16LE(int16_t value)
{
  Serial.write((uint8_t)(value & 0xFF));
  Serial.write((uint8_t)((value >> 8) & 0xFF));
}

void sendBufferedSamplesThroughUART(void)
{
  Serial.write((uint8_t)PACKET_HEADER_1);
  Serial.write((uint8_t)PACKET_HEADER_2);
  Serial.write((uint8_t)PACKET_PAYLOAD_LEN);
  Serial.write((uint8_t)PACKET_TYPE_ECG_RESP);
  Serial.write(packetSequence++);
  Serial.write((uint8_t)SAMPLES_PER_PACKET);

  for (uint8_t i = 0; i < SAMPLES_PER_PACKET; ++i)
  {
    writeInt16LE(samplePacketBuffer[i].ecg);
    writeInt16LE(samplePacketBuffer[i].resp);
  }

  Serial.write((uint8_t)globalHeartRate);
  Serial.write((uint8_t)globalRespirationRate);
  Serial.write((uint8_t)PACKET_TAIL_1);
  Serial.write((uint8_t)PACKET_TAIL_2);
}

void bufferSampleAndSendWhenReady(int16_t ecgSample, int16_t respSample)
{
  samplePacketBuffer[samplePacketIndex].ecg = ecgSample;
  samplePacketBuffer[samplePacketIndex].resp = respSample;
  samplePacketIndex++;

  if (samplePacketIndex >= SAMPLES_PER_PACKET)
  {
    sendBufferedSamplesThroughUART();
    samplePacketIndex = 0;
  }
}

static uint8_t updateRespirationRateEstimate(int16_t rawRespSample)
{
  RespirationRateEstimator *state = &respRateEstimator;
  const uint16_t minBreathIntervalSamples = (DEMO_SAMPLE_RATE_HZ * 60UL) / RESP_MAX_BPM;
  const uint16_t maxBreathIntervalSamples = (DEMO_SAMPLE_RATE_HZ * 60UL) / RESP_MIN_BPM;

  state->sampleCounter++;

  if (state->sampleCounter == 1)
  {
    state->baseline = rawRespSample;
    state->smooth = rawRespSample;
  }

  // Slow baseline tracker for impedance drift removal.
  state->baseline += ((int32_t)rawRespSample - state->baseline) >> 8;
  // Short smoothing to suppress packet-to-packet jitter while keeping the respiratory envelope.
  state->smooth += ((int32_t)rawRespSample - state->smooth) >> 3;

  int16_t centeredResp = (int16_t)(state->smooth - state->baseline);
  int32_t absCenteredResp = centeredResp >= 0 ? centeredResp : -centeredResp;
  state->amplitude += (absCenteredResp - state->amplitude) >> 6;

  int16_t dynamicThreshold = (int16_t)(state->amplitude >> 2);
  if (dynamicThreshold < 12)
  {
    dynamicThreshold = 12;
  }
  int16_t releaseThreshold = dynamicThreshold >> 1;

  if (centeredResp < -releaseThreshold)
  {
    state->armed = true;
  }

  if (state->armed && state->previousCentered < dynamicThreshold && centeredResp >= dynamicThreshold)
  {
    if (state->lastBreathSample != 0)
    {
      uint32_t intervalSamples = state->sampleCounter - state->lastBreathSample;

      if (intervalSamples >= minBreathIntervalSamples && intervalSamples <= maxBreathIntervalSamples)
      {
        state->breathIntervals[state->intervalIndex] = (uint16_t)intervalSamples;
        state->intervalIndex = (state->intervalIndex + 1) % RESP_INTERVAL_BUFFER_LEN;

        if (state->intervalCount < RESP_INTERVAL_BUFFER_LEN)
        {
          state->intervalCount++;
        }

        uint32_t intervalSum = 0;
        for (uint8_t i = 0; i < state->intervalCount; ++i)
        {
          intervalSum += state->breathIntervals[i];
        }

        if (intervalSum > 0)
        {
          uint32_t averageInterval = intervalSum / state->intervalCount;
          state->respirationRate = (uint8_t)((60UL * DEMO_SAMPLE_RATE_HZ) / averageInterval);
        }
      }
    }

    state->lastBreathSample = state->sampleCounter;
    state->armed = false;
  }

  if (state->lastBreathSample != 0 && (state->sampleCounter - state->lastBreathSample) > (DEMO_SAMPLE_RATE_HZ * 12UL))
  {
    state->respirationRate = 0;
    state->intervalCount = 0;
    state->intervalIndex = 0;
  }

  state->previousCentered = centeredResp;
  return state->respirationRate;
}

void setup()
{
  delay(2000);

  SPI.begin();
  SPI.setBitOrder(MSBFIRST);
  //CPOL = 0, CPHA = 1
  SPI.setDataMode(SPI_MODE1);
  // Selecting 1Mhz clock for SPI
  SPI.setClockDivider(SPI_CLOCK_DIV16);

  pinMode(ADS1292_DRDY_PIN, INPUT);
  pinMode(ADS1292_CS_PIN, OUTPUT);
  pinMode(ADS1292_START_PIN, OUTPUT);
  pinMode(ADS1292_PWDN_PIN, OUTPUT);

  Serial.begin(57600);
  ADS1292R.ads1292Init(ADS1292_CS_PIN,ADS1292_PWDN_PIN,ADS1292_START_PIN);
  Serial.println("Initiliziation is done");
  // Demo timing summary:
  // ADS1292R samples ECG and RESP simultaneously at 250 SPS.
  // Each UART packet contains 5 consecutive sampling instants.
  // Each packet therefore covers a 20 ms time window.
  // UART packet rate is 50 Hz.
}

void loop()
{
  ads1292OutputValues ecgRespirationValues;
  boolean ret = ADS1292R.getAds1292EcgAndRespirationSamples(ADS1292_DRDY_PIN,ADS1292_CS_PIN,&ecgRespirationValues);

  if (ret == true)
  {
    ecgWaveBuff = (int16_t)(ecgRespirationValues.sDaqVals[1] >> 8) ;  // ignore the lower 8 bits out of 24bits
    resWaveBuff = (int16_t)(ecgRespirationValues.sresultTempResp>>8) ;

    if(ecgRespirationValues.leadoffDetected == false)
    {
      ECG_RESPIRATION_ALGORITHM.ECG_ProcessCurrSample(&ecgWaveBuff, &ecgFilterout);   // filter out the line noise @40Hz cutoff 161 order
      ECG_RESPIRATION_ALGORITHM.QRS_Algorithm_Interface(ecgFilterout,&globalHeartRate); // calculate
      respFilterout = resWaveBuff;
      globalRespirationRate = updateRespirationRateEstimate(resWaveBuff);
      // RESP algorithm is kept optional here. Raw RESP samples are packetized to keep sampling continuous and packet parsing simple.
      // respFilterout = ECG_RESPIRATION_ALGORITHM.Resp_ProcessCurrSample(resWaveBuff);
      // ECG_RESPIRATION_ALGORITHM.RESP_Algorithm_Interface(respFilterout,&globalRespirationRate);

    }else{
      ecgFilterout = 0;
      respFilterout = 0;
      globalHeartRate = 0;
      globalRespirationRate = 0;
    }

    bufferSampleAndSendWhenReady(ecgFilterout, respFilterout);
  }
}
