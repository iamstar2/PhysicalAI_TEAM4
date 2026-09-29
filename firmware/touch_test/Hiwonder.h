#include "Wire.h"
#ifndef HIWONDER_H
#define HIWONDER_H

#include <Arduino.h>

#define Freq_default 1000
#define Channel_default 11
#define Pin_default 21
#define Key_Pin 5
#define Touch_Pin 33
#define Led_Pin 18
#define SCL1 23
#define SDA1 22
#define SCL2 13
#define SDA2 19

/* Ultrasound */
#define ULTRASOUND_I2C_ADDR 0x77  //발광 초음파 모듈 IIC 주소
#define DISTANCE_ADDR 0
#define DISDENCE_L    0
#define DISDENCE_H    1
#define RGB_WORK_MODE 2//RGB 램프 모드, 0: 사용자 정의 모드   1: 브리딩(호흡) 모드  기본값 0
#define RGB1_R      3//1번 프로브의 R값, 0~255, 기본값 0
#define RGB1_G      4//기본값 0
#define RGB1_B      5//기본값 255
#define RGB2_R      6//2번 프로브의 R값, 0~255, 기본값 0
#define RGB2_G      7//기본값 0
#define RGB2_B      8//기본값 255
#define RGB1_R_BREATHING_CYCLE      9 //브리딩 모드일 때 1번 프로브 R의 호흡 주기, 단위 100ms, 기본값 0
#define RGB1_G_BREATHING_CYCLE      10
#define RGB1_B_BREATHING_CYCLE      11
#define RGB2_R_BREATHING_CYCLE      12//2번 프로브
#define RGB2_G_BREATHING_CYCLE      13
#define RGB2_B_BREATHING_CYCLE      14
#define RGB_WORK_SIMPLE_MODE    0 //조명 설정 모드
#define RGB_WORK_BREATHING_MODE   1 //브리딩(호흡) 모드
#define FILTER_N 3
#define DISTANCE_ERRO 65535

/* ASRSensor */
#define ASR_I2C_ADDR		0x79 //음성 인식 모듈 IIC 주소
#define ASR_RESULT_ADDR           100
//인식 결과 저장 위치. 이 주소의 값을 계속 읽어 음성이 인식되었는지 판단하며, 값에 따라 서로 다른 음성에 대응함
#define ASR_WORDS_ERASE_ADDR      101//모든 단어 항목 삭제
#define ASR_MODE_ADDR             102
//인식 모드 설정, 값 범위 1~3
//1: 반복 인식 모드. 상태 램프 항상 켜짐(기본 모드)
//2: 암호(구령) 모드, 첫 번째 단어 항목을 암호로 사용. 상태 램프는 꺼져 있다가 암호어가 인식되면 켜지고, 새로운 음성 인식을 기다린 뒤 인식 결과를 읽으면 꺼짐
//3: 버튼 모드, 버튼을 누르면 인식을 시작하고 누르지 않으면 인식하지 않음. 정전 시에도 저장 지원. 상태 램프는 버튼을 누르면 켜지고 누르지 않으면 꺼짐
#define ASR_ADD_WORDS_ADDR        160//단어 항목 추가 주소, 정전 시에도 저장 지원

/* MP3Sensor */
#define MP3_I2C_ADDR    0x7B //MP3 모듈 IIC 주소
#define MP3_PLAY_NUM_ADDR         1//지정 트랙 재생, 0~3000, 하위 바이트 먼저 상위 바이트 나중
#define MP3_PLAY_ADDR             5//재생
#define MP3_PAUSE_ADDR            6//일시정지
#define MP3_PREV_ADDR             8//이전 곡
#define MP3_NEXT_ADDR             9//다음 곡
#define MP3_VOL_VALUE_ADDR        12//음량 크기 지정 0~30
#define MP3_SINGLE_LOOP_ON_ADDR   13//한 곡 반복 켜기, 재생 중에 켜야 유효함
#define MP3_SINGLE_LOOP_OFF_ADDR  14//한 곡 반복 끄기
#define MP3_MAXCOUNT  3001

#define ESP32S3_IIC_ADDR 0x53
#define RED 0
#define YELLOW 1
#define GREEN 2
#define BLUE 3
#define BLACK 4
#define FACE_CENTER_ADDR 0xB0
#define COLOR_ADDR 0xC5
#define COLOR_FOLLOW_ADDR 0xC0
#define Line_FOLLOW_UP_ADDR 0xA0
#define Line_FOLLOW_DOWN_ADDR 0xA1


static int filter_buf[FILTER_N + 1];
typedef void (*CallbackFunc)();

bool wireWriteByte(TwoWire *iic, uint8_t addr, uint8_t val);
bool wireWriteDataArray(TwoWire *iic, uint8_t addr, uint8_t reg,uint8_t *val,unsigned int len);
int wireReadDataArray(TwoWire *iic, uint8_t addr, uint8_t reg, uint8_t *val, unsigned int len);
bool wireWriteWords(TwoWire *iic, uint8_t addr, uint8_t reg,uint8_t idNum,unsigned char *words);

void taskRun(void *p);
void startMain(CallbackFunc ncb);

extern TwoWire IIC1;
extern TwoWire IIC2;

class PowerBuzzer{
  private:
    int Buzzer_freq;
    int Buzzer_channel;
    int Buzzer_Pin;
    int BatteryValue;
    int duty_value;
    int time_value;
    bool bt_open;
    bool bt_state;
    bool duty_flag;
    bool userTone;
    TaskHandle_t Battery_TaskHandel;
    static void Buzzer_Task(void *p);
  
  protected:
    void Buzzer_init(void);

  public:
    PowerBuzzer(void){
      Buzzer_freq = Freq_default; 
      Buzzer_channel = Channel_default; 
      Buzzer_Pin = Pin_default;
      bt_open = true;
      bt_state = false;
      duty_flag = false;
      userTone = false;
      Battery_TaskHandel = NULL;
    };
    
    void playTone(int duty, int btime, bool bg_State);
    void setVolume(int freq);
    int readBattery(void);
    void disableLowPowerAlarm(void);
};

class Button{
  private:
    int bt_key;
    bool clicked_state;
    CallbackFunc clicked_cb;
    CallbackFunc longpressed_cb;
    TaskHandle_t Button_TaskHandel;
    static void Button_Task(void *p);
  public:
    Button(void){
      bt_key = 0;
      clicked_state = false;
      clicked_cb = nullptr;
      longpressed_cb = nullptr;
      Button_TaskHandel = NULL;
    };
    int GetButtonResult(void);
    void Button_init(uint8_t num = 1);
    void Clicked(CallbackFunc ncb);
    void Longpressed(CallbackFunc ncb);
};

class LED{
  public:
    void LED_init(void);
    void on(void);
    void off(void);
};

class LightSensor{
  public:
    int read(void);
};

class UltrasoundSonar{
  public:
    void Ultrasound_init(void);
    void setRGB(uint8_t index, uint8_t r, uint8_t g, uint8_t b);
    void setBreathing(uint8_t index, uint8_t rgb, uint8_t cycle);
    uint16_t getDistance(void);
};

class ASRSensor{
  public:
    void ASR_init(void);
    void setMode(uint8_t mode);
    void addWord(uint8_t idNum, const char *words);
    void erase(void);
    uint8_t getResult(void);
};

class MP3Sensor{
  public:
    void MP3_init(void);
    void play(uint16_t num = MP3_MAXCOUNT);
    void pause(void);
    void prev(void);
    void next(void);
    void loop_on(void);
    void loop_off(void);
    void volume(uint8_t value);
};

class ESP32S3Cam{
  public:
    void ESP32S3_init();
    bool face_recognition();
    void color_recognition(uint8_t *color_data);
    void color_follow(uint8_t color_label, uint8_t *color);
    void line_follow(uint8_t line_num, uint8_t *line);
};

#endif  //HIWONDER_H
