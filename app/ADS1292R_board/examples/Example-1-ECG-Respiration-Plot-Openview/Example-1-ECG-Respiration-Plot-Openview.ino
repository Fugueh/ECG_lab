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
#define PACKET_HEADER_1          0xA5
#define PACKET_HEADER_2          0x5A
#define PACKET_TYPE_ECG_RESP_RAW 0x03
#define PACKET_TAIL_1            0x55
#define PACKET_TAIL_2            0xAA

#define ECG_RAW_BYTES_PER_SAMPLE 3
#define RESP_BYTES_PER_SAMPLE    2
#define PACKET_PAYLOAD_LEN       30
#define PACKET_TOTAL_LEN         35

int16_t ecgWaveBuff, ecgFilterout;
int16_t resWaveBuff,respFilterout;
int32_t ecgRawSample;

ads1292r ADS1292R;
ecg_respiration_algorithm ECG_RESPIRATION_ALGORITHM;

struct RespirationRateEstimator
{
  float amplitude;
  float previousPreviousSample;
  float previousSample;
  uint32_t sampleCounter;
  uint32_t lastPeakSample;
  uint8_t respirationRate;
  bool armed;
};

struct BiquadState
{
  float z1;
  float z2;
};

static const float RESP_BANDPASS_SOS[4][6] = {
  {4.357743358690126376e-09f, 8.715486717380252751e-09f, 4.357743358690126376e-09f, 1.0f, -1.972519892168127731e+00f, 9.727548804702866869e-01f},
  {1.0f, 2.0f, 1.0f, 1.0f, -1.988126592172564822e+00f, 9.884243007557537153e-01f},
  {1.0f, -2.0f, 1.0f, 1.0f, -1.997437921280502460e+00f, 9.974399702362736209e-01f},
  {1.0f, -2.0f, 1.0f, 1.0f, -1.999139101574710420e+00f, 9.991407330723069968e-01f}
};

RespirationRateEstimator respRateEstimator = {0.0f, 0.0f, 0.0f, 0, 0, 0, false};
BiquadState respBandpassState[4] = {{0.0f, 0.0f}, {0.0f, 0.0f}, {0.0f, 0.0f}, {0.0f, 0.0f}};

static float applyRespBandpassFilter(int16_t rawRespSample)
{
  float stageInput = (float)rawRespSample;

  for (uint8_t i = 0; i < 4; ++i)
  {
    const float *sos = RESP_BANDPASS_SOS[i];
    BiquadState *state = &respBandpassState[i];
    float stageOutput = sos[0] * stageInput + state->z1;
    state->z1 = sos[1] * stageInput - sos[4] * stageOutput + state->z2;
    state->z2 = sos[2] * stageInput - sos[5] * stageOutput;
    stageInput = stageOutput;
  }

  return stageInput;
}

static void resetRespRatePipeline(void)
{
  respRateEstimator.amplitude = 0.0f;
  respRateEstimator.previousPreviousSample = 0.0f;
  respRateEstimator.previousSample = 0.0f;
  respRateEstimator.sampleCounter = 0;
  respRateEstimator.lastPeakSample = 0;
  respRateEstimator.respirationRate = 0;
  respRateEstimator.armed = false;
  for (uint8_t i = 0; i < 4; ++i)
  {
    respBandpassState[i].z1 = 0.0f;
    respBandpassState[i].z2 = 0.0f;
  }
}

struct EcgRespSampleFrame
{
  int32_t ecgRaw;
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

static void writeInt24LE(int32_t value)
{
  uint32_t packed = ((uint32_t)value) & 0x00FFFFFFUL;
  Serial.write((uint8_t)(packed & 0xFF));
  Serial.write((uint8_t)((packed >> 8) & 0xFF));
  Serial.write((uint8_t)((packed >> 16) & 0xFF));
}

void sendBufferedSamplesThroughUART(void)
{
  Serial.write((uint8_t)PACKET_HEADER_1);
  Serial.write((uint8_t)PACKET_HEADER_2);
  Serial.write((uint8_t)PACKET_PAYLOAD_LEN);
  Serial.write((uint8_t)PACKET_TYPE_ECG_RESP_RAW);
  Serial.write(packetSequence++);
  Serial.write((uint8_t)SAMPLES_PER_PACKET);

  for (uint8_t i = 0; i < SAMPLES_PER_PACKET; ++i)
  {
    writeInt24LE(samplePacketBuffer[i].ecgRaw);
    writeInt16LE(samplePacketBuffer[i].resp);
  }

  Serial.write((uint8_t)globalHeartRate);
  Serial.write((uint8_t)globalRespirationRate);
  Serial.write((uint8_t)PACKET_TAIL_1);
  Serial.write((uint8_t)PACKET_TAIL_2);
}

void bufferSampleAndSendWhenReady(int32_t ecgRaw, int16_t respSample)
{
  samplePacketBuffer[samplePacketIndex].ecgRaw = ecgRaw;
  samplePacketBuffer[samplePacketIndex].resp = respSample;
  samplePacketIndex++;

  if (samplePacketIndex >= SAMPLES_PER_PACKET)
  {
    sendBufferedSamplesThroughUART();
    samplePacketIndex = 0;
  }
}

static uint8_t updateRespirationRateEstimate(float filteredRespSample)
{
  RespirationRateEstimator *state = &respRateEstimator;
  const uint16_t minBreathIntervalSamples = (DEMO_SAMPLE_RATE_HZ * 60UL) / RESP_MAX_BPM;
  const uint16_t maxBreathIntervalSamples = (DEMO_SAMPLE_RATE_HZ * 60UL) / RESP_MIN_BPM;

  state->sampleCounter++;

  float absResp = filteredRespSample >= 0.0f ? filteredRespSample : -filteredRespSample;
  state->amplitude += (absResp - state->amplitude) * 0.015625f;

  float dynamicThreshold = state->amplitude * 0.25f;
  if (dynamicThreshold < 8.0f)
  {
    dynamicThreshold = 8.0f;
  }
  float releaseThreshold = dynamicThreshold * 0.5f;

  if (filteredRespSample < -releaseThreshold)
  {
    state->armed = true;
  }

  if (
    state->armed &&
    state->previousSample >= dynamicThreshold &&
    state->previousPreviousSample < state->previousSample &&
    state->previousSample >= filteredRespSample
  )
  {
    uint32_t peakSample = state->sampleCounter - 1;

    if (state->lastPeakSample != 0)
    {
      uint32_t intervalSamples = peakSample - state->lastPeakSample;

      if (intervalSamples >= minBreathIntervalSamples && intervalSamples <= maxBreathIntervalSamples)
      {
        state->respirationRate = (uint8_t)((60UL * DEMO_SAMPLE_RATE_HZ) / intervalSamples);
      }
    }

    state->lastPeakSample = peakSample;
    state->armed = false;
  }

  if (state->lastPeakSample != 0 && (state->sampleCounter - state->lastPeakSample) > (DEMO_SAMPLE_RATE_HZ * 12UL))
  {
    state->respirationRate = 0;
  }

  state->previousPreviousSample = state->previousSample;
  state->previousSample = filteredRespSample;
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
  // ECG is transmitted as raw signed 24-bit ADC codes to preserve fidelity.
  // RESP remains 16-bit for compactness.
  // Each packet therefore covers a 20 ms time window.
  // UART packet rate is 50 Hz.
}

void loop()
{
  ads1292OutputValues ecgRespirationValues;
  boolean ret = ADS1292R.getAds1292EcgAndRespirationSamples(ADS1292_DRDY_PIN,ADS1292_CS_PIN,&ecgRespirationValues);

  if (ret == true)
  {
    float respRateSignal = 0.0f;
    ecgRawSample = (int32_t)ecgRespirationValues.sDaqVals[1];
    ecgWaveBuff = (int16_t)(ecgRawSample >> 8) ;  // ignore the lower 8 bits out of 24bits
    resWaveBuff = (int16_t)(ecgRespirationValues.sresultTempResp>>8) ;

    if(ecgRespirationValues.leadoffDetected == false)
    {
      ECG_RESPIRATION_ALGORITHM.ECG_ProcessCurrSample(&ecgWaveBuff, &ecgFilterout);   // filter out the line noise @40Hz cutoff 161 order
      ECG_RESPIRATION_ALGORITHM.QRS_Algorithm_Interface(ecgFilterout,&globalHeartRate); // calculate
      respFilterout = resWaveBuff;
      respRateSignal = applyRespBandpassFilter(resWaveBuff);
      globalRespirationRate = updateRespirationRateEstimate(respRateSignal);
      // RESP algorithm is kept optional here. Raw RESP samples are packetized to keep sampling continuous and packet parsing simple.
      // respFilterout = ECG_RESPIRATION_ALGORITHM.Resp_ProcessCurrSample(resWaveBuff);
      // ECG_RESPIRATION_ALGORITHM.RESP_Algorithm_Interface(respFilterout,&globalRespirationRate);

    }else{
      ecgFilterout = 0;
      respFilterout = 0;
      globalHeartRate = 0;
      globalRespirationRate = 0;
      resetRespRatePipeline();
    }

    // Keep the legacy filtered branch on-board for HR estimation,
    // but send the raw 24-bit ECG samples over UART.
    bufferSampleAndSendWhenReady(ecgRawSample, respFilterout);
  }
}
