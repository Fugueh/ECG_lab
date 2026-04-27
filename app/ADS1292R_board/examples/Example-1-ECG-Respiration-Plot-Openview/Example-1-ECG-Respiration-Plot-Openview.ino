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
#define RESP_TA_HISTORY_LEN      32
#define RESP_LOW_TA_FACTOR       0.25f
#define RESP_MIN_PHASE_RATIO     0.10f
#define PACKET_HEADER_1          0xA5
#define PACKET_HEADER_2          0x5A
#define PACKET_TYPE_ECG_RESP_RAW 0x03
#define PACKET_TAIL_1            0x55
#define PACKET_TAIL_2            0xAA

#define ECG_RAW_BYTES_PER_SAMPLE 3
#define RESP_BYTES_PER_SAMPLE    2
#define PACKET_PAYLOAD_LEN       30
#define PACKET_TOTAL_LEN         35
#define ECG_MWI_WINDOW_SAMPLES   38
#define ECG_QRS_REFRACTORY_SAMPLES 50
#define ECG_MIN_RR_SAMPLES       38
#define ECG_MAX_RR_SAMPLES       300
#define ECG_STARTUP_IGNORE_SAMPLES 250
#define ECG_INIT_WINDOW_END_SAMPLES 500

int16_t ecgWaveBuff, ecgFilterout;
int16_t resWaveBuff,respFilterout;
int32_t ecgRawSample;

ads1292r ADS1292R;
ecg_respiration_algorithm ECG_RESPIRATION_ALGORITHM;

struct RespirationRateEstimator
{
  float previousFilteredSample;
  float currentPositivePeak;
  float currentNegativeTrough;
  float lastCompletedPositivePeak;
  float lastCompletedNegativeTrough;
  float tidalAmplitudeHistory[RESP_TA_HISTORY_LEN];
  uint32_t sampleCounter;
  uint32_t previousRisingCrossingSample;
  uint32_t lastFallingCrossingSample;
  uint8_t tidalAmplitudeCount;
  uint8_t tidalAmplitudeIndex;
  uint8_t respirationRate;
  bool positivePhaseActive;
  bool negativePhaseActive;
  bool havePositivePeak;
  bool haveNegativeTrough;
};

struct BiquadState
{
  float z1;
  float z2;
};

struct HeartRateEstimator
{
  float derivativeHistory[5];
  float mwiBuffer[ECG_MWI_WINDOW_SAMPLES];
  float mwiSum;
  float previousPreviousIntegrated;
  float previousIntegrated;
  float signalPeak;
  float noisePeak;
  float threshold;
  float warmupPeak;
  uint32_t sampleCounter;
  uint32_t lastQrsSample;
  uint8_t heartRate;
};

static const float RESP_BANDPASS_SOS[2][6] = {
  {4.176161019517901575e-04f, 8.352322039035803150e-04f, 4.176161019517901575e-04f, 1.0f, -1.946195450634147006e+00f, 9.479176761701030296e-01f},
  {1.0f, -2.0f, 1.0f, 1.0f, -1.994838446465836856e+00f, 9.948548513896050549e-01f}
};

static const float ECG_BANDPASS_SOS[2][6] = {
  {1.335920002785649305e-02f, 2.671840005571298610e-02f, 1.335920002785649305e-02f, 1.0f, -1.681353856955223547e+00f, 7.798921439604280526e-01f},
  {1.0f, -2.0f, 1.0f, 1.0f, -1.879593595875511225e+00f, 8.987098877918257012e-01f}
};

RespirationRateEstimator respRateEstimator = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, {0.0f}, 0, 0, 0, 0, 0, false, false, false, false};
HeartRateEstimator heartRateEstimator = {{0.0f}, {0.0f}, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0};
BiquadState ecgBandpassState[2] = {{0.0f, 0.0f}, {0.0f, 0.0f}};
BiquadState respBandpassState[2] = {{0.0f, 0.0f}, {0.0f, 0.0f}};

static float applyEcgBandpassFilter(int16_t rawEcgSample)
{
  float stageInput = (float)rawEcgSample;

  for (uint8_t i = 0; i < 2; ++i)
  {
    const float *sos = ECG_BANDPASS_SOS[i];
    BiquadState *state = &ecgBandpassState[i];
    float stageOutput = sos[0] * stageInput + state->z1;
    state->z1 = sos[1] * stageInput - sos[4] * stageOutput + state->z2;
    state->z2 = sos[2] * stageInput - sos[5] * stageOutput;
    stageInput = stageOutput;
  }

  return stageInput;
}

static float applyRespBandpassFilter(int16_t rawRespSample)
{
  float stageInput = (float)rawRespSample;

  for (uint8_t i = 0; i < 2; ++i)
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

static void resetHeartRatePipeline(void)
{
  for (uint8_t i = 0; i < 5; ++i)
  {
    heartRateEstimator.derivativeHistory[i] = 0.0f;
  }
  for (uint8_t i = 0; i < ECG_MWI_WINDOW_SAMPLES; ++i)
  {
    heartRateEstimator.mwiBuffer[i] = 0.0f;
  }
  heartRateEstimator.mwiSum = 0.0f;
  heartRateEstimator.previousPreviousIntegrated = 0.0f;
  heartRateEstimator.previousIntegrated = 0.0f;
  heartRateEstimator.signalPeak = 0.0f;
  heartRateEstimator.noisePeak = 0.0f;
  heartRateEstimator.threshold = 0.0f;
  heartRateEstimator.warmupPeak = 0.0f;
  heartRateEstimator.sampleCounter = 0;
  heartRateEstimator.lastQrsSample = 0;
  heartRateEstimator.heartRate = 0;

  for (uint8_t i = 0; i < 2; ++i)
  {
    ecgBandpassState[i].z1 = 0.0f;
    ecgBandpassState[i].z2 = 0.0f;
  }
}

static void resetRespRatePipeline(void)
{
  respRateEstimator.previousFilteredSample = 0.0f;
  respRateEstimator.currentPositivePeak = 0.0f;
  respRateEstimator.currentNegativeTrough = 0.0f;
  respRateEstimator.lastCompletedPositivePeak = 0.0f;
  respRateEstimator.lastCompletedNegativeTrough = 0.0f;
  for (uint8_t i = 0; i < RESP_TA_HISTORY_LEN; ++i)
  {
    respRateEstimator.tidalAmplitudeHistory[i] = 0.0f;
  }
  respRateEstimator.sampleCounter = 0;
  respRateEstimator.previousRisingCrossingSample = 0;
  respRateEstimator.lastFallingCrossingSample = 0;
  respRateEstimator.tidalAmplitudeCount = 0;
  respRateEstimator.tidalAmplitudeIndex = 0;
  respRateEstimator.respirationRate = 0;
  respRateEstimator.positivePhaseActive = false;
  respRateEstimator.negativePhaseActive = false;
  respRateEstimator.havePositivePeak = false;
  respRateEstimator.haveNegativeTrough = false;
  for (uint8_t i = 0; i < 2; ++i)
  {
    respBandpassState[i].z1 = 0.0f;
    respBandpassState[i].z2 = 0.0f;
  }
}

static float computeRespTidalAmplitudeThreshold(void)
{
  float sorted[RESP_TA_HISTORY_LEN];
  uint8_t count = respRateEstimator.tidalAmplitudeCount;
  uint8_t i = 0;
  uint8_t j = 0;

  if (count < 4)
  {
    return 0.0f;
  }

  for (i = 0; i < count; ++i)
  {
    sorted[i] = respRateEstimator.tidalAmplitudeHistory[i];
  }

  for (i = 1; i < count; ++i)
  {
    float key = sorted[i];
    j = i;
    while (j > 0 && sorted[j - 1] > key)
    {
      sorted[j] = sorted[j - 1];
      --j;
    }
    sorted[j] = key;
  }

  i = (uint8_t)((count - 1) * 0.8f);
  return sorted[i] * RESP_LOW_TA_FACTOR;
}

static void appendRespTidalAmplitude(float tidalAmplitude)
{
  respRateEstimator.tidalAmplitudeHistory[respRateEstimator.tidalAmplitudeIndex] = tidalAmplitude;
  respRateEstimator.tidalAmplitudeIndex = (uint8_t)((respRateEstimator.tidalAmplitudeIndex + 1) % RESP_TA_HISTORY_LEN);
  if (respRateEstimator.tidalAmplitudeCount < RESP_TA_HISTORY_LEN)
  {
    respRateEstimator.tidalAmplitudeCount++;
  }
}

static uint8_t updateHeartRateEstimate(int16_t rawEcgSample)
{
  HeartRateEstimator *state = &heartRateEstimator;
  float bandpassed = applyEcgBandpassFilter(rawEcgSample);
  uint8_t mwiIndex = 0;
  float derivative = 0.0f;
  float squared = 0.0f;
  float integrated = 0.0f;

  state->sampleCounter++;

  for (int8_t i = 4; i > 0; --i)
  {
    state->derivativeHistory[i] = state->derivativeHistory[i - 1];
  }
  state->derivativeHistory[0] = bandpassed;

  derivative = (
    2.0f * state->derivativeHistory[0] +
    state->derivativeHistory[1] -
    state->derivativeHistory[3] -
    2.0f * state->derivativeHistory[4]
  ) * 0.125f;
  squared = derivative * derivative;

  mwiIndex = (uint8_t)(state->sampleCounter % ECG_MWI_WINDOW_SAMPLES);
  state->mwiSum -= state->mwiBuffer[mwiIndex];
  state->mwiBuffer[mwiIndex] = squared;
  state->mwiSum += squared;
  integrated = state->mwiSum / ECG_MWI_WINDOW_SAMPLES;

  if (
    state->sampleCounter > 2 &&
    state->previousIntegrated > state->previousPreviousIntegrated &&
    state->previousIntegrated >= integrated
  )
  {
    float candidatePeak = state->previousIntegrated;
    uint32_t peakSample = state->sampleCounter - 1;

    if (state->sampleCounter <= ECG_STARTUP_IGNORE_SAMPLES)
    {
      // Ignore the initial band-pass transient caused by the large ECG DC offset.
    }
    else if (state->sampleCounter <= ECG_INIT_WINDOW_END_SAMPLES)
    {
      if (candidatePeak > state->warmupPeak)
      {
        state->warmupPeak = candidatePeak;
      }
    }
    else
    {
      if (state->signalPeak <= 0.0f && state->warmupPeak > 0.0f)
      {
        state->signalPeak = state->warmupPeak;
        state->noisePeak = state->warmupPeak * 0.125f;
      }
      else if (state->signalPeak <= 0.0f)
      {
        state->signalPeak = candidatePeak;
        state->noisePeak = candidatePeak * 0.125f;
      }

      if (state->threshold <= 0.0f)
      {
        state->threshold = state->noisePeak + 0.25f * (state->signalPeak - state->noisePeak);
      }

      if (
        candidatePeak > state->threshold &&
        (state->lastQrsSample == 0 || (peakSample - state->lastQrsSample) >= ECG_QRS_REFRACTORY_SAMPLES)
      )
      {
        state->signalPeak = 0.125f * candidatePeak + 0.875f * state->signalPeak;

        if (state->lastQrsSample != 0)
        {
          uint32_t rrSamples = peakSample - state->lastQrsSample;
          if (rrSamples >= ECG_MIN_RR_SAMPLES && rrSamples <= ECG_MAX_RR_SAMPLES)
          {
            state->heartRate = (uint8_t)((60UL * DEMO_SAMPLE_RATE_HZ) / rrSamples);
          }
        }

        state->lastQrsSample = peakSample;
      }
      else
      {
        state->noisePeak = 0.125f * candidatePeak + 0.875f * state->noisePeak;
      }

      state->threshold = state->noisePeak + 0.25f * (state->signalPeak - state->noisePeak);
    }
  }

  if (state->lastQrsSample != 0 && (state->sampleCounter - state->lastQrsSample) > ECG_MAX_RR_SAMPLES)
  {
    state->heartRate = 0;
    state->lastQrsSample = 0;
  }

  state->previousPreviousIntegrated = state->previousIntegrated;
  state->previousIntegrated = integrated;
  return state->heartRate;
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
  bool risingCrossing = false;
  bool fallingCrossing = false;

  state->sampleCounter++;

  risingCrossing = (state->previousFilteredSample <= 0.0f && filteredRespSample > 0.0f);
  fallingCrossing = (state->previousFilteredSample >= 0.0f && filteredRespSample < 0.0f);

  if (filteredRespSample >= 0.0f)
  {
    if (!state->positivePhaseActive)
    {
      state->positivePhaseActive = true;
      state->currentPositivePeak = filteredRespSample;
    }
    else if (filteredRespSample > state->currentPositivePeak)
    {
      state->currentPositivePeak = filteredRespSample;
    }
    state->negativePhaseActive = false;
  }
  else
  {
    if (!state->negativePhaseActive)
    {
      state->negativePhaseActive = true;
      state->currentNegativeTrough = filteredRespSample;
    }
    else if (filteredRespSample < state->currentNegativeTrough)
    {
      state->currentNegativeTrough = filteredRespSample;
    }
    state->positivePhaseActive = false;
  }

  if (fallingCrossing)
  {
    state->lastFallingCrossingSample = state->sampleCounter;
    state->lastCompletedPositivePeak = state->currentPositivePeak;
    state->havePositivePeak = true;
  }

  if (risingCrossing)
  {
    state->lastCompletedNegativeTrough = state->currentNegativeTrough;
    state->haveNegativeTrough = true;

    if (
      state->previousRisingCrossingSample != 0 &&
      state->lastFallingCrossingSample > state->previousRisingCrossingSample &&
      state->havePositivePeak &&
      state->haveNegativeTrough
    )
    {
      uint32_t cycleSamples = state->sampleCounter - state->previousRisingCrossingSample;
      uint32_t inspiratorySamples = state->lastFallingCrossingSample - state->previousRisingCrossingSample;
      uint32_t expiratorySamples = state->sampleCounter - state->lastFallingCrossingSample;
      uint32_t minPhaseSamples = (uint32_t)(cycleSamples * RESP_MIN_PHASE_RATIO);
      float tidalAmplitude = state->lastCompletedPositivePeak - state->lastCompletedNegativeTrough;
      float lowTaThreshold = computeRespTidalAmplitudeThreshold();

      if (
        cycleSamples >= minBreathIntervalSamples &&
        cycleSamples <= maxBreathIntervalSamples &&
        inspiratorySamples >= minPhaseSamples &&
        expiratorySamples >= minPhaseSamples &&
        tidalAmplitude > lowTaThreshold
      )
      {
        state->respirationRate = (uint8_t)((60UL * DEMO_SAMPLE_RATE_HZ) / cycleSamples);
        appendRespTidalAmplitude(tidalAmplitude);
      }
    }

    state->previousRisingCrossingSample = state->sampleCounter;
  }

  if (state->previousRisingCrossingSample != 0 && (state->sampleCounter - state->previousRisingCrossingSample) > (DEMO_SAMPLE_RATE_HZ * 12UL))
  {
    state->respirationRate = 0;
  }

  state->previousFilteredSample = filteredRespSample;
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
      globalHeartRate = updateHeartRateEstimate(ecgWaveBuff);
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
      resetHeartRatePipeline();
      resetRespRatePipeline();
    }

    // Keep the legacy filtered branch on-board for HR estimation,
    // but send the raw 24-bit ECG samples over UART.
    bufferSampleAndSendWhenReady(ecgRawSample, respFilterout);
  }
}
