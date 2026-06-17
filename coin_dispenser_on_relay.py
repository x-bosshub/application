import os
import json
import time
import threading
import queue
import socket
from datetime import datetime
from gpiozero import DigitalInputDevice, DigitalOutputDevice, Button
from tm1637_display import TM1637
import sys
import pytz
import paho.mqtt.client as mqtt

APP_VERSION = "5.6.0" 
bangkok_tz = pytz.timezone('Asia/Bangkok')
APP_BASE_PATH = '/home/pi5/application'

def get_raspberry_serial_number():
    try:
        with open('/sys/firmware/devicetree/base/serial-number', 'r') as f:
            serial_number = f.read().strip().replace('\u0000','')
            return serial_number
    except Exception:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        return line.split(':')[1].strip()
        except Exception:
            return "unknown_pi"

DEVICE_ID = get_raspberry_serial_number()
MQTT_BROKER = '141.98.19.212'
MQTT_PORT = 1883
MQTT_CLIENT_ID = f"coin_dispenser_hw_{DEVICE_ID}"
MQTT_TOPIC_EXCHANGE_SUCCESS = f"coin_machine/{DEVICE_ID}/exchange/success"
MQTT_TOPIC_EXCHANGE_ERROR = f"coin_machine/{DEVICE_ID}/exchange/error"
MQTT_TOPIC_COMMAND = f"coin_machine/{DEVICE_ID}/command"
MQTT_TOPIC_RESPONSE = f"coin_machine/{DEVICE_ID}/response"

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = "N/A"
    finally:
        s.close()
    return ip_address

def get_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read()) / 1000.0
    except FileNotFoundError:
        temp = "N/A"
    return temp

sending_status = {"coin_stock":0,"status":"ready","coins_to_dispense_target":0,"coins_dispensed_count":0,"bill_pulse_count":0,"comment":"พร้อมใช้งาน","message":None}

class CoinDispenserManager:
    def __init__(self):
        self.RUN_STATUS = sending_status
        
        self.CONFIG_SYSTEM_FILE = os.path.join(APP_BASE_PATH, 'config.json')
        self.COIN_CONFIG_FILE = os.path.join(APP_BASE_PATH, 'config_coin.json')
        self.TRANSACTION_LOG_FILE = os.path.join(APP_BASE_PATH, 'transactions.json')
        
        self.load_system_config()

        self.message = "พร้อมใช้งาน"
        self.coins_to_dispense_target = 0
        self.coins_dispensed_count = 0
        self.is_dispensing_active = False
        self.bill_pulse_count = 0
        self.last_bill_pulse_time = 0
        self.current_transaction_bill_value = 0
        self.relay_start_time = 0.0
        self.retry_attempt = 0 
        self.MAX_RETRY_ATTEMPTS = 1

        self.RELAY_ACTIVE = False

        self.relay = DigitalOutputDevice(self.GPIO_RELAY, active_high=self.RELAY_ACTIVE, initial_value=False)
        self.relay_reload = DigitalOutputDevice(self.GPIO_RELAY_REVERT, active_high=self.RELAY_ACTIVE, initial_value=False)
        self.biller_sensor = Button(self.BILER_SENSOR_PIN, pull_up=True, bounce_time=0.01)
        self.coin_sensor = Button(self.COIN_SENSOR_PIN, pull_up=True, bounce_time=0.005)
        
        self.biller_power = DigitalOutputDevice(self.BILER_POWER_PIN, active_high=False, initial_value=False)
        
        self.display = self._setup_tm1637()
        self.TM = self.display is not None

        self.biller_sensor.when_pressed = self._biler_sensor_callback
        self.coin_sensor.when_pressed = self._coin_sensor_callback

        self.biller_process_thread = threading.Thread(target=self._process_biller_pulses, daemon=True)
        self.relay_monitor_thread = threading.Thread(target=self._monitor_relay_timeout, daemon=True)
        self.biller_process_thread.start()
        self.relay_monitor_thread.start()
        
        self.mqtt_client = self._setup_mqtt()

        self.load_coin_config()
        self.set_relay_state(False)
        self.show_number_on_display(0)
        
        self.biller_power.on()

    def load_system_config(self):
        self.BILER_SENSOR_PIN = 25
        self.COIN_SENSOR_PIN = 12
        self.GPIO_RELAY = 20
        self.GPIO_RELAY_REVERT = 21
        self.BILER_POWER_PIN = 26
        self.TM_CLK = 2
        self.TM_DIO = 3
        self.BILL_PULSE_MAPPING = {2: 20, 5: 50, 10: 100, 50: 500, 100: 1000}
        self.BILL_PULSE_TIMEOUT = 0.5
        self.RELAY_MAX_ACTIVE_TIME = 5
        self.COIN_PER_BAHT_RATIO = 10

        if os.path.exists(self.CONFIG_SYSTEM_FILE):
            try:
                with open(self.CONFIG_SYSTEM_FILE, 'r') as f:
                    sys_config = json.load(f)
                    
                    hw = sys_config.get('hardware', {})
                    self.BILER_SENSOR_PIN = hw.get('biller_sensor_pin', self.BILER_SENSOR_PIN)
                    self.COIN_SENSOR_PIN = hw.get('coin_sensor_pin', self.COIN_SENSOR_PIN)
                    self.GPIO_RELAY = hw.get('gpio_relay', self.GPIO_RELAY)
                    self.GPIO_RELAY_REVERT = hw.get('gpio_relay_revert', self.GPIO_RELAY_REVERT)
                    self.BILER_POWER_PIN = hw.get('biller_power_pin', self.BILER_POWER_PIN)
                    self.TM_CLK = hw.get('tm_clk', self.TM_CLK)
                    self.TM_DIO = hw.get('tm_dio', self.TM_DIO)

                    raw_mapping = sys_config.get('BILL_PULSE_MAPPING', self.BILL_PULSE_MAPPING)
                    self.BILL_PULSE_MAPPING = {int(k): int(v) for k, v in raw_mapping.items()}
                    
                    self.BILL_PULSE_TIMEOUT = sys_config.get('BILL_PULSE_TIMEOUT', self.BILL_PULSE_TIMEOUT)
                    self.RELAY_MAX_ACTIVE_TIME = sys_config.get('RELAY_MAX_ACTIVE_TIME', self.RELAY_MAX_ACTIVE_TIME)
                    self.COIN_PER_BAHT_RATIO = sys_config.get('coin_per_baht_ratio', self.COIN_PER_BAHT_RATIO)
                    
            except Exception:
                pass

    def load_coin_config(self):
        self.COIN_CONFIG = {
            "datetime": str(datetime.now(bangkok_tz)).split('.')[0],
            "status": True, "active": True, "error": 0,
            "coin_stock": 0, "current_credit": 0.0,
            "bill_pulse_count": 0, "coins_dispensed_count": 0
        }
        if os.path.exists(self.COIN_CONFIG_FILE):
            try:
                with open(self.COIN_CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    self.COIN_CONFIG.update(loaded_config)
            except Exception:
                pass
        else:
            self.save_coin_config()
            
        self.RUN_STATUS['coin_stock'] = self.COIN_CONFIG.get('coin_stock', 0)

    def save_coin_config(self):
        try:
            self.COIN_CONFIG['datetime'] = str(datetime.now(bangkok_tz)).split('.')[0]
            self.COIN_CONFIG['coin_stock'] = int(self.COIN_CONFIG.get('coin_stock', 0))
            with open(self.COIN_CONFIG_FILE, 'w') as f:
                json.dump(self.COIN_CONFIG, f, indent=4)
        except Exception:
            pass

    def _setup_tm1637(self):
        try:
            display = TM1637(clk_pin=self.TM_CLK, dio_pin=self.TM_DIO, brightness=7)
            display.clear()
            return display
        except Exception:
            return None

    def _handle_command(self, command_payload):
        command = command_payload.get("command")
        if command == "status":
            return self._send_status()
        elif command == "get_status":
            return self._send_status()
        elif command == "display":
            return self.show_number_on_display(command_payload.get("value"))
        elif command == "coin_stock":
            self.RUN_STATUS['coin_stock'] = int(command_payload.get("value"))
            self.COIN_CONFIG['coin_stock'] = int(command_payload.get("value"))
            poweredby = command_payload.get("by")
            self.save_coin_config()
            return self._publish_mqtt_message(MQTT_TOPIC_RESPONSE,{"status": "success", "data":self.COIN_CONFIG,"message": "อัพเดทเหรียญ"})
        elif command == "reset":
            self.COIN_CONFIG['error'] = 0
            self.COIN_CONFIG['current_credit'] = 0
            self.COIN_CONFIG['bill_pulse_count'] = 0
            self.save_coin_config()
            self._publish_mqtt_message(MQTT_TOPIC_RESPONSE,{"status": "success", "message": "รีเซ็ตข้อมูล"})

        elif command == "reboot":
            self._publish_mqtt_message(
                MQTT_TOPIC_RESPONSE,
                {"status": "success", "message": "รีสตาร์ทเครื่อง"}
            )
            import os
            time.sleep(1)
            os.system('sudo reboot')
        elif command == "dispense":
            value = command_payload.get("value")
            transaction_id = command_payload.get("by")
            if isinstance(value, int) and value > 0:
                self.dispense_coins_mqtt(value, transaction_id)
            else:
                self._publish_mqtt_message(MQTT_TOPIC_RESPONSE,{"status": "error", "message": "ค่า value ไม่ถูกต้อง"})
        else:
            self._publish_mqtt_message(MQTT_TOPIC_RESPONSE,{"status": "error", "command": command, "message": "คำสั่งไม่ถูกต้อง"})
            
    def _send_status(self):
        self.load_coin_config()
        payload = {
            "status": "online",
            "device_id": DEVICE_ID,
            "ip_address": get_ip(),
            "message":"เรียกดูสถานะ",
            "temp": get_temp(),
            "is_dispensing_active": self.is_dispensing_active,
            "coins_dispensed_count": self.coins_dispensed_count,
            "coins_to_dispense_target": self.coins_to_dispense_target,
            "current_credit": self.COIN_CONFIG.get('current_credit', 0),
            "coin_stock": self.COIN_CONFIG.get('coin_stock', 0),
            "timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
        }
        self._publish_mqtt_message(MQTT_TOPIC_RESPONSE, payload)
        return payload

    def _setup_mqtt(self):
        try:
            client = mqtt.Client(client_id=MQTT_CLIENT_ID)
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            will_payload = {"version": APP_VERSION, "status": "offline", "datetime": str(datetime.now(bangkok_tz)).split('.')[0], "ip_address": get_ip(), "temp": get_temp()}
            client.will_set(f"coin_machine/{DEVICE_ID}/status", payload=json.dumps(will_payload), qos=1, retain=True)
            client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_start()
            return client
        except Exception:
            return None

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(MQTT_TOPIC_COMMAND, qos=1)
            now_in_bangkok = datetime.now(bangkok_tz)
            payload = {"version": APP_VERSION, "status": "online", "datetime": str(now_in_bangkok).split('.')[0], "ip_address": get_ip(), "temp": get_temp(),"config":self.COIN_CONFIG}
            client.publish(f"coin_machine/{DEVICE_ID}/status", json.dumps(payload), qos=1, retain=True).wait_for_publish(timeout=2)
            
    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            if topic == MQTT_TOPIC_COMMAND:
                self._handle_command(payload)
        except Exception:
            pass

    def _publish_mqtt_message(self, topic, payload):
        if self.mqtt_client and self.mqtt_client.is_connected():
            try:
                self.mqtt_client.publish(topic, json.dumps(payload), qos=0).wait_for_publish(timeout=1)
                time.sleep(1)
                self.display.show(0)
            except Exception:
                self.display.show(0)
        else:
            self.display.show(0)

    def save_transaction_log(self, data):
        logs = []
        if os.path.exists(self.TRANSACTION_LOG_FILE):
            try:
                with open(self.TRANSACTION_LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                if not isinstance(logs, list): logs = []
            except: logs = []

        if 'timestamp' not in data:
            data['timestamp'] = str(datetime.now(bangkok_tz)).split('.')[0]
            
        logs.append(data)
        
        if len(logs) > 500:
            logs = logs[-500:]

        try:
            with open(self.TRANSACTION_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def save_run_status(self):
        try:
            with open(os.path.join(APP_BASE_PATH, 'run_status.json'), 'w') as f:
                json.dump(self.RUN_STATUS, f, indent=4)
        except Exception:
            pass

    def show_number_on_display(self, no):
        if self.TM:
            try:
                self.display.clear()
                self.display.show(str(no))
            except Exception:
                pass

    def set_relay_state(self, state):
        self.load_coin_config()
        if state:
            if not self.relay.is_active:
                self.relay.on()
                self.relay_reload.off()
                self.relay_start_time = time.time()
                self.is_dispensing_active = True
        else:
            self.is_dispensing_active = False
            if self.relay.is_active:
                self.relay.on()
                self.relay_reload.on()
                time.sleep(0.05) 
                
                self.relay.off()
                self.relay_reload.off()
                
                self.relay_start_time = 0.0
                self.show_number_on_display(0)
            else:
                self.show_number_on_display(0)
            
    def _coin_sensor_callback(self):
        if self.is_dispensing_active:
            self.coins_dispensed_count += 1
            
            if self.coins_dispensed_count >= self.coins_to_dispense_target:
                self.set_relay_state(False)
            
            current_stock = self.COIN_CONFIG.get('coin_stock', 0)
            self.COIN_CONFIG['coin_stock'] = max(0, current_stock - 1)
            self.COIN_CONFIG['coins_dispensed_count'] = self.coins_dispensed_count
            self.COIN_CONFIG['current_credit'] += 1 
            self.display.show(str(self.coins_dispensed_count))
            
            self.RUN_STATUS['status'] = 'dispensed'
            self.RUN_STATUS['coins_dispensed_count'] = self.coins_dispensed_count
            self.RUN_STATUS['coins_to_dispense_target'] = self.coins_to_dispense_target
            self.RUN_STATUS['coin_stock'] = self.COIN_CONFIG['coin_stock']
            self.RUN_STATUS['message'] = self.message

            if self.coins_dispensed_count >= self.coins_to_dispense_target:
                self.save_coin_config()
                self.save_run_status()
                
                log_data = {
                    "type": "dispense",
                    "status": "success",
                    "message": "การจ่ายเหรียญ สำเร็จ",
                    "comment": self.message,
                    "coin_stock": self.COIN_CONFIG.get('coin_stock', 0),
                    "amount": self.current_transaction_bill_value,
                    "coins_target": self.coins_to_dispense_target,
                    "coins_dispensed": self.coins_dispensed_count,
                    "timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
                }
                self.save_transaction_log(log_data)
                self._publish_mqtt_message(
                    MQTT_TOPIC_EXCHANGE_SUCCESS,
                    {
                        "version": APP_VERSION, "device_id": DEVICE_ID, "action": "bill_exchange_success",
                        "comment": self.message,
                        "status": "success", 
                        "message": f"จ่ายเหรียญ จำนวน  {self.coins_to_dispense_target} สำเร็จ",
                        "type": "biller",
                        "temp": get_temp(), 
                        "ip_address": get_ip(),
                        "amount": self.current_transaction_bill_value,
                        "bill_value_received": self.current_transaction_bill_value,
                        "coins_dispensed_target": self.coins_to_dispense_target,
                        "coins_dispensed_actual": self.coins_dispensed_count,
                        "timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
                    }
                )
                
                self.current_transaction_bill_value = 0
                self.coins_dispensed_count = 0
                self.retry_attempt = 0
                self.coins_to_dispense_target = 0
                self.RUN_STATUS['status'] = 'success'
                self.RUN_STATUS['comment'] = "biller"
                self.RUN_STATUS['message'] = log_data['message']
                self.RUN_STATUS['bill_pulse_count'] = 0
                self.RUN_STATUS['coins_dispensed_count'] = self.coins_dispensed_count
                self.RUN_STATUS['coins_to_dispense_target'] = self.coins_to_dispense_target
                self.save_run_status()
        else:
            current_stock = self.COIN_CONFIG.get('coin_stock', 0)
            self.COIN_CONFIG['coin_stock'] = max(0, current_stock - 1)
            self.save_coin_config()
            
            log_data = {
                "type": "dispense",
                "status": "error",
                "error_msg": "over_dispense",
                "message": "เหรียญจ่ายเกิน (ไหลตกเอง/มอเตอร์เบรกไม่ทัน)",
                "coin_stock": self.COIN_CONFIG['coin_stock'],
                "timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
            }
            self.save_transaction_log(log_data)
            
            self.RUN_STATUS['comment'] = log_data['error_msg']
            self.RUN_STATUS['message'] = log_data['message']

            self._publish_mqtt_message(
                MQTT_TOPIC_EXCHANGE_ERROR,
                {
                    "version": APP_VERSION, 
                    "device_id": DEVICE_ID, 
                    "action": "over_dispense",
                    "status": "error", 
                    "coins_dispensed_count ":self.coins_dispensed_count,
                    "coins_to_dispense_target":self.coins_to_dispense_target,
                    "over_dispense": self.coins_dispensed_count - self.coins_to_dispense_target ,
                    "message": "ตรวจพบเหรียญจ่ายเกิน (มอเตอร์เบรกไม่ทัน หรือไหลตกลงมาเอง)",
                    "type": "coin_sensor_error",
                    "temp": get_temp(), 
                    "ip_address": get_ip(),
                    "timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
                }
            )

    def _biler_sensor_callback(self):
        self.bill_pulse_count += 1
        self.last_bill_pulse_time = time.time()
        
        self.COIN_CONFIG['bill_pulse_count'] = self.bill_pulse_count
        self.show_number_on_display(self.bill_pulse_count)
        self.RUN_STATUS['bill_pulse_count'] = self.bill_pulse_count

    def _process_biller_pulses(self):
        self.load_coin_config()
        while True:
            if self.bill_pulse_count > 0 and (time.time() - self.last_bill_pulse_time) > self.BILL_PULSE_TIMEOUT:
                self.save_coin_config()
                
                detected_bill_value = self.BILL_PULSE_MAPPING.get(self.bill_pulse_count)
                if detected_bill_value:
                    if not self.is_dispensing_active:
                        self.current_transaction_bill_value = detected_bill_value
                        
                        num_coins_to_dispense = detected_bill_value // self.COIN_PER_BAHT_RATIO
                        
                        current_stock = self.COIN_CONFIG.get('coin_stock', 0)
                        if current_stock >= num_coins_to_dispense:
                             self.start_dispensing(num_coins_to_dispense, "Biller")
                        else:
                             self.start_dispensing(num_coins_to_dispense, "Biller")
                else:
                    self.display.show('----')
                    time.sleep(0.5)
                    self.display.show(0)
                    
                self.bill_pulse_count = 0
                self.last_bill_pulse_time = 0
            time.sleep(0.01)

    def dispense_coins_mqtt(self, value, transaction_id):
        if transaction_id: 
            self.message = transaction_id
            
        if self.is_dispensing_active:
            message = "ไม่สามารถทำรายการได้: เครื่องกำลังจ่ายเหรียญอยู่"
            self._publish_mqtt_message(
                MQTT_TOPIC_RESPONSE,
                {"status": "error", "command": "dispense", "message": message, "transaction_id": transaction_id}
            )
            return
            
        self.load_coin_config()

        num_coins_to_dispense = value // self.COIN_PER_BAHT_RATIO
        self.current_transaction_bill_value = value
        
        current_stock = self.COIN_CONFIG.get('coin_stock', 0)
        
        if self.start_dispensing(num_coins_to_dispense, "Admin"):
            message = f"เริ่มจ่ายเหรียญจำนวน {num_coins_to_dispense} เหรียญ"
            status = "success"
            self._publish_mqtt_message(
                MQTT_TOPIC_RESPONSE,
                {"status": "success", "command": "dispense", "message": message, "transaction_id": transaction_id, "coins_target": num_coins_to_dispense, "type": "admin", "comment": self.message,"coin_stock": self.COIN_CONFIG.get('coin_stock', 0)}
            )
        else:
            message = "ไม่สามารถเริ่มการจ่ายเหรียญได้"
            status = "error"
            self._publish_mqtt_message(
                MQTT_TOPIC_RESPONSE,
                {"status": "error", "command": "dispense", "message": message, "transaction_id": transaction_id,"coin_stock": self.COIN_CONFIG.get('coin_stock', 0)}
            )
            log_data = {
                "type": "dispense_coins_mqtt",
                "status": status,
                "message": message,
                "coin_stock": self.COIN_CONFIG.get('coin_stock', 0),
                "amount": self.current_transaction_bill_value,
                "coins_target": self.coins_to_dispense_target,
                "coins_dispensed": self.coins_dispensed_count,
                "timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
            }
            self.save_transaction_log(log_data)

    def check_status(self):
        self.save_run_status()
        return self.RUN_STATUS

    def _monitor_relay_timeout(self):
        while True:
            if self.is_dispensing_active and self.relay_start_time > 0:
                elapsed_time = time.time() - self.relay_start_time
                if elapsed_time > self.RELAY_MAX_ACTIVE_TIME:
                    self.set_relay_state(False)
                    if self.coins_dispensed_count < self.coins_to_dispense_target:
                        if self.retry_attempt < self.MAX_RETRY_ATTEMPTS:
                            self.retry_attempt += 1
                            remaining_coins = self.coins_to_dispense_target - self.coins_dispensed_count
                            
                            log_data = {
                                "type": "dispense",
                                "status": "error",
                                "comment":self.message,
                                "message":"การจ่ายเหรียญ ครั้งที่ 1 ไม่สำเร็จ",
                                "error_msg": "timeout_incomplete_dispense","coin_stock": self.COIN_CONFIG.get('coin_stock', 0),
                                "amount": self.current_transaction_bill_value,
                                "coins_target": self.coins_to_dispense_target,
                                "coins_dispensed": self.coins_dispensed_count,"timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
                            }
                            self.save_transaction_log(log_data)
                            self.relay.off()
                            time.sleep(0.2)
                            self.relay_reload.on()
                            time.sleep(0.2)
                            self.relay_reload.off()
                            self.start_dispensing(remaining_coins,self.message)
                            continue 
                        else:
                            mynotcoin = self.coins_to_dispense_target - self.coins_dispensed_count
                            self.COIN_CONFIG['error'] = self.COIN_CONFIG['error'] + mynotcoin
                            self.save_coin_config()
                            
                            log_data = {
                                "type": "dispense",
                                "status": "error",
                                "message":"การจ่ายเหรียญ ครั้งที่ 2 ไม่สำเร็จ",
                                "comment":self.message,"coin_stock": self.COIN_CONFIG.get('coin_stock', 0),
                                "error_msg": "timeout_incomplete_dispense",
                                "amount": self.current_transaction_bill_value,
                                "coins_target": self.coins_to_dispense_target,
                                "coins_dispensed": self.coins_dispensed_count,"timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
                            }
                            self.save_transaction_log(log_data)

                            self._publish_mqtt_message(
                                MQTT_TOPIC_EXCHANGE_ERROR,
                                {
                                    "version": APP_VERSION, 
                                    "device_id": DEVICE_ID, 
                                    "action": "bill_exchange_error",
                                    "type":"dispense",
                                    "comment":self.message,"coin_stock": self.COIN_CONFIG.get('coin_stock', 0),
                                    "temp":get_temp(),"ip_address":get_ip(),
                                    "status": "error", "message": f"เกิดข้อผิดพลาด: จ่ายเหรียญไม่ครบ ({self.coins_dispensed_count}/{self.coins_to_dispense_target}) หลังจากการลองใหม่",
                                    "bill_value_received": self.current_transaction_bill_value,
                                    "coins_dispensed_target": self.coins_to_dispense_target,
                                    "coins_dispensed_actual": self.coins_dispensed_count,
                                    "timestamp": str(datetime.now(bangkok_tz)).split('.')[0]
                                }
                            )
                            self.RUN_STATUS['status'] = 'error'
                            self.RUN_STATUS['bill_pulse_count'] = self.bill_pulse_count
                            self.RUN_STATUS['coins_dispensed_count'] = self.coins_dispensed_count
                            self.RUN_STATUS['coins_to_dispense_target'] = self.coins_to_dispense_target
                            self.save_run_status()

                    self.current_transaction_bill_value = 0
                    self.coins_dispensed_count = 0
                    self.coins_to_dispense_target = 0
                    self.retry_attempt = 0

            time.sleep(0.1)
            
    def start_dispensing(self, num_coins,message):
        if message : self.message = message
        if self.is_dispensing_active:
            self.display.show('----')
            time.sleep(0.5)
            self.display.show(0)
            return False

        if num_coins <= 0:
            if self.coins_to_dispense_target > 0 and self.coins_dispensed_count >= self.coins_to_dispense_target:
                self.set_relay_state(False)
                self.current_transaction_bill_value = 0
                self.coins_dispensed_count = 0
                self.coins_to_dispense_target = 0
                self.retry_attempt = 0
            return False
            
        if self.coins_dispensed_count == 0:
            self.coins_to_dispense_target = num_coins
        self.display.show('----')
        time.sleep(0.5)
        self.RUN_STATUS['comment'] = "start_dispensing"
        self.RUN_STATUS['message'] = message
        self.RUN_STATUS['status'] = 'start'
        self.RUN_STATUS['bill_pulse_count'] = self.bill_pulse_count
        self.RUN_STATUS['coins_dispensed_count'] = self.coins_dispensed_count
        self.RUN_STATUS['coins_to_dispense_target'] = self.coins_to_dispense_target
        self.display.show(str(self.coins_dispensed_count))
        time.sleep(0.5)
        if(self.coins_dispensed_count <= 0) :
            self.display.show(0)
            time.sleep(0.5)

        self.save_run_status()
        self.is_dispensing_active = True
        self.set_relay_state(True)
        return True

    def run(self):
        try:
            from signal import pause
            pause()
        except KeyboardInterrupt:
            pass
        except Exception:
            self.set_relay_state(False)
            if hasattr(self, 'biller_power'):
                self.biller_power.off()
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            if self.display:
                self.display.clear()
            import os
            time.sleep(3)
            os.system("sudo reboot")
        finally:
            self.set_relay_state(False)
            if hasattr(self, 'biller_power'):
                self.biller_power.off()
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            if self.display:
                self.display.clear()

if __name__ == '__main__':
    manager = CoinDispenserManager()
    manager.run()
