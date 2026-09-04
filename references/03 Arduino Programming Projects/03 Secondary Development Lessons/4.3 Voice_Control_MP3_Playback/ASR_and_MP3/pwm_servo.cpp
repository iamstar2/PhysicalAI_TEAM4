#include "HardwareSerial.h"
#include "Servo.h"
#include "pwm_servo.h"
#include <Preferences.h>
#include <esp_timer.h>

#define SERVO_OFFSET_NVS_NAMESPACE "mechdog"
#define SERVO_OFFSET_KEY_PREFIX "offset_s"

typedef struct {
  uint8_t pin_id;          /**< ESP32 GPIO pin ID for the servo. ->서보모터 핀 번호*/
  int current_pulsewidth;  /**< Current pulse width of the servo. ->현재 펄스 폭*/
  int actual_pulsewidth;   /**< Actual pulse width of the servo. --실제 동작 펄스 폭*/
  bool pulsewidth_changed; /**< Flag indicating whether the pulse width has changed. ->펄스 폭 변경 플래그*/
  bool is_running;         /**< Flag indicating whether the servo is running. ->서보모터 동작 중 여부 플래그*/
  int target_pulsewidth;   /**< Target pulse width of the servo. ->목표 펄스 폭*/
  int offset;              /**< Offset value for the servo. ->서보모터 오프셋*/
  float pulsewidth_inc;    /**< Increment of pulse width per cycle (20ms). ->매 주기의 펄스 폭 증가량*/
  uint32_t duration;       /**< Duration of the servo movement. Unit: ms ->서보모터 동작 시간*/
  int inc_num;             /**< Number of increments of pulse width. ->펄스 폭 증가 횟수*/

} pwm_servo_obj_t;

static void pwm_servo_pulsewidth_update(pwm_servo_obj_t *self, int8_t index);
static void timer_update_callback(void *argv);


DRAM_ATTR pwm_servo_obj_t pwm_servos[10] = {
    {.pin_id = 25, .current_pulsewidth = 2000, .actual_pulsewidth = 2000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 26, .current_pulsewidth = 2000, .actual_pulsewidth = 2000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 27, .current_pulsewidth = 2000, .actual_pulsewidth = 2000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 14, .current_pulsewidth = 2000, .actual_pulsewidth = 2000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 16, .current_pulsewidth = 1000, .actual_pulsewidth = 1000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 17, .current_pulsewidth = 1000, .actual_pulsewidth = 1000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 15, .current_pulsewidth = 1000, .actual_pulsewidth = 1000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 2, .current_pulsewidth = 1000, .actual_pulsewidth = 1000, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 0, .current_pulsewidth = 1500, .actual_pulsewidth = 1500, .pulsewidth_changed = false, .is_running = false},
    {.pin_id = 4, .current_pulsewidth = 1500, .actual_pulsewidth = 1500, .pulsewidth_changed = false, .is_running = false},
};

Servo servos[10];
esp_timer_handle_t timer_handle;
Preferences nvs;

void pwm_servo_init(void) {
  char nvs_key[16];
  
  nvs.begin(SERVO_OFFSET_NVS_NAMESPACE, false);

  for (int i = 0; i < 10; ++i) {
    sprintf(nvs_key, SERVO_OFFSET_KEY_PREFIX "%d", i + 1);
    pwm_servos[i].offset = nvs.getInt(nvs_key, 0);  //오프셋 읽기
  }
  nvs.end();

  for (int i = 0; i < 10; ++i) { 
    servos[i].attach(pwm_servos[i].pin_id);
  }

  // Set up timer to update pulsewidth
  const esp_timer_create_args_t timer_args = {
    .callback = &timer_update_callback,  // timer callback function
    .name = "pwm_servo_update_timer",
  };

  esp_timer_create(&timer_args, &timer_handle);
  esp_timer_start_periodic(timer_handle, 5000);
}

static uint8_t servo_deinit_flag = 0;
void pwm_servo_deinit(void) {
  esp_timer_stop(timer_handle);
  servo_deinit_flag = 1;
  for (int i = 0; i < 10; ++i) {
    servos[i].detach();
  }
}


static void IRAM_ATTR timer_update_callback(void *argv) {
  if (servo_deinit_flag == 0) {
    static int servo_index = 0;
    for (int i = 0; i < 5; ++i) {
      pwm_servo_pulsewidth_update(&pwm_servos[servo_index + i], servo_index + i);
    }
    servo_index = servo_index == 0 ? 5 : 0;
  }
}


/**
  * @brief Update the pulsewidth of the PWM servo.
  *
  * This function is used to update the pulsewidth of the PWM servo.
  * The pulsewidth is updated gradually until it reaches the target pulsewidth.
  *
  * @param self The PWM servo object.
  *
  * @return None.
*/
static void IRAM_ATTR pwm_servo_pulsewidth_update(pwm_servo_obj_t *self, int8_t index) {
  // Check if pulsewidth has changed
  if (self->pulsewidth_changed) {
    self->pulsewidth_changed = false;

    // Calculate pulsewidth increment based on target and current pulsewidth
    if (self->current_pulsewidth == 0) {  // If current pulsewidth is 0, set increment to target pulsewidth
      self->pulsewidth_inc = (float)self->target_pulsewidth;
      self->inc_num = 1;
    } else {
      self->inc_num = self->duration / 10;  // 10ms per tick
      if (self->target_pulsewidth > self->current_pulsewidth) {
        self->pulsewidth_inc = (float)(-(self->target_pulsewidth - self->current_pulsewidth)) / (float)self->inc_num;
      } else {
        self->pulsewidth_inc = (float)(self->current_pulsewidth - self->target_pulsewidth) / (float)self->inc_num;
      }
    }
    self->is_running = true;
  }

  // Update pulsewidth gradually until it reaches the target pulsewidth
  if (self->is_running) {
    --self->inc_num;
    if (self->inc_num == 0) {
      self->current_pulsewidth = self->target_pulsewidth;  // Update current pulsewidth to target pulsewidth
      self->is_running = false;
    } else {
      self->current_pulsewidth = self->target_pulsewidth + (int)(self->pulsewidth_inc * self->inc_num);
    }
    // Calculate actual pulsewidth based on current pulsewidth and offset
    self->actual_pulsewidth = self->current_pulsewidth + self->offset;
    // Set the compare value of the hardware comparator
    servos[index].writeMicroseconds(self->actual_pulsewidth);
  }
}

#define L_MAX_0 2300
#define L_MIN_0 500
#define L_MAX_1 1900
#define L_MIN_1 900

#define R_MAX_0 2500
#define R_MIN_0 700
#define R_MAX_1 2100
#define R_MIN_1 1100
/**
  * @brief Set the position of the PWM servo.
  *
  * This function is used to set the position of the PWM servo.
  * The position is determined by the pulsewidth and duration.
  *
  * @param servo_index The servo index. Valid values are 0 to 9.
  * @param pulsewidth The pulsewidth in microseconds. Valid values are 500 to 2500.
  * @param duration The duration in milliseconds. Valid values are 20 to 30000. 
  *
  * @return 0 if successful, -1 if servo ID is invalid
*/
int pwm_servo_set_position(uint32_t servo_index, uint32_t pulsewidth, uint32_t duration) {
  // Check if servo ID is valid
  if (servo_index >= 10) {
    return -1;
  }
  duration = duration < 20 ? 20 : (duration > 30000 ? 30000 : duration);  // Limit duration to 20ms to 30s
  // pulsewidth = pulsewidth > 2500 ? 2500 : (pulsewidth < 500 ? 500 : pulsewidth); // Limit pulsewidth to 500us to 2500us
  switch (servo_index) {
    case 0:  //왼쪽 위쪽 다리
    case 2:
      pulsewidth = pulsewidth > L_MAX_0 ? L_MAX_0 : pulsewidth;
      pulsewidth = pulsewidth < L_MIN_0 ? L_MIN_0 : pulsewidth;
      break;
    case 1:  //왼쪽 아래쪽 다리
    case 3:
      pulsewidth = pulsewidth > L_MAX_1 ? L_MAX_1 : pulsewidth;
      pulsewidth = pulsewidth < L_MIN_1 ? L_MIN_1 : pulsewidth;
      break;

    case 4:  //오른쪽 위쪽 다리
    case 6:
      pulsewidth = pulsewidth > R_MAX_0 ? R_MAX_0 : pulsewidth;
      pulsewidth = pulsewidth < R_MIN_0 ? R_MIN_0 : pulsewidth;
      break;
    case 5:  //오른쪽 아래쪽 다리
    case 7:
      pulsewidth = pulsewidth > R_MAX_1 ? R_MAX_1 : pulsewidth;
      pulsewidth = pulsewidth < R_MIN_1 ? R_MIN_1 : pulsewidth;
      break;
  }
  pwm_servos[servo_index].target_pulsewidth = pulsewidth;  // Set target pulsewidth
  pwm_servos[servo_index].duration = duration;             // Set duration
  pwm_servos[servo_index].pulsewidth_changed = true;

  return 0;
}

/**
  * @brief Set the offset value for the PWM servo.
  *
  * This function is used to set the offset value for the PWM servo.
  * The offset value determines the position of the servo motor's neutral position.
  *
  * @param servo_index The servo index. Valid values are 0 to 9.
  * @param offset The offset value. Valid values are -125 to 125.
  *
  * @return 0 if successful, -1 if servo ID is invalid, -2 if offset is invalid
*/
int pwm_servo_set_offset(uint32_t servo_index, int offset) {
  // Check if servo ID is valid
  if (servo_index >= 10) {
    return -1;
  }
  // Check if offset is within the valid range of -125 to 125
  if (offset < -125 || offset > 125) {
    return -2;
  }
  pwm_servo_obj_t *self = &pwm_servos[servo_index];
  self->offset = offset;
  self->actual_pulsewidth = self->current_pulsewidth + self->offset;
  servos[servo_index].writeMicroseconds(self->actual_pulsewidth);
  return 0;
}

/**
  * @brief Get the current pulse width of the servo.
  *
  * This function is used to get the current pulse width of the servo.
  *
  * @param servo_id The servo ID. Valid values are 1 to 10.
  * @param position The current pulse width of the servo. Valid values are 500 to 2500.
  * @param duration_ms The duration in milliseconds. Valid values are 20 to 30000. 
  *
  * @return The current pulse width of the servo.
*/
int pwm_servo_position(int8_t servo_id,int position,int duration_ms) {
  if (servo_id < 1 || servo_id > 10){
    return -1;
  }
  if (position == 0 && duration_ms == 0){
    return pwm_servos[servo_id - 1].current_pulsewidth;//매개변수가 하나뿐이면 서보모터 펄스 폭을 반환함.
  }else{
    int duration = 0;
    if (duration_ms != 0){
      duration = duration_ms;
    }
    pwm_servo_set_position(servo_id - 1, position, duration);
  }
}


/**
  * @brief Set the offset value for the PWM servo.
  *
  * This function is used to set the offset value for the PWM servo.
  * The offset value determines the position of the servo motor's neutral position.
  *
  * @param servo_id The servo ID. Valid values are 1 to 10.
  * @param offset The offset value. Valid values are -125 to 125.
  *
  * @return offset value.
*/
int get_pwm_servo_offset(int8_t servo_id) {
  if (servo_id < 1 || servo_id > 10){
    return -1;
  }
  return pwm_servos[servo_id - 1].offset; //서보모터 오프셋 반환
}
int set_pwm_servo_offset(int8_t servo_id,int new_offset) {
  if (servo_id < 1 || servo_id > 10){
    return -1;
  }
  if(new_offset > 125 || new_offset < -125){
    return -1;
  }
  pwm_servo_set_offset(servo_id - 1, new_offset); //오프셋 설정
}

/** 
  * @brief Save the offset value to nvs flash for the PWM servo.
  *
  * This function is used to save the offset value to nvs flash for the PWM servo.
  * The offset value determines the position of the servo motor's neutral position.
  *
  * @param servo_id
  *
  * @return None.
*/
int pwm_servo_save_offset(int8_t servo_id) {
  if (servo_id < 1 || servo_id > 10){
    return -1;
  }
  int8_t offset;
  char nvs_key[15];
  offset = pwm_servos[servo_id - 1].offset;
  sprintf(nvs_key, SERVO_OFFSET_KEY_PREFIX"%d", servo_id); 
  nvs.begin(SERVO_OFFSET_NVS_NAMESPACE, false);
  nvs.putInt(nvs_key, offset);
  nvs.end();
}

/**
  * @brief Restore the offset value from nvs flash for the PWM servo.
  *
  * This function is used to restore the offset value frome nvs flash for the PWM servo.
  * The offset value determines the position of the servo motor's neutral position.
  *
  * @param servo_id
  *
  * @return None.
*/
static int pwm_servo_restore_offset(int8_t servo_id) {
  if (servo_id < 1 || servo_id > 10){
    return -1;
  }
  int8_t offset;
  char nvs_key[15];
  sprintf(nvs_key, SERVO_OFFSET_KEY_PREFIX"%d", servo_id); 
  nvs.begin(SERVO_OFFSET_NVS_NAMESPACE, false);
  nvs.getInt(nvs_key, offset);
  nvs.end();
  pwm_servo_set_offset(servo_id - 1, offset);
}
