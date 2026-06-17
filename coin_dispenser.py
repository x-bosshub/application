# -*- coding: utf-8 -*-
# coin_dispenser.py

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
from datetime import datetime
import pytz
import paho.mqtt.client as mqtt

# --- Global Configurations ---
APP_VERSION = "5.6.0" 
bangkok_tz = pytz.timezone('Asia/Bangkok')
APP_BASE_PATH = '/home/pi5/application'

# --- MQTT Configuration ---
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
# New MQTT Topics
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
        
        # --- File Paths ---
        self.CONFIG_SYSTEM_FILE = os.path.join(APP_BASE_PATH, 'config.json')
        self.COIN_CONFIG_FILE = os.path.join(APP_BASE_PATH, 'config_coin.json')
        self.TRANSACTION_LOG_FILE = os.path.join(APP_BASE_PATH, 'transactions.json')
        
        # --- โหลด System Config ก่อน เพื่อเตรียมค่า Pin และตัวแปรระบบ ---
        self.load_system_config()

        self.message = "พร้อมใช้งาน"
        # Global States
        self.coins_to_dispense_target = 0
        self.coins_dispensed_count = 0
        self.is_dispensing_active = False
        self.bill_pulse_count = 0
        self.last_bill_pulse_time = 0
        self.current_transaction_bill_value = 0
        self.relay_start_time = 0.0
        self.retry_attempt = 0 
        self.MAX_RETRY_ATTEMPTS = 1

        # Hardware Objects (ใช้ค่าที่โหลดมาจาก sys_config)
        self.relay = DigitalOutputDevice(self.GPIO_RELAY, active_high=True, initial_value=False)
        self.relay_reload = DigitalOutputDevice(self.GPIO_RELAY_REVERT, active_high=True, initial_value=False)
        self.biller_sensor = Button(self.BILER_SENSOR_PIN, pull_up=True, bounce_time=0.01)
        self.coin_sensor = Button(self.COIN_SENSOR_PIN, pull_up=True, bounce_time=0.005)
        
        # คุมไฟ Biller ผ่าน MOSFET (Active High)
        self.biller_power = DigitalOutputDevice(self.BILER_POWER_PIN, active_high=True, initial_value=False)
        
        self.display = self._setup_tm1637()
        self.TM = self.display is not None

        # Callbacks
        self.biller_sensor.when_pressed = self._biler_sensor_callback
        self.coin_sensor.when_pressed = self._coin_sensor_callback

        # Threads
        self.biller_process_thread = threading.Thread(target=self._process_biller_pulses, daemon=True)
        self.relay_monitor_thread = threading.Thread(target=self._monitor_relay_timeout, daemon=True)
        self.biller_process_thread.start()
        self.relay_monitor_thread.start()
        
        # MQTT Client
        self.mqtt_client = self._setup_mqtt()

        # Initial Setup (โหลดเฉพาะ State ของเหรียญ)
        self.load_coin_config()
        self.set_relay_state(False)
        self.show_number_on_display(0)
        
        # เปิดไฟเครื่องรับธนบัตรเมื่อพร้อมทำงาน
        self.biller_power.on()
        print("[Hardware] Biller Power (GPIO 13) is ON. System is Ready.")

    def load_system_config(self):
        """โหลดค่าคงที่ของระบบและฮาร์ดแวร์จาก config.json"""
        # ตั้งค่า Default กันเหนียว
        self.BILER_SENSOR_PIN = 25
        self.COIN_SENSOR_PIN = 12
        self.GPIO_RELAY = 26
        self.GPIO_RELAY_REVERT = 21
        self.BILER_POWER_PIN = 13 # พินใหม่สำหรับ MOSFET
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

                    # สำคัญ: แปลง Key ของ Mapping จาก JSON (String) กลับเป็น Integer เพื่อให้บิลเลอร์อ่านค่าได้ตรง
                    raw_mapping = sys_config.get('BILL_PULSE_MAPPING', self.BILL_PULSE_MAPPING)
                    self.BILL_PULSE_MAPPING = {int(k): int(v) for k, v in raw_mapping.items()}
                    
                    self.BILL_PULSE_TIMEOUT = sys_config.get('BILL_PULSE_TIMEOUT', self.BILL_PULSE_TIMEOUT)
                    self.RELAY_MAX_ACTIVE_TIME = sys_config.get('RELAY_MAX_ACTIVE_TIME', self.RELAY_MAX_ACTIVE_TIME)
                    self.COIN_PER_BAHT_RATIO = sys_config.get('coin_per_baht_ratio', self.COIN_PER_BAHT_RATIO)
                    
            except Exception as e:
                print(f"[Config] Error loading config.json: {e}")

    def load_coin_config(self):
        """โหลดสถานะของเหรียญจาก config_coin.json (อ่านและเขียนบ่อยมาก)"""
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
            except Exception as e:
                print(f"[Config] Error loading coin config: {e}. Using defaults.")
        else:
            self.save_coin_config()
            
        self.RUN_STATUS['coin_stock'] = self.COIN_CONFIG.get('coin_stock', 0)

    def save_coin_config(self):
        """บันทึกเฉพาะสถานะเหรียญและยอดสะสมลง config_coin.json"""
        try:
            self.COIN_CONFIG['datetime'] = str(datetime.now(bangkok_tz)).split('.')[0]
            self.COIN_CONFIG['coin_stock'] = int(self.COIN_CONFIG.get('coin_stock', 0))
            with open(self.COIN_CONFIG_FILE, 'w') as f:
                json.dump(self.COIN_CONFIG, f, indent=4)
        except Exception as e:
            print(f"[Config] An error occurred while saving config: {e}")

    def _setup_tm1637(self):
        try:
            display = TM1637(clk_pin=self.TM_CLK, dio_pin=self.TM_DIO, brightness=7)
            display.clear()
            print("TM1637 display initialized and cleared.")
            return display
        except Exception as e:
            print(f"Error initializing TM1637 display: {e}. TM1637 functionality will be disabled.")
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
            print("[CoinDispenser] [MQTT] Attempting to connect...")
            return client
        except Exception as e:
            print(f"[CoinDispenser] [MQTT] Error setting up client: {e}")
            return None

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(MQTT_TOPIC_COMMAND, qos=1)
            print(f"[CoinDispenser] [MQTT] Subscribed to {MQTT_TOPIC_COMMAND}")
            now_in_bangkok = datetime.now(bangkok_tz)
            payload = {"version": APP_VERSION, "status": "online", "datetime": str(now_in_bangkok).split('.')[0], "ip_address": get_ip(), "temp": get_temp(),"config":self.COIN_CONFIG}
            client.publish(f"coin_machine/{DEVICE_ID}/status", json.dumps(payload), qos=1, retain=True).wait_for_publish(timeout=2)
            print("[CoinDispenser] [MQTT] Connected to Broker successfully!")
        else:
            print(f"[CoinDispenser] [MQTT] Failed to connect, return code {rc}")
            
    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            print(f"[CoinDispenser] [MQTT] Received message on topic {topic}: {payload}")
            if topic == MQTT_TOPIC_COMMAND:
                self._handle_command(payload)
        except json.JSONDecodeError:
            print(f"[CoinDispenser] [MQTT] Received non-JSON message on topic {topic}: {msg.payload.decode('utf-8')}")
        except Exception as e:
            print(f"[CoinDispenser] [MQTT] Error processing message: {e}")

    def _publish_mqtt_message(self, topic, payload):
        if self.mqtt_client and self.mqtt_client.is_connected():
            try:
                self.mqtt_client.publish(topic, json.dumps(payload), qos=0).wait_for_publish(timeout=1)
                print(f"[CoinDispenser] [MQTT] Successfully sent message to topic '{topic}'")
            except Exception as e:
                print(f"[CoinDispenser] [MQTT] Error publishing message: {e}")
        else:
            print("[CoinDispenser] [MQTT] Client not connected. Cannot publish message. (Offline Mode)")

    # --- Save Transaction Log ---
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
            print(f"[Log] Transaction saved to {self.TRANSACTION_LOG_FILE}")
        except Exception as e:
            print(f"[Log] Error saving transaction: {e}")

    def save_run_status(self):
        try:
            with open(os.path.join(APP_BASE_PATH, 'run_status.json'), 'w') as f:
                json.dump(self.RUN_STATUS, f, indent=4)
        except Exception as e:
            print(f"Saving Error: {e}")

    def show_number_on_display(self, no):
        if self.TM:
            try:
                self.display.clear()
                self.display.show(str(no))
            except Exception as e:
                print(f"[TM1637] Error displaying number: {e}")

    def set_relay_state(self, state):
        # self.load_coin_config() ออก เพื่อไม่ให้ข้อมูลจากไฟล์มาทับค่าใน RAM ขณะกำลังนับเหรียญ
        if state:
            if not self.relay.is_active:
                self.relay.on()
                self.relay_reload.off()
                self.relay_start_time = time.time()
                self.is_dispensing_active = True
                print(f"[Relay] State set to ON. Started at {self.relay_start_time:.2f}s")
            else:
                print("[Relay] Relay is already ON.")
        else:
            self.is_dispensing_active = False
            if self.relay.is_active:
                print("[Relay] State set to OFF (Applying Hard Brake for DRV8871).")
                
                # --- ลอจิก Hard Brake สำหรับไอซี DRV8871 ---
                # สั่งจ่ายไฟเข้าทั้ง IN1 และ IN2 ชั่วขณะเพื่อเบรกหัวทิ่ม (ชอร์ตลัดวงจรมอเตอร์)
                self.relay.on()
                self.relay_reload.on()
                time.sleep(0.05) # เวลาเบรก 50 ms (เพียงพอต่อการหยุดแรงเฉื่อยทันที)
                
                # จากนั้นก็ปล่อยไฟทั้ง 2 ขา เข้าสู่โหมด Coast (สแตนบายปกติ)
                self.relay.off()
                self.relay_reload.off()
                # ------------------------------------------
                
                self.relay_start_time = 0.0
                self.show_number_on_display(0)
            else:
                print("[Relay] Relay is already OFF.")
                self.show_number_on_display(0)
            
    def _coin_sensor_callback(self):
        if self.is_dispensing_active:
            self.coins_dispensed_count += 1
            
            # 1. เช็คเป้าหมายและ "ตัดไฟ Relay ทันที" เพื่อหยุดมอเตอร์
            if self.coins_dispensed_count >= self.coins_to_dispense_target:
                self.set_relay_state(False)
                print("[Coin] Target reached. Relay stopped instantly.")
            
            # 2. จัดการลด Stock ใน RAM ทันที (ยังไม่เซฟลงไฟล์เพื่อลดอาการกระตุก)
            current_stock = self.COIN_CONFIG.get('coin_stock', 0)
            self.COIN_CONFIG['coin_stock'] = max(0, current_stock - 1)
            self.COIN_CONFIG['coins_dispensed_count'] = self.coins_dispensed_count
            self.COIN_CONFIG['current_credit'] += 1 

            print(f"[Coin] Detected: {self.coins_dispensed_count} / {self.coins_to_dispense_target}. Stock left: {self.COIN_CONFIG['coin_stock']}")

            self.RUN_STATUS['status'] = 'dispensed'
            self.RUN_STATUS['coins_dispensed_count'] = self.coins_dispensed_count
            self.RUN_STATUS['coins_to_dispense_target'] = self.coins_to_dispense_target
            self.RUN_STATUS['coin_stock'] = self.COIN_CONFIG['coin_stock']
            self.RUN_STATUS['message'] = self.message

            # 3. แจ้งเตือนและบันทึกข้อมูลแบบเต็มๆ เมื่อจ่ายครบจำนวน
            if self.coins_dispensed_count >= self.coins_to_dispense_target:
                self.save_coin_config() # เซฟลงไฟล์แค่รอบเดียวเมื่อจ่ายเสร็จ
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
                
                # Reset สถานะเตรียมรับรอบถัดไป
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
            # 4. กรณีเหรียญตกเกิน (Over-dispense) หรือมอเตอร์เบรกไม่ทัน
            print("[Coin] Warning: Extra coin detected (Over-dispense)!")
            
            # หักสต็อกเหรียญให้ตรงความจริง
            current_stock = self.COIN_CONFIG.get('coin_stock', 0)
            self.COIN_CONFIG['coin_stock'] = max(0, current_stock - 1)
            self.save_coin_config()
            
            # บันทึกลงประวัติว่าจ่ายเกิน
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

            # ยิง MQTT แจ้งเตือน Error
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

    # Callback
    def _biler_sensor_callback(self):
        self.bill_pulse_count += 1
        self.last_bill_pulse_time = time.time()
        
        # ทดเลขใน RAM อย่างเดียว ไม่อ่าน/เขียนไฟล์ตรงนี้เพื่อลด I/O Block
        self.COIN_CONFIG['bill_pulse_count'] = self.bill_pulse_count
        self.show_number_on_display(self.bill_pulse_count)
        self.RUN_STATUS['bill_pulse_count'] = self.bill_pulse_count
        print(f"[Biller] Pulse Detected! Current count: {self.bill_pulse_count}")

    def _process_biller_pulses(self):
        self.load_coin_config()
        while True:
            if self.bill_pulse_count > 0 and (time.time() - self.last_bill_pulse_time) > self.BILL_PULSE_TIMEOUT:
                print(f"[Biller Processor] Pulse counting finished. Total pulses: {self.bill_pulse_count}")
                
                # เขียนลงไฟล์แค่ตอนรับแบงก์จบเรียบร้อยแล้ว
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
                             print(f"[Biller Processor] Not enough stock! Needed {num_coins_to_dispense}, Have {current_stock}")
                             self.start_dispensing(num_coins_to_dispense, "Biller")
                    else:
                        print(f"[Biller Processor] Received {detected_bill_value} Baht but dispensing is active. Ignoring.")
                else:
                    print(f"[Biller Processor] Unknown/Glitch pulse count: {self.bill_pulse_count}. Ignoring to prevent money loss.")

                self.bill_pulse_count = 0
                self.last_bill_pulse_time = 0
            time.sleep(0.01)

    def dispense_coins_mqtt(self, value, transaction_id):
        if transaction_id: 
            self.message = transaction_id
            
        if self.is_dispensing_active:
            message = "ไม่สามารถทำรายการได้: เครื่องกำลังจ่ายเหรียญอยู่"
            print(f"[MQTT Dispense] {message}")
            self._publish_mqtt_message(
                MQTT_TOPIC_RESPONSE,
                {"status": "error", "command": "dispense", "message": message, "transaction_id": transaction_id}
            )
            return
            
        # รีโหลดไฟล์คอนฟิกเพื่อดึงสต็อกล่าสุดก่อนเริ่มจ่าย
        self.load_coin_config()

        num_coins_to_dispense = value // self.COIN_PER_BAHT_RATIO
        self.current_transaction_bill_value = value
        
        current_stock = self.COIN_CONFIG.get('coin_stock', 0)
        if current_stock < num_coins_to_dispense:
            print(f"[MQTT Dispense] Stock might be low. {current_stock} < {num_coins_to_dispense}")
        
        if self.start_dispensing(num_coins_to_dispense, "Admin"):
            message = f"เริ่มจ่ายเหรียญจำนวน {num_coins_to_dispense} เหรียญ"
            status = "success"
            print(f"[MQTT Dispense] {message}")
            # เอาการส่ง MQTT จังหวะยืนยันการรับคำสั่ง (ACK) ออก 
            # เพื่อให้เหลือส่งแค่ตอนจบการจ่ายเหรียญรอบเดียวใน _coin_sensor_callback
        else:
            message = "ไม่สามารถเริ่มการจ่ายเหรียญได้"
            status = "error"
            print(f"[MQTT Dispense] {message}")
            self._publish_mqtt_message(
                MQTT_TOPIC_RESPONSE,
                {"status": "error", "command": "dispense", "message": message, "transaction_id": transaction_id,"coin_stock": self.COIN_CONFIG.get('coin_stock', 0)}
            )
            # --- Log Transaction (Error) ---
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
        print(self.RUN_STATUS)
        self.save_run_status()
        return self.RUN_STATUS

    def _monitor_relay_timeout(self):
        print("[Relay Timeout Monitor] Thread started.")
        while True:
            if self.is_dispensing_active and self.relay_start_time > 0:
                elapsed_time = time.time() - self.relay_start_time
                if elapsed_time > self.RELAY_MAX_ACTIVE_TIME:
                    print(f"[Relay Timeout Monitor] Relay active for {elapsed_time:.2f}s, exceeding max {self.RELAY_MAX_ACTIVE_TIME}s.")
                    self.set_relay_state(False)
                    # Check if the number of coins dispensed is less than the target
                    if self.coins_dispensed_count < self.coins_to_dispense_target:
                        print(f"[Relay Timeout Monitor] Dispensed {self.coins_dispensed_count} coins, but target was {self.coins_to_dispense_target}.")
                        # Retry logic
                        if self.retry_attempt < self.MAX_RETRY_ATTEMPTS:
                            self.retry_attempt += 1
                            print(f"[Relay Timeout Monitor] Retrying dispensing... Attempt {self.retry_attempt}/{self.MAX_RETRY_ATTEMPTS}")
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
                            print(f"[Relay Timeout Monitor] Max retry attempts ({self.MAX_RETRY_ATTEMPTS}) reached. Aborting.")
                            
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
            print("[Dispenser] Already dispensing. Please wait.")
            return False

        if num_coins <= 0:
            print("[Dispenser] Number of coins to dispense must be greater than 0.")
            if self.coins_to_dispense_target > 0 and self.coins_dispensed_count >= self.coins_to_dispense_target:
                self.set_relay_state(False)
                self.current_transaction_bill_value = 0
                self.coins_dispensed_count = 0
                self.coins_to_dispense_target = 0
                self.retry_attempt = 0
            return False
            
        if self.coins_dispensed_count == 0:
            self.coins_to_dispense_target = num_coins
        self.show_number_on_display(self.coins_to_dispense_target)
        time.sleep(1)
        self.RUN_STATUS['comment'] = "start_dispensing"
        self.RUN_STATUS['message'] = message
        self.RUN_STATUS['status'] = 'start'
        self.RUN_STATUS['bill_pulse_count'] = self.bill_pulse_count
        self.RUN_STATUS['coins_dispensed_count'] = self.coins_dispensed_count
        self.RUN_STATUS['coins_to_dispense_target'] = self.coins_to_dispense_target
        self.save_run_status()
        print(f"[Dispenser] Starting to dispense {num_coins} coins...")
        self.is_dispensing_active = True
        self.set_relay_state(True)
        return True

    def run(self):
        try:
            from signal import pause
            print("Running coin_dispenser_gpio.py directly for testing...")
            print("Press Ctrl+C to exit.")
            pause()
        except KeyboardInterrupt:
            print("\nExiting program.")
        except Exception as e:
            print(f'A critical error occurred: {e}')
            self.set_relay_state(False)
            if hasattr(self, 'biller_power'):
                self.biller_power.off()
                print("[Hardware] Biller Power (GPIO 13) is OFF due to exception.")
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
                print("[CoinDispenser] [MQTT] Disconnected.")
            if self.display:
                self.display.clear()
            import os
            time.sleep(3)
            os.system("sudo reboot")
        finally:
            self.set_relay_state(False)
            # ตัดไฟบิลเลอร์ทุกครั้งที่ปิดโปรแกรม หรือโปรแกรมแครช
            if hasattr(self, 'biller_power'):
                self.biller_power.off()
                print("[Hardware] Biller Power (GPIO 13) is OFF.")
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
                print("[CoinDispenser] [MQTT] Disconnected.")
            if self.display:
                self.display.clear()
            print("Program terminated.")

if __name__ == '__main__':
    manager = CoinDispenserManager()
    manager.run()
