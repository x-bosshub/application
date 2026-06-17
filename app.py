# -*- coding: utf-8 -*-
# app.py
# curl -o /home/pi5/application/app.py http://141.98.19.190:4000/static/coin_machine_hybrid/app.py
# 
APP_VERSION = "5.6.0"
import os
import sys
import platform
import subprocess
import socket
import json
import threading
import time
from datetime import datetime
import pytz
import requests
from kivy.config import Config

# Graphics Config
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '600') 
Config.set('graphics', 'fullscreen', 'auto') 
Config.set('graphics', 'show_cursor', '0')
Config.set('graphics', 'resizable', '1')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')
Config.write()
# Kivy Imports
os.environ['KIVY_NO_CONSOLELOG'] = '1'
import kivy
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, NoTransition
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.properties import StringProperty, NumericProperty, ObjectProperty, BooleanProperty, ListProperty
from kivy.core.text import LabelBase
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.metrics import dp
from kivy.graphics.transformation import Matrix
from kivy.graphics import Color, RoundedRectangle, Line, BoxShadow, Ellipse
from kivy.animation import Animation
from kivy.factory import Factory 
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView

# Hardware & Network Imports
from gpiozero.pins.lgpio import LGPIOFactory 
import paho.mqtt.client as mqtt

# =============================================================================
# 1. SYSTEM & CONFIGURATION
# =============================================================================

APP_BASE_PATH = '/home/pi5/application'
bangkok_tz = pytz.timezone('Asia/Bangkok')

if platform.system() == 'Linux':
    Window.fullscreen = 'auto'
    Window.show_cursor = False
else:
    Window.size = (1024, 600)

# Font Configuration
THAI_FONT_FILE = os.path.join(APP_BASE_PATH, 'fonts', 'Mali-Bold.ttf')
if os.path.exists(THAI_FONT_FILE):
    LabelBase.register(name='AppFont', fn_regular=THAI_FONT_FILE)
    APP_FONT = 'AppFont'
else:
    APP_FONT = 'Roboto'

def get_raspberry_serial_number():
    try:
        with open('/sys/firmware/devicetree/base/serial-number', 'r') as f:
            return f.read().strip().replace('\u0000', '')
    except Exception:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        return line.split(':')[1].strip()
        except:
            return "unknown_device"

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1' 
    finally:
        s.close()
    return IP

# --- Config Class ---
class Config:
    SYSTEM_CONFIG_FILE = os.path.join(APP_BASE_PATH, 'config.json')
    COIN_STATE_FILE = os.path.join(APP_BASE_PATH, 'config_coin.json')
    TRANSACTION_LOG_FILE = os.path.join(APP_BASE_PATH, 'transactions.json')
    SERAIL_ID = get_raspberry_serial_number() or "unknown_device"
    
    # Default values (จะถูกโหลดทับด้วย load_config ถอยหลังกลับไปหา JSON)
    PAYMENT_API_BASE = "http://141.98.19.212:5560/api-pay"
    API_KEY = "F8C04-06726831FD"
    USERNAME = SERAIL_ID
    PASSWORD = "242424"
    
    MQTT_BROKER = '141.98.19.212'
    MQTT_PORT = 1883
    MQTT_CLIENT_ID = f"coin_machine_client_{SERAIL_ID}"
    MQTT_TOPIC_PAYMENT_SUCCESS = f"coin_machine/{SERAIL_ID}/payment/success"
    MQTT_TOPIC_PAYMENT_ERROR = f"coin_machine/{SERAIL_ID}/payment/error"
    MQTT_TOPIC_LOGS = f"coin_machine/{SERAIL_ID}/logs"
    MQTT_TOPIC_RESPONSE = f"coin_machine/{SERAIL_ID}/response"
    MQTT_TOPIC_COMMAND = f"coin_machine/{SERAIL_ID}/command"
    
    SELECT_AMOUNT = [20,40,50,60,70,80,90,100,120,130,140,150]
    payment_timeout_seconds = 120

# Global Config Dictionary for UI binding
APP_CONFIG = {
    "api_key": Config.API_KEY,
    "username": Config.USERNAME,
    "admin_password": Config.PASSWORD,
    "coin_per_baht_ratio": 10,
    "payment_timeout_seconds": 120,
    "background_color": [1, 1, 1, 1],
    "show_setting_button": True,
    "auto_reboot": False,
    "contact_title": "ติดต่อเจ้าหน้าที่",
    "contact_text": "@ไลน์แอด",
    "SELECT_AMOUNT": Config.SELECT_AMOUNT,
    "BILL_PULSE_MAPPING": {"2": 20, "5": 50, "10": 100, "50": 500, "100": 1000},
    "BILL_PULSE_TIMEOUT": 0.5,
    "RELAY_MAX_ACTIVE_TIME": 5
}

# --- Utils ---
def check_internet_connection(host="8.8.8.8", port=53, timeout=1):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except (socket.error, OSError):
        return False

def _calculate_coins_from_amount(amount_string: str) -> int:
    try:
        main_amount = int(float(amount_string))
        return main_amount // APP_CONFIG["coin_per_baht_ratio"]
    except:
        return 0

def log_transaction(data):
    logs = []
    if os.path.exists(Config.TRANSACTION_LOG_FILE):
        try:
            with open(Config.TRANSACTION_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            if not isinstance(logs, list): logs = []
        except: logs = []
    
    log_entry = data.copy()
    log_entry['timestamp'] = datetime.now(bangkok_tz).isoformat().split('.')[0]
    log_entry['type'] = 'qr_payment'
    
    logs.append(log_entry)
    if len(logs) > 500: logs = logs[-500:]

    with open(Config.TRANSACTION_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)

def load_config():
    global APP_CONFIG
    
    if os.path.exists(Config.SYSTEM_CONFIG_FILE):
        try:
            with open(Config.SYSTEM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                sys_data = json.load(f)
                
                app_data = sys_data.get('app', {})
                Config.PASSWORD = app_data.get('admin_password', Config.PASSWORD)
                
                mqtt_data = sys_data.get('mqtt', {})
                Config.MQTT_BROKER = mqtt_data.get('broker', Config.MQTT_BROKER)
                Config.MQTT_PORT = mqtt_data.get('port', Config.MQTT_PORT)
                
                pay_data = sys_data.get('payment', {})
                Config.PAYMENT_API_BASE = pay_data.get('api_base', Config.PAYMENT_API_BASE)
                Config.API_KEY = pay_data.get('api_key', Config.API_KEY)
                Config.payment_timeout_seconds = pay_data.get('timeout_seconds', Config.payment_timeout_seconds)
                
                Config.SELECT_AMOUNT = sys_data.get('SELECT_AMOUNT', Config.SELECT_AMOUNT)
                
                ui_data = sys_data.get('ui', {})
                APP_CONFIG["background_color"] = ui_data.get('background_color', APP_CONFIG["background_color"])
                APP_CONFIG["show_setting_button"] = ui_data.get('show_setting_button', APP_CONFIG["show_setting_button"])
                APP_CONFIG["contact_title"] = ui_data.get('contact_title', APP_CONFIG["contact_title"])
                APP_CONFIG["contact_text"] = ui_data.get('contact_text', APP_CONFIG["contact_text"])
                
                APP_CONFIG["api_key"] = Config.API_KEY
                APP_CONFIG["admin_password"] = Config.PASSWORD
                APP_CONFIG["coin_per_baht_ratio"] = sys_data.get('coin_per_baht_ratio', APP_CONFIG["coin_per_baht_ratio"])
                APP_CONFIG["auto_reboot"] = app_data.get('auto_reboot', APP_CONFIG["auto_reboot"])
                APP_CONFIG["SELECT_AMOUNT"] = Config.SELECT_AMOUNT
                APP_CONFIG["BILL_PULSE_MAPPING"] = sys_data.get('BILL_PULSE_MAPPING', APP_CONFIG["BILL_PULSE_MAPPING"])
                APP_CONFIG["BILL_PULSE_TIMEOUT"] = sys_data.get('BILL_PULSE_TIMEOUT', APP_CONFIG["BILL_PULSE_TIMEOUT"])
                APP_CONFIG["RELAY_MAX_ACTIVE_TIME"] = sys_data.get('RELAY_MAX_ACTIVE_TIME', APP_CONFIG["RELAY_MAX_ACTIVE_TIME"])
                
        except Exception as e:
            print(f"[App] Error loading config.json: {e}")
    else:
        save_system_config()

    app = App.get_running_app()
    if os.path.exists(Config.COIN_STATE_FILE):
        try:
            with open(Config.COIN_STATE_FILE, 'r', encoding='utf-8') as f:
                coin_data = json.load(f)
                if app:
                    app.coin_stock = coin_data.get('coin_stock', 0)
        except Exception as e:
            print(f"[App] Error loading config_coin.json: {e}")
            if app: app.coin_stock = 0
    else:
        if app: app.coin_stock = 0
        save_coin_state()

def save_system_config():
    if not os.path.exists(Config.SYSTEM_CONFIG_FILE):
        sys_data = {
            "app": {"version": APP_VERSION, "base_path": APP_BASE_PATH, "admin_password": APP_CONFIG["admin_password"], "auto_reboot": APP_CONFIG["auto_reboot"]},
            "mqtt": {"broker": Config.MQTT_BROKER, "port": Config.MQTT_PORT},
            "hardware": {"biller_sensor_pin": 25, "coin_sensor_pin": 12, "gpio_relay": 26, "gpio_relay_revert": 21, "tm_clk": 2, "tm_dio": 3},
            "payment": {"api_base": Config.PAYMENT_API_BASE, "api_key": APP_CONFIG["api_key"], "timeout_seconds": APP_CONFIG["payment_timeout_seconds"]},
            "ui": {"background_color": APP_CONFIG["background_color"], "show_setting_button": APP_CONFIG["show_setting_button"], "contact_title": APP_CONFIG["contact_title"], "contact_text": APP_CONFIG["contact_text"]},
            "coin_per_baht_ratio": APP_CONFIG["coin_per_baht_ratio"],
            "BILL_PULSE_TIMEOUT": APP_CONFIG["BILL_PULSE_TIMEOUT"],
            "RELAY_MAX_ACTIVE_TIME": APP_CONFIG["RELAY_MAX_ACTIVE_TIME"],
            "SELECT_AMOUNT": APP_CONFIG["SELECT_AMOUNT"],
            "BILL_PULSE_MAPPING": APP_CONFIG["BILL_PULSE_MAPPING"]
        }
    else:
        try:
            with open(Config.SYSTEM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                sys_data = json.load(f)
        except:
            sys_data = {}
        
        if "app" not in sys_data: sys_data["app"] = {}
        sys_data["app"]["admin_password"] = APP_CONFIG.get("admin_password", "242424")
        
        if "payment" not in sys_data: sys_data["payment"] = {}
        sys_data["payment"]["api_key"] = APP_CONFIG.get("api_key", "F8C04-06726831FD")
        
        sys_data["coin_per_baht_ratio"] = APP_CONFIG.get("coin_per_baht_ratio", 10)
        sys_data["SELECT_AMOUNT"] = APP_CONFIG.get("SELECT_AMOUNT", Config.SELECT_AMOUNT)

    try:
        with open(Config.SYSTEM_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(sys_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[App] Error saving config.json: {e}")

def save_coin_state(raise_error=False):
    app = App.get_running_app()
    stock = app.coin_stock if app else 0
    
    coin_data = {
        "datetime": str(datetime.now(bangkok_tz)).split('.')[0],
        "status": True,
        "active": True,
        "error": 0,
        "coin_stock": stock,
        "current_credit": 0.0,
        "bill_pulse_count": 0,
        "coins_dispensed_count": 0
    }
    if os.path.exists(Config.COIN_STATE_FILE):
        try:
            with open(Config.COIN_STATE_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                old_data["coin_stock"] = stock
                old_data["datetime"] = coin_data["datetime"]
                coin_data = old_data
        except:
            pass
            
    try:
        with open(Config.COIN_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(coin_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[App] Error saving config_coin.json: {e}")
        # ถ้าสั่งให้ฟ้อง Error ก็เด้ง Exception ออกไปให้ UI รู้
        if raise_error:
            raise e

def save_config():
    save_system_config()
    save_coin_state()

# --- MQTT Setup ---
mqtt_client = None
import coin_dispenser

def on_connect(client, userdata, flags, rc):
    if rc == 0: print("[MQTT] Connected successfully!")

def setup_mqtt():
    global mqtt_client
    if Config.SERAIL_ID == "unknown_device": return None
    try:
        client = mqtt.Client(client_id=Config.MQTT_CLIENT_ID, clean_session=True)
        client.on_connect = on_connect
        client.connect_async(Config.MQTT_BROKER, Config.MQTT_PORT, 60)
        return client
    except Exception as e:
        print(f"[MQTT] Error: {e}")
        return None

def publish_mqtt_message(topic, payload):
    if mqtt_client and mqtt_client.is_connected():
        try:
            payload_str = json.dumps(payload, ensure_ascii=False)
            mqtt_client.publish(topic, payload_str, qos=1)
        except: pass

# =============================================================================
# 2. CUSTOM WIDGETS & DEBOUNCE LOGIC
# =============================================================================

class DebounceMixin:
    _last_touch_time = 0
    DEBOUNCE_DELAY = 0.3 

    def check_debounce(self):
        current_time = time.time()
        if current_time - self._last_touch_time < self.DEBOUNCE_DELAY:
            return False
        self._last_touch_time = current_time
        return True

class Card(BoxLayout):
    pass

class SafeButton(Button, DebounceMixin):
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if not self.check_debounce():
                return True
        return super().on_touch_down(touch)

class SoftButton(ButtonBehavior, BoxLayout, DebounceMixin):
    text = StringProperty("")
    bg_color = ListProperty([0.2, 0.6, 0.85, 1]) 
    radius = ListProperty([20,])
    font_size = NumericProperty('20sp')

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if not self.check_debounce():
                return True 
        return super().on_touch_down(touch)

    def on_press(self):
        Animation(opacity=0.7, duration=0.1).start(self)
    def on_release(self):
        Animation(opacity=1, duration=0.1).start(self)

class CircleButton(ButtonBehavior, BoxLayout, DebounceMixin):
    text = StringProperty("")
    bg_color = ListProperty([0.2, 0.6, 0.85, 1])
    scale = NumericProperty(1.0)
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if not self.check_debounce():
                return True 
        return super().on_touch_down(touch)

    def on_press(self):
        Animation(scale=0.9, duration=0.05).start(self)
    def on_release(self):
        Animation(scale=1.0, duration=0.05).start(self)

class HistoryItem(RecycleDataViewBehavior, BoxLayout):
    time = StringProperty("")
    amount = StringProperty("")
    source_type = StringProperty("")
    status_color = ListProperty([0.3, 0.75, 0.45, 1])
    index = None

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        ts = data.get('timestamp') or data.get('log_timestamp', '')
        self.time = ts.replace('T', ' ')[:16] 
        self.amount = str(data.get('amount', '0'))
        txn_type = data.get('type', 'qr_payment')
        if txn_type == 'dispense':
            self.source_type = "CASH"
            self.status_color = [0.9, 0.6, 0.2, 1] 
        else:
            self.source_type = "QR"
            self.status_color = [0.2, 0.6, 0.85, 1] 

        status = data.get('status', 'success')
        if status != 'success':
             self.status_color = [0.9, 0.35, 0.35, 1] 

        return super(HistoryItem, self).refresh_view_attrs(rv, index, data)

class WifiItem(RecycleDataViewBehavior, BoxLayout, DebounceMixin):
    ssid = StringProperty("")
    signal = StringProperty("")
    index = None
    
    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.ssid = data.get('ssid', 'Unknown')
        self.signal = str(data.get('signal', 0)) + "%"
        return super(WifiItem, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if not self.check_debounce():
                return True
            app = App.get_running_app()
            screen = app.root.get_screen('wifi_settings')
            screen.prompt_password(self.ssid)
            return True
        return super(WifiItem, self).on_touch_down(touch)

Factory.register('Card', cls=Card)
Factory.register('SoftButton', cls=SoftButton)
Factory.register('CircleButton', cls=CircleButton)
Factory.register('HistoryItem', cls=HistoryItem)
Factory.register('WifiItem', cls=WifiItem)
Factory.register('SafeButton', cls=SafeButton)

# =============================================================================
# 3. KV DESIGN
# =============================================================================

class SelectAmountEditor(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = dp(15)
        self.padding = [dp(10), dp(10), dp(10), 0]
        self.size_hint_y = 1
        
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(30))
        header.add_widget(Label(text="ตั้งค่าปุ่มราคาหน้าตู้ (SELECT AMOUNT)", font_size='24sp', bold=True, color=[0.1, 0.4, 0.8, 1], halign='left', text_size=(None, None)))
        
        btn_add = SoftButton(text='+ เพิ่มราคา' ,size_hint_x=None, width=dp(160), bg_color=[0.9, 0.35, 0.35, 1], font_size='20sp', radius=[15])
        btn_add.bind(on_release=self.add_new_row)
        header.add_widget(btn_add)
        self.add_widget(header)
        
        self.scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.list_layout = GridLayout(cols=1, spacing=dp(10), size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        self.list_layout.padding = [dp(5), dp(5)]
        
        self.scroll.add_widget(self.list_layout)
        self.add_widget(self.scroll)
        
        self.load_data()

    def load_data(self):
        self.list_layout.clear_widgets()
        amounts = APP_CONFIG.get("SELECT_AMOUNT", [20, 40, 50, 60, 70, 80, 90, 100, 120, 130, 140, 150])
        for amount in amounts:
            self.list_layout.add_widget(SelectAmountRow(amount, self.remove_row))

    def add_new_row(self, instance):
        self.list_layout.add_widget(SelectAmountRow("", self.remove_row))

    def remove_row(self, row_widget):
        self.list_layout.remove_widget(row_widget)

    def get_amounts_data(self):
        new_amounts = []
        for row in self.list_layout.children:
            val = row.amount_input.text.strip()
            if val and val.isdigit():
                new_amounts.append(int(val))
        return sorted(list(set(new_amounts)))

class NumpadPopup(Popup):
    def __init__(self, target_widget, **kwargs):
        super().__init__(**kwargs)
        self.title = "ระบุจำนวนเงิน (บาท)"
        self.title_font = APP_FONT
        self.title_align = 'center'
        self.title_size = '24sp'
        self.size_hint = (0.5, 0.85)
        self.target_widget = target_widget 
        self.background_color = [0, 0, 0, 0.85]
        self.separator_color = [0.2, 0.6, 0.85, 1]
        
        layout = BoxLayout(orientation='vertical', spacing=dp(15), padding=dp(15))
        
        display_box = BoxLayout(size_hint_y=0.25)
        with display_box.canvas.before:
            Color(0.95, 0.95, 0.95, 1)
            self.rect = RoundedRectangle(pos=display_box.pos, size=display_box.size, radius=[15])
        display_box.bind(pos=self.update_rect, size=self.update_rect)
        
        self.display_label = Label(text=self.target_widget.text, font_size='60sp', bold=True, color=[0.1, 0.4, 0.8, 1])
        display_box.add_widget(self.display_label)
        layout.add_widget(display_box)
        
        grid = GridLayout(cols=3, spacing=dp(10), size_hint_y=0.55)
        
        for i in range(1, 10):
            btn = SoftButton(text=str(i), bg_color=[0.3, 0.4, 0.5, 1], font_size='36sp', radius=[15])
            btn.bind(on_release=lambda x, num=str(i): self.add_digit(num))
            grid.add_widget(btn)
        
        btn_clear = SoftButton(text='C', bg_color=[0.9, 0.35, 0.35, 1], font_size='36sp', radius=[15])
        btn_clear.bind(on_release=lambda x: self.clear_display())
        grid.add_widget(btn_clear)
        
        btn_0 = SoftButton(text='0', bg_color=[0.3, 0.4, 0.5, 1], font_size='36sp', radius=[15])
        btn_0.bind(on_release=lambda x: self.add_digit('0'))
        grid.add_widget(btn_0)
        
        btn_del = SoftButton(text='<-', bg_color=[0.9, 0.6, 0.2, 1], font_size='36sp', radius=[15])
        btn_del.bind(on_release=lambda x: self.del_digit())
        grid.add_widget(btn_del)
        
        layout.add_widget(grid)
        
        action_layout = BoxLayout(size_hint_y=0.2, spacing=dp(15))
        btn_cancel = SoftButton(text='ยกเลิก', bg_color=[0.6, 0.6, 0.6, 1], font_size='26sp', radius=[15])
        btn_cancel.bind(on_release=self.dismiss)
        
        btn_ok = SoftButton(text='ตกลง', bg_color=[0.3, 0.75, 0.45, 1], font_size='26sp', radius=[15])
        btn_ok.bind(on_release=self.confirm)
        
        action_layout.add_widget(btn_cancel)
        action_layout.add_widget(btn_ok)
        
        layout.add_widget(action_layout)
        self.content = layout

    def update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def add_digit(self, digit):
        if self.display_label.text == "0" or self.display_label.text == "":
            self.display_label.text = digit
        else:
            self.display_label.text += digit

    def clear_display(self):
        self.display_label.text = ""

    def del_digit(self):
        self.display_label.text = self.display_label.text[:-1]

    def confirm(self, instance):
        if self.display_label.text.strip():
            self.target_widget.text = self.display_label.text.strip()
        self.dismiss()

class SelectAmountRow(BoxLayout):
    def __init__(self, amount_val, remove_callback, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(80) 
        self.spacing = dp(20)
        self.padding = [dp(20), dp(10), dp(20), dp(10)]

        with self.canvas.before:
            Color(0.95, 0.95, 0.95, 1) 
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])
        self.bind(pos=self.update_rect, size=self.update_rect)

        self.amount_input = SoftButton(
            text=str(amount_val), font_size='32sp', size_hint_x=0.5,
            bg_color=[0.2, 0.6, 0.85, 1], radius=[15]
        )
        self.amount_input.bind(on_release=self.open_numpad)
        self.add_widget(self.amount_input)
        
        self.add_widget(Label(text="บาท", font_size='26sp', size_hint_x=0.2, color=[0.2, 0.2, 0.2, 1], bold=True))
        
        btn_remove = SoftButton(
            text="ลบ", bg_color=[0.9, 0.35, 0.35, 1], 
            size_hint_x=0.3, font_size='22sp', radius=[15]
        )
        btn_remove.bind(on_release=lambda x: remove_callback(self))
        self.add_widget(btn_remove)

    def update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size
        
    def open_numpad(self, instance):
        popup = NumpadPopup(target_widget=self.amount_input)
        popup.open()


KV_CODE = f"""
#:import hex kivy.utils.get_color_from_hex

# --- Color Palette ---
#:set c_bg (0.92, 0.96, 0.99, 1)           
#:set c_white (1, 1, 1, 1)
#:set c_primary (0.2, 0.6, 0.85, 1)        
#:set c_primary_dark (0.1, 0.4, 0.6, 1)    
#:set c_red (0.9, 0.35, 0.35, 1)             
#:set c_green (0.3, 0.75, 0.45, 1)           
#:set c_shadow (0, 0, 0, 0.08)
#:set app_font '{APP_FONT}'

<Label>:
    font_name: app_font
    color: c_primary_dark

<Card>:
    padding: [dp(20), dp(20), dp(20), dp(20)]
    canvas.before:
        Color:
            rgba: c_shadow
        BoxShadow:
            pos: self.pos
            size: self.size
            offset: 0, -4
            blur_radius: 12
            spread_radius: [-4, -4]
        Color:
            rgba: c_white
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [20,]

<SafeButton>:
    font_name: app_font
    bold: True

<SoftButton>:
    orientation: 'vertical'
    padding: [dp(10), dp(10)]
    spacing: dp(5)
    alignment: 'center'
    canvas.before:
        Color:
            rgba: c_shadow
        BoxShadow:
            pos: self.x, self.y - 4
            size: self.width, self.height
            offset: 0, -2
            blur_radius: 8
            spread_radius: [-2, -2]
        Color:
            rgba: root.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: root.radius
    Label:
        text: root.text
        font_size: root.font_size
        bold: True
        color: c_white
        halign: 'center'
        valign: 'middle'

<CircleButton>:
    size_hint: None, None
    size: '80dp', '80dp'
    canvas.before:
        PushMatrix
        Scale:
            origin: self.center
            x: self.scale
            y: self.scale
        Color:
            rgba: c_shadow
        BoxShadow:
            pos: self.x, self.y - 3
            size: self.width, self.height
            offset: 0, -2
            blur_radius: 8
            spread_radius: [-2, -2]
        Color:
            rgba: root.bg_color
        Ellipse:
            pos: self.pos
            size: self.size
    canvas.after:
        PopMatrix
    Label:
        text: root.text
        font_size: '30sp'
        bold: True
        color: c_white
        center: root.center

<HistoryItem>:
    size_hint_y: None
    height: '60dp'
    padding: [dp(15), dp(5)]
    canvas.before:
        Color:
            rgba: (0.95, 0.95, 0.95, 1) if self.index is not None and self.index % 2 == 0 else c_white
        Rectangle:
            pos: self.pos
            size: self.size
    Label:
        text: root.time
        size_hint_x: 0.5
        halign: 'left'
        text_size: self.size
        valign: 'middle'
        font_size: '18sp'
        color: (0.4, 0.4, 0.4, 1)
    BoxLayout:
        size_hint_x: 0.2
        padding: [dp(5), dp(15)]
        canvas.before:
            Color:
                rgba: root.status_color
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [10,]
        Label:
            text: root.source_type
            color: c_white
            bold: True
            font_size: '14sp'
            halign: 'center'
            valign: 'middle'
    Label:
        text: root.amount + " บ."
        size_hint_x: 0.3
        halign: 'right'
        text_size: self.size
        valign: 'middle'
        bold: True
        font_size: '22sp'
        color: c_primary

<WifiItem>:
    size_hint_y: None
    height: '70dp'
    padding: [dp(20), dp(10)]
    canvas.before:
        Color:
            rgba: c_white
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: (0.9, 0.9, 0.9, 1)
        Line:
            points: [self.x, self.y, self.x + self.width, self.y]
            width: 1
    BoxLayout:
        orientation: 'vertical'
        size_hint_x: 0.8
        Label:
            text: root.ssid
            font_size: '22sp'
            bold: True
            halign: 'left'
            text_size: self.size
            color: c_primary_dark
    Label:
        text: root.signal
        size_hint_x: 0.2
        color: c_green

# --- Screens ---

<BaseScreen@Screen>:
    canvas.before:
        Color:
            rgba: c_bg
        Rectangle:
            pos: self.pos
            size: self.size

<WelcomeScreen>:
    BaseScreen:
    SafeButton:
        size_hint: None, None
        size: '80dp', '80dp'
        text: "v "+app.APP_VERSION
        pos_hint: {{'top': 1, 'right': 1}}
        background_color: 0,0,0,0
        on_release: app.root.current = 'admin_login'
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(20), dp(20)]
        spacing: dp(10) 
        alignment: 'center'
        Image:
            source: 'images/duck.png'
            size_hint_y:0.5
            fit_mode: 'contain'
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: '50dp'
            Label:
                text: "บริการแลกเหรียญ"
                font_size: '28sp'
                bold: True
                color: c_primary
            Label:
                text: "Wash Lover Coin Exchange"
                font_size: '24sp'
                color: c_primary_dark
        Label:
            text: "ขออภัย เหรียญหมดชั่วคราว"
            font_size: '30sp'
            bold: True
            color: c_red
            size_hint_y: None
            height: '30dp'
            opacity: 1 if app.coin_stock <= 0 else 0

        SoftButton:
            text: "แตะเพื่อเริ่มใช้งาน"
            font_size: '32sp'
            size_hint_y: None
            height: '100dp'
            radius: [50,]
            bg_color: c_primary if app.coin_stock > 0 else (0.7, 0.7, 0.7, 1)
            on_release: root.start_process()

<SelectAmountScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(15), dp(15)]
        spacing: dp(10)
        BoxLayout:
            size_hint_y: None
            height: '60dp'
            Label:
                text: "เลือกจำนวนเงิน"
                font_size: '32sp'
                bold: True
                halign: 'left'
                text_size: self.size
            AnchorLayout:
                size_hint_x: None
                width: '120dp'
                anchor_x: 'right'
                SoftButton:
                    text: " ย้อนกลับ"
                    bg_color: c_red
                    size_hint_y: None
                    height: '50dp'
                    radius: [25,]
                    on_release: app.root.current = 'welcome'
        ScrollView:
            GridLayout:
                id: grid_prices
                cols: 3
                spacing: dp(15)
                padding: [dp(5), dp(5)]
                size_hint_y: None
                height: self.minimum_height
                row_default_height: '95dp'
                row_force_default: True

<PaymentScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(30), dp(20)]
        spacing: dp(15)
        alignment: 'center'
        Label:
            text: "ยอดชำระ " + str(root.amount_to_pay) + " บาท"
            font_size: '48sp'
            bold: True
            color: c_primary
            size_hint_y: None
            height: '60dp'
        Card:
            orientation: 'vertical'
            size_hint: None, None
            size: '380dp', '400dp'
            pos_hint: {{'center_x': 0.5}}
            padding: [dp(10), dp(10)]
            Label:
                id: status_label
                text: "กำลังเชื่อมต่อ..."
                color: (0.4, 0.4, 0.4, 1)
                font_size: '24sp'
                size_hint_y: None
                height: '40dp'
            AnchorLayout:
                anchor_x: 'center'
                anchor_y: 'center'
                AsyncImage:
                    id: qr_image
                    source: ''
                    opacity: 0
                    keep_ratio: True
                    size_hint: None, None
                    size: '260dp', '260dp'
            Label:
                id: timer_label
                text: ""
                color: c_red
                font_size: '26sp'
                bold: True
                size_hint_y: None
                height: '40dp'
        Widget:
            size_hint_y: 1
        SoftButton:
            text: "ยกเลิกรายการ"
            bg_color: c_red
            size_hint_y: None
            height: '70dp'
            radius: [35]
            on_release: root.cancel_payment()

<PointCollectionPromptScreen>:
    BaseScreen:
    AnchorLayout:
        anchor_x: 'center'
        anchor_y: 'center'
        Card:
            orientation: 'vertical'
            size_hint: None, None
            size: '700dp', '350dp'
            padding: [dp(20), dp(30)]
            spacing: dp(15)
            Label:
                text: "แลกเหรียญสำเร็จ!"
                font_size: '48sp'
                bold: True
                color: c_green
                size_hint_y: None
                height: '60dp'
            Label:
                text: "คุณต้องการสะสมคะแนน\\nจากการทำรายการครั้งนี้หรือไม่?"
                font_size: '28sp'
                color: c_primary_dark
                halign: 'center'
                valign: 'middle'
            Widget:
                size_hint_y: None
                height: '10dp'
            BoxLayout:
                size_hint_y: None
                height: '70dp'
                spacing: dp(20)
                SoftButton:
                    text: "ไม่ต้องการ"
                    bg_color: (0.6, 0.6, 0.6, 1)
                    font_size: '26sp'
                    radius: [20]
                    on_release: root.skip()
                SoftButton:
                    text: "สะสมคะแนน"
                    bg_color: c_primary
                    font_size: '26sp'
                    radius: [20]
                    on_release: root.go_to_phone_input()
            Label:
                id: timeout_lbl
                text: ""
                color: c_red
                font_size: '20sp'
                size_hint_y: None
                height: '30dp'

<PhoneInputScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(15), dp(15), dp(15), dp(15)]
        spacing: dp(15)
        
        Label:
            text: "ระบุเบอร์โทรศัพท์เพื่อสะสมคะแนน"
            font_size: '32sp'
            bold: True
            color: c_primary
            size_hint_y: None
            height: '40dp'
            
        BoxLayout:
            size_hint_y: None
            height: '70dp'
            size_hint_x: None
            width: '450dp'
            pos_hint: {{'center_x': 0.5}}
            canvas.before:
                Color:
                    rgba: c_white
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [15]
                Color:
                    rgba: c_primary
                Line:
                    rounded_rectangle: [self.x, self.y, self.width, self.height, 15]
                    width: 1.5
            Label:
                text: root.display_text
                font_size: '46sp'
                bold: True
                color: c_primary_dark
                halign: 'center'
                valign: 'middle'
                text_size: self.size
                
        AnchorLayout:
            GridLayout:
                id: phone_keypad_grid
                cols: 3
                spacing: dp(10)
                size_hint: None, None
                width: '400dp'
                height: '280dp'
                
        BoxLayout:
            size_hint_y: None
            height: '70dp'
            size_hint_x: None
            width: '400dp'
            pos_hint: {{'center_x': 0.5}}
            spacing: dp(20)
            SoftButton:
                text: "ข้าม"
                bg_color: (0.6, 0.6, 0.6, 1)
                font_size: '26sp'
                radius: [15]
                on_release: root.skip()
            SoftButton:
                text: "ยืนยัน"
                bg_color: c_green if len(root.phone_number) == 10 else (0.7, 0.7, 0.7, 1)
                font_size: '26sp'
                radius: [15]
                disabled: len(root.phone_number) < 10
                on_release: root.submit()

<SuccessScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(40), dp(40)]
        spacing: dp(30)
        alignment: 'center'
        Widget:
            id: success_icon
            size_hint: None, None
            size: '180dp', '180dp'
            pos_hint: {{'center_x': 0.5}}
            canvas:
                Color:
                    rgba: c_green
                Line:
                    circle: (self.center_x, self.center_y, self.width/2)
                    width: 6
                Line:
                    points: [self.center_x - 40, self.center_y, self.center_x - 10, self.center_y - 30, self.center_x + 50, self.center_y + 40]
                    width: 10
                    cap: 'round'
                    joint: 'round'
        Label:
            text: "ขอบคุณที่ใช้บริการ!"
            font_size: '50sp'
            bold: True
            color: c_green
            size_hint_y: None
            height: '70dp'
        Label:
            text: "โปรดรอรับเหรียญที่ช่องจ่าย"
            font_size: '28sp'
            color: (0.5, 0.5, 0.5, 1)

<ErrorScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(40), dp(40)]
        spacing: dp(30)
        alignment: 'center'
        Widget:
            id: error_icon
            size_hint: None, None
            size: '180dp', '180dp'
            pos_hint: {{'center_x': 0.5}}
            canvas:
                Color:
                    rgba: c_red
                Line:
                    circle: (self.center_x, self.center_y, self.width/2)
                    width: 6
                Line:
                    points: [self.center_x - 40, self.center_y - 40, self.center_x + 40, self.center_y + 40]
                    width: 10
                    cap: 'round'
                Line:
                    points: [self.center_x + 40, self.center_y - 40, self.center_x - 40, self.center_y + 40]
                    width: 10
                    cap: 'round'
        Label:
            text: "ขออภัย"
            font_size: '50sp'
            bold: True
            color: c_red
            size_hint_y: None
            height: '70dp'
        Label:
            id: error_msg
            text: "เกิดข้อผิดพลาด"
            font_size: '28sp'
            color: (0.5, 0.5, 0.5, 1)
        SoftButton:
            text: "กลับหน้าหลัก"
            bg_color: c_red
            size_hint_y: None
            height: '80dp'
            radius: [40,]
            on_release: app.root.current = 'welcome'

<AdminLoginScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(20), dp(10)]
        spacing: dp(5)
        AnchorLayout:
            size_hint_y: None
            height: '60dp'
            anchor_x: 'right'
            SafeButton:
                text: "X"
                font_size: '32sp'
                bold: True
                color: c_primary_dark
                background_color: 0,0,0,0
                size_hint: None, None
                size: '60dp', '60dp'
                on_release: app.root.current = 'welcome'
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: '100dp'
            spacing: dp(15)
            Label:
                text: "ยืนยันตัวตน"
                font_size: '42sp'
                bold: True
                size_hint_y: None
                height: '50dp'
            Label:
                text: "*" * len(root.pin_text) if root.pin_text else "_ _ _ _ _ _"
                font_size: '42sp'
                color: c_primary
                size_hint_y: None
                height: '50dp'
                font_name: 'Roboto'
        AnchorLayout:
            anchor_x: 'center'
            anchor_y: 'center'
            size_hint: 1, 1
            GridLayout:
                id: keypad_grid
                cols: 3
                spacing: dp(10)
                size_hint: None, None
                width: self.minimum_width
                height: self.minimum_height

<AdminDashboardScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(10), dp(10)]
        spacing: dp(10)
        BoxLayout:
            size_hint_y: None
            height: '60dp'
            Label:
                text: "Id: " + app.SERAIL_ID
                halign: 'left'
                text_size: self.size
                bold: True
                font_size: '20sp'
            Label:
                text: "IP:" + app.GET_IP
                halign: 'left'
                text_size: self.size
                bold: True
                font_size: '20sp'
            SoftButton:
                text: "Wi-Fi"
                bg_color: [0.2, 0.5, 0.8, 1]
                size_hint_x: None
                width: '100dp'
                font_size: '18sp'
                on_release: app.root.current = 'wifi_settings'
            Widget:
                size_hint_x: None
                width: '10dp'
            SoftButton:
                text: "รีสตารท์"
                bg_color: (0.3, 0.3, 0.3, 1)
                size_hint_x: None
                width: '100dp'
                font_size: '14sp'
                on_release: root.reboot_system()
            SoftButton:
                text: "ปิดโปรแกรม"
                bg_color: (0.3, 0.3, 0.3, 1)
                size_hint_x: None
                width: '100dp'
                font_size: '14sp'
                on_release: root.shutdown_system()
            Widget:
                size_hint_x: None
                width: '10dp'
            SoftButton:
                text: "Logout"
                bg_color: c_red
                size_hint_x: None
                width: '80dp'
                font_size: '16sp'
                on_release: app.logout()
        BoxLayout:
            size_hint_y: None
            height: '70dp'
            spacing: dp(15)
            canvas.before:
                Color:
                    rgba: c_white
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [15,]
            ToggleButton:
                text: "จำนวนเหรียญ"
                group: 'admin_tabs'
                state: 'down'
                font_name: app_font
                font_size: '20sp'
                bold: True
                background_normal: ''
                background_down: ''
                background_color: (0,0,0,0)
                color: c_primary if self.state == 'down' else (0.6,0.6,0.6,1)
                on_press: root.current_tab = 'stock'
            ToggleButton:
                text: "ตั้งค่า"
                group: 'admin_tabs'
                font_name: app_font
                font_size: '20sp'
                bold: True
                background_normal: ''
                background_down: ''
                background_color: (0,0,0,0)
                color: c_primary if self.state == 'down' else (0.6,0.6,0.6,1)
                on_press: root.current_tab = 'settings'
            ToggleButton:
                text: "ประวัติ"
                group: 'admin_tabs'
                font_name: app_font
                font_size: '20sp'
                bold: True
                background_normal: ''
                background_down: ''
                background_color: (0,0,0,0)
                color: c_primary if self.state == 'down' else (0.6,0.6,0.6,1)
                on_press: root.current_tab = 'history'
            ToggleButton:
                text: "เวอร์ชั้น"
                group: 'admin_tabs'
                font_name: app_font
                font_size: '20sp'
                bold: True
                background_normal: ''
                background_down: ''
                background_color: (0,0,0,0)
                color: c_primary if self.state == 'down' else (0.6,0.6,0.6,1)
                on_press: root.current_tab = 'update'
        Card:
            id: content_area
            orientation: 'vertical'
            padding: [dp(20), dp(20)]

<WifiScreen>:
    BaseScreen:
    BoxLayout:
        orientation: 'vertical'
        padding: [dp(20), dp(20)]
        spacing: dp(10)
        BoxLayout:
            size_hint_y: None
            height: '60dp'
            Label:
                text: "ตั้งค่า Wi-Fi"
                font_size: '32sp'
                bold: True
                halign: 'left'
                text_size: self.size
            SoftButton:
                text: "สแกน"
                bg_color: c_primary
                size_hint_x: None
                width: '100dp'
                on_release: root.scan_wifi()
            Widget:
                size_hint_x: None
                width: '10dp'
            SoftButton:
                text: "กลับ"
                bg_color: c_red
                size_hint_x: None
                width: '100dp'
                on_release: app.root.current = 'admin_dashboard'
        Label:
            id: status_label
            text: "พร้อมใช้งาน"
            size_hint_y: None
            height: '40dp'
            color: (0.4,0.4,0.4,1)
        RecycleView:
            id: rv_wifi
            viewclass: 'WifiItem'
            RecycleBoxLayout:
                default_size: None, dp(80)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
                spacing: dp(5)

<PasswordPopupContent>:
    orientation: 'vertical'
    padding: dp(15)
    spacing: dp(15)
    Label:
        text: "เชื่อมต่อ: " + root.ssid_name
        size_hint_y: None
        height: '40dp'
        font_size: '24sp'
        color: c_white
        bold: True
    TextInput:
        id: input_pass
        multiline: False
        password: False
        font_size: '32sp'
        size_hint_y: None
        height: '60dp'
        readonly: True 
    GridLayout:
        cols: 10
        spacing: dp(8)
        id: keyboard_grid
    BoxLayout:
        size_hint_y: None
        height: '70dp'
        spacing: dp(15)
        SoftButton:
            text: "ยกเลิก"
            bg_color: c_red
            radius: [15]
            font_size: '24sp'
            on_release: root.cancel()
        SoftButton:
            text: "เชื่อมต่อ"
            bg_color: c_green
            radius: [15]
            font_size: '24sp'
            on_release: root.confirm(input_pass.text)
"""

# =============================================================================
# 4. PYTHON LOGIC
# =============================================================================

c_gpio = None 

class WelcomeScreen(Screen):
    def start_process(self):
        app = App.get_running_app()
        if app.coin_stock <= 0:
            return

        if check_internet_connection():
            self.manager.current = 'select_amount'
        else:
            self.manager.get_screen('error').set_error("ไม่สามารถเชื่อมต่ออินเทอร์เน็ตได้")
            self.manager.current = 'error'

class SelectAmountScreen(Screen):
    def on_enter(self):
        load_config()
        grid = self.ids.grid_prices
        grid.clear_widgets()
        for amount in Config.SELECT_AMOUNT:
            btn = SoftButton(text=f"{amount}\nบาท", font_size='26sp')
            btn.bind(on_release=lambda x, a=amount: self.select_amount(a))
            grid.add_widget(btn)

    def select_amount(self, amount):
        if check_internet_connection():
            payment_screen = self.manager.get_screen('payment')
            payment_screen.set_amount(amount)
            self.manager.current = 'payment'
        else:
            self.manager.get_screen('error').set_error("ไม่สามารถเชื่อมต่ออินเทอร์เน็ตได้")
            self.manager.current = 'error'

class PaymentScreen(Screen):
    amount_to_pay = NumericProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cancel_event = threading.Event()
        self.countdown_event = None
        self.payment_succeeded = False

    def set_amount(self, amount):
        self.amount_to_pay = amount

    def on_enter(self, *args):
        self._cancel_event.clear()
        self.payment_succeeded = False
        self.ids.qr_image.source = ''
        self.ids.qr_image.opacity = 0
        self.ids.timer_label.text = ""
        self.ids.status_label.text = "กำลังสร้าง QR Code..."
        threading.Thread(target=self._call_payment_api, daemon=True).start()

    def _call_payment_api(self):
        try:
            params = {"amount": self.amount_to_pay, "secretKey": Config.API_KEY, "username": Config.USERNAME,"device":"OD0445560V7002081BQ","type":"tung"}
            response = requests.get(Config.PAYMENT_API_BASE, params=params, timeout=10)
            if self._cancel_event.is_set(): return
            response.raise_for_status()
            data = response.json()
            if data and data.get('qrcode'):
                Clock.schedule_once(lambda dt: self._update_qr_and_start_timers(data.get('image2'), data.get('url_check')))
            else: 
                Clock.schedule_once(lambda dt: self.fail_transaction("API Error"))
        except Exception as e:
            if not self._cancel_event.is_set():
                Clock.schedule_once(lambda dt: self.fail_transaction(str(e)))

    def _update_qr_and_start_timers(self, qr_img_url, check_url):
        if self._cancel_event.is_set(): return
        self.ids.qr_image.source = qr_img_url
        self.ids.qr_image.opacity = 1
        self.ids.status_label.text = "กรุณาสแกน PromptPay"
        self.countdown_time = APP_CONFIG["payment_timeout_seconds"]
        if self.countdown_event: self.countdown_event.cancel()
        self.countdown_event = Clock.schedule_interval(self.update_countdown, 1)
        threading.Thread(target=self._check_payment_status_loop, args=(check_url,), daemon=True).start()

    def update_countdown(self, dt):
        self.countdown_time -= 1
        self.ids.timer_label.text = f"เหลือเวลา: {self.countdown_time} วินาที"
        if self.countdown_time <= 0:
            self.cancel_payment()

    def _check_payment_status_loop(self, check_url):
        while not self._cancel_event.is_set() and not self.payment_succeeded:
            try:
                response = requests.get(check_url, timeout=3)
                data = response.json()
                status = data.get('data', {}).get('status')
                if status == "success":
                    self.payment_succeeded = True
                    Clock.schedule_once(lambda dt, d=data: self.payment_successful(d))
                    break
                elif status == "failed":
                    Clock.schedule_once(lambda dt: self.fail_transaction("การชำระเงินล้มเหลว"))
                    break
            except: pass
            time.sleep(3)

    def payment_successful(self, transaction_data):
        self._cleanup()
        
        transaction_details = transaction_data.get('data', {})
        amount_str = transaction_details.get('amount', '0.00')
        coins_to_dispense = _calculate_coins_from_amount(amount_str)
        
        log_data = {
            "status": "success",
            "amount": amount_str,
            "coins": coins_to_dispense, "device_id": Config.SERAIL_ID,  
            "message":"ชำระเงินผ่าน Payment สำเร็จ",
            "refId" : transaction_details.get('refId',"Payment") ,
            "transaction_id": transaction_details.get('ref1',transaction_details.get('refId', "Payment") )
        }
        log_transaction(log_data)
        
        mqtt_payload = {
            "status": "success", 
            "action":"payment",
            "amount": amount_str,
            "coins_to_dispense": coins_to_dispense,
            "coins_dispensed": 0,
            "message":"ชำระเงินผ่าน Payment สำเร็จ",
            "refId" : transaction_details.get('refId', "Payment"),
            "coins": coins_to_dispense, "device_id": Config.SERAIL_ID,
            "version":APP_VERSION
        }
        publish_mqtt_message(Config.MQTT_TOPIC_PAYMENT_SUCCESS, mqtt_payload)

        app = App.get_running_app()
        app.last_transaction_ref = transaction_details.get('refId', "Payment")
        app.last_transaction_amount = amount_str

        if coins_to_dispense > 0:
            c_gpio.start_dispensing(coins_to_dispense,transaction_details.get('refId'))
        print(c_gpio.check_status())
        
        self.manager.current = 'point_prompt'

    def fail_transaction(self, msg):
        self._cleanup()
        self.manager.get_screen('error').set_error(msg)
        self.manager.current = 'error'

    def cancel_payment(self):
        self._cleanup()
        self._cancel_event.set()
        self.manager.current = 'welcome'

    def _cleanup(self):
        if self.countdown_event:
            self.countdown_event.cancel()
            self.countdown_event = None

# ==========================================
# หน้าจอถามเพื่อเก็บคะแนน (Point Collection)
# ==========================================
class PointCollectionPromptScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout_event = None
        self.countdown_time = 15

    def on_enter(self):
        self.countdown_time = 15
        self.ids.timeout_lbl.text = f"ข้ามอัตโนมัติใน {self.countdown_time} วินาที"
        if self.timeout_event:
            self.timeout_event.cancel()
        self.timeout_event = Clock.schedule_interval(self.update_timeout, 1)

    def update_timeout(self, dt):
        self.countdown_time -= 1
        self.ids.timeout_lbl.text = f"ข้ามอัตโนมัติใน {self.countdown_time} วินาที"
        if self.countdown_time <= 0:
            self.skip()

    def on_leave(self):
        if self.timeout_event:
            self.timeout_event.cancel()
            self.timeout_event = None

    def skip(self):
        if self.timeout_event:
            self.timeout_event.cancel()
        self.manager.current = 'success'

    def go_to_phone_input(self):
        if self.timeout_event:
            self.timeout_event.cancel()
        self.manager.current = 'phone_input'


# ==========================================
# หน้าจอกรอกเบอร์โทรศัพท์ (มี API ยิงขอคะแนนหลังบ้าน)
# ==========================================
class PhoneInputScreen(Screen):
    phone_number = StringProperty("")
    display_text = StringProperty("_ _ _ _ _ _ _ _ _ _")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout_event = None
        self.countdown_time = 30

    def on_enter(self):
        self.phone_number = ""
        self.build_keypad()
        self.countdown_time = 30
        if self.timeout_event:
            self.timeout_event.cancel()
        self.timeout_event = Clock.schedule_interval(self.update_timeout, 1)

    def on_phone_number(self, instance, value):
        self.update_display()

    def update_display(self):
        p = self.phone_number
        # เอาขีดล่างเติมถ้าไม่ถึง 10 ตัว
        p_padded = p + "_" * (10 - len(p))
        self.display_text = p_padded

    def update_timeout(self, dt):
        self.countdown_time -= 1
        if self.countdown_time <= 0:
            self.skip()

    def on_leave(self):
        if self.timeout_event:
            self.timeout_event.cancel()
            self.timeout_event = None

    def build_keypad(self):
        grid = self.ids.phone_keypad_grid
        grid.clear_widgets()
        for i in range(1, 10):
            btn = SoftButton(text=str(i), bg_color=[0.2, 0.6, 0.85, 1], font_size='36sp', radius=[15])
            btn.bind(on_release=lambda x, num=str(i): self.add_digit(num))
            grid.add_widget(btn)
            
        btn_c = SoftButton(text='C', bg_color=[0.9, 0.35, 0.35, 1], font_size='36sp', radius=[15])
        btn_c.bind(on_release=lambda x: self.clear_input())
        grid.add_widget(btn_c)
        
        btn_0 = SoftButton(text='0', bg_color=[0.2, 0.6, 0.85, 1], font_size='36sp', radius=[15])
        btn_0.bind(on_release=lambda x: self.add_digit('0'))
        grid.add_widget(btn_0)
        
        btn_del = SoftButton(text='<-', bg_color=[0.9, 0.6, 0.2, 1], font_size='36sp', radius=[15])
        btn_del.bind(on_release=lambda x: self.del_digit())
        grid.add_widget(btn_del)

    def add_digit(self, digit):
        self.countdown_time = 30 
        if len(self.phone_number) < 10:
            self.phone_number += digit

    def del_digit(self):
        self.countdown_time = 30
        if len(self.phone_number) > 0:
            self.phone_number = self.phone_number[:-1]

    def clear_input(self):
        self.countdown_time = 30
        self.phone_number = ""

    def submit(self):
        if len(self.phone_number) == 10:
            app = App.get_running_app()
            amount_str = app.last_transaction_amount
            try:
                points_exp = int(float(amount_str))
            except:
                points_exp = 0

            phone_to_send = self.phone_number

            # ส่ง MQTT เก็บ Log ตามเดิม
            payload_mqtt = {
                "phone": phone_to_send,
                "amount": amount_str,
                "refId": app.last_transaction_ref,
                "timestamp": datetime.now(bangkok_tz).isoformat()
            }
            publish_mqtt_message(Config.MQTT_TOPIC_LOGS + "/points", payload_mqtt)

            # เคลียร์เบอร์ออกจากหน้าจอ
            self.phone_number = ""

            # ฟังก์ชันยิง API ระบบคะแนนหลังบ้าน (Threading เพื่อไม่ให้หน้าตู้ค้าง)
            def _send_api():
                url = "http://45.144.166.198:8000/api/admin/users/topup_by_phone"
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": "WASHLOVER_IOT_SECRET_2026"
                }
                payload_api = {
                    "phone": phone_to_send, 
                    "balance": 0, 
                    "points": points_exp, 
                    "exp": points_exp, 
                    "transaction_type": "ตู้แลกเหรียญ", 
                    "details": "เก็บคะแนนผ่านตู้แลกเหรียญ"
                }
                try:
                    response = requests.post(url, json=payload_api, headers=headers, timeout=5)
                    if response.status_code == 200:
                        print("✅ ทำรายการสำเร็จ")
                        Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'success'))
                    else:
                        print("❌ ไม่พบเบอร์โทรศัพท์กรุณาสมัครสมาชิกผ่านแอป")
                        Clock.schedule_once(lambda dt: self.show_phone_error())
                except Exception as e:
                    print(f"API Error: {e}")
                    Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'success'))

            threading.Thread(target=_send_api, daemon=True).start()

    def show_phone_error(self):
        theme_color = [0.9, 0.35, 0.35, 1]
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20))
        lbl = Label(text="ไม่พบเบอร์โทรศัพท์\\nกรุณาสมัครสมาชิกผ่านแอป", font_size='24sp', bold=True, color=theme_color, halign='center', valign='middle')
        lbl.bind(size=lbl.setter('text_size'))
        layout.add_widget(lbl)
        
        btn_close = SoftButton(text='ตกลง', bg_color=theme_color, size_hint_y=None, height=dp(60), radius=[15])
        layout.add_widget(btn_close)
        
        popup = Popup(title="แจ้งเตือน", title_font=APP_FONT, title_size='24sp', title_align='center',
                      content=layout, size_hint=(0.5, 0.4), separator_color=theme_color, auto_dismiss=False)
        
        def on_close(instance):
            popup.dismiss()
            self.manager.current = 'success'

        btn_close.bind(on_release=on_close)
        popup.open()

    def skip(self):
        self.phone_number = ""
        self.manager.current = 'success'


class SuccessScreen(Screen):
    def on_enter(self):
        icon = self.ids.success_icon
        anim = Animation(size=(dp(220), dp(220)), duration=0.2, t='out_back')
        anim += Animation(size=(dp(180), dp(180)), duration=0.1)
        anim.start(icon)
        Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'welcome'), 5)

class ErrorScreen(Screen):
    def set_error(self, msg):
        self.ids.error_msg.text = msg

class AdminLoginScreen(Screen):
    pin_text = StringProperty("")
    
    def on_enter(self):
        self.pin_text = ""
        grid = self.ids.keypad_grid
        grid.clear_widgets()
        for i in range(1, 10):
            btn = CircleButton(text=str(i))
            btn.bind(on_release=lambda x, num=str(i): self.add_pin(num))
            grid.add_widget(btn)
        btn_c = CircleButton(text='C', bg_color=[0.9, 0.35, 0.35, 1])
        btn_c.bind(on_release=lambda x: self.clear_pin())
        grid.add_widget(btn_c)
        btn_0 = CircleButton(text='0')
        btn_0.bind(on_release=lambda x: self.add_pin('0'))
        grid.add_widget(btn_0)
        btn_go = CircleButton(text='>', bg_color=[0.3, 0.75, 0.45, 1])
        btn_go.bind(on_release=lambda x: self.submit_pin())
        grid.add_widget(btn_go)

    def add_pin(self, num):
        if len(self.pin_text) < 6: self.pin_text += num
    def clear_pin(self): self.pin_text = ""
    def submit_pin(self):
        if self.pin_text == APP_CONFIG["admin_password"]:
            self.manager.current = 'admin_dashboard'
        else:
            self.pin_text = ""

class AdminDashboardScreen(Screen):
    current_tab = StringProperty('stock')
    stock_input = StringProperty("0")
    
    def on_current_tab(self, instance, value):
        self.load_tab_content(value)
        
    def on_enter(self):
        self.load_tab_content(self.current_tab)

    def load_tab_content(self, tab_name):
        if not self.ids or 'content_area' not in self.ids:
            return
            
        container = self.ids.content_area
        container.clear_widgets()
        
        if tab_name == 'stock':
            self.stock_input = "0"
            main_layout = BoxLayout(orientation='horizontal', spacing=dp(20))
            
            left_col = BoxLayout(orientation='vertical', spacing=dp(20), size_hint_x=0.55, padding=[0, dp(10), 0, 0])
            
            top_box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(80))
            top_box.add_widget(Label(text="จำนวนเหรียญในเครื่องปัจจุบัน:", font_size='22sp', halign='center', color=[0.4, 0.4, 0.4, 1]))
            stock_val = Label(text=str(App.get_running_app().coin_stock), font_size='60sp', bold=True, color=[0.2, 0.6, 0.85, 1])
            App.get_running_app().bind(coin_stock=lambda i, v: setattr(stock_val, 'text', str(v)))
            top_box.add_widget(stock_val)
            left_col.add_widget(top_box)

            input_box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(80))
            input_box.add_widget(Label(text="ระบุจำนวนเหรียญ:", font_size='20sp', halign='center', color=[0.5, 0.5, 0.5, 1]))
            input_label = Label(text=self.stock_input, font_size='48sp', color=[0.2, 0.2, 0.2, 1], bold=True)
            self.bind(stock_input=input_label.setter('text'))
            input_box.add_widget(input_label)
            left_col.add_widget(input_box)
            
            action_box = BoxLayout(size_hint_y=None, height=dp(65), spacing=dp(10))
            
            btn_add = SoftButton(text="เพิ่ม (+)", bg_color=[0.3, 0.75, 0.45, 1], font_size='20sp', radius=[15])
            btn_add.bind(on_release=lambda x: self.execute_stock_action('add'))
            
            btn_set = SoftButton(text="ตั้งค่า (=)", bg_color=[0.2, 0.6, 0.85, 1], font_size='20sp', radius=[15])
            btn_set.bind(on_release=lambda x: self.execute_stock_action('set'))
            
            btn_clr_stock = SoftButton(text="เคลียร์ (0)", bg_color=[0.9, 0.35, 0.35, 1], font_size='20sp', radius=[15])
            btn_clr_stock.bind(on_release=lambda x: self.execute_stock_action('clear'))

            action_box.add_widget(btn_add)
            action_box.add_widget(btn_set)
            action_box.add_widget(btn_clr_stock)
            left_col.add_widget(action_box)
            
            left_col.add_widget(Widget()) 
            main_layout.add_widget(left_col)

            right_col = AnchorLayout(anchor_x='center', anchor_y='center', size_hint_x=0.45, padding=[dp(10), dp(10), dp(10), dp(10)])
            
            pad_grid = GridLayout(cols=3, spacing=dp(10), size_hint=(1, 0.85))
            for i in range(1, 10):
                btn = SoftButton(text=str(i), bg_color=[0.3, 0.4, 0.5, 1], font_size='36sp', radius=[15])
                btn.bind(on_release=lambda x, n=str(i): self.add_stock_digit(n))
                pad_grid.add_widget(btn)
            
            btn_c = SoftButton(text='C', bg_color=[0.9, 0.35, 0.35, 1], font_size='36sp', radius=[15])
            btn_c.bind(on_release=lambda x: self.clear_stock_input())
            pad_grid.add_widget(btn_c)
            
            btn_0 = SoftButton(text='0', bg_color=[0.3, 0.4, 0.5, 1], font_size='36sp', radius=[15])
            btn_0.bind(on_release=lambda x: self.add_stock_digit('0'))
            pad_grid.add_widget(btn_0)
            
            btn_del = SoftButton(text='-', bg_color=[0.9, 0.6, 0.2, 1], font_size='36sp', radius=[15])
            btn_del.bind(on_release=lambda x: self.del_stock_digit())
            pad_grid.add_widget(btn_del)
            
            right_col.add_widget(pad_grid)
            main_layout.add_widget(right_col)

            container.add_widget(main_layout)

        elif tab_name == 'settings':
            layout = BoxLayout(orientation='vertical', spacing=dp(10))
            self.amount_editor = SelectAmountEditor()
            layout.add_widget(self.amount_editor)

            btn_save = SoftButton(text='บันทึกยอดเงิน', bg_color=[0.2, 0.6, 0.85, 1], size_hint_y=None, height=dp(60), font_size='20sp')
            btn_save.bind(on_release=lambda x: self.save_settings())
            
            save_box = BoxLayout(size_hint_y=None, height=dp(100), padding=[dp(20), dp(10), dp(20), dp(10)])
            save_box.add_widget(btn_save)
            
            layout.add_widget(save_box)
            container.add_widget(layout)


        elif tab_name == 'history':
            rv = RecycleView(viewclass='HistoryItem')
            logs = []
            if os.path.exists(Config.TRANSACTION_LOG_FILE):
                try:
                    with open(Config.TRANSACTION_LOG_FILE, 'r') as f: logs = json.load(f)
                except: pass
            rv.data = logs[::-1]
            
            from kivy.uix.recycleboxlayout import RecycleBoxLayout
            rb = RecycleBoxLayout(default_size=(None, dp(70)), default_size_hint=(1, None), size_hint_y=None, orientation='vertical', spacing=dp(5))
            rb.bind(minimum_height=rb.setter('height'))
            rv.add_widget(rb)
            container.add_widget(rv)

        elif tab_name == 'update':
            layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
            
            self.lbl_current_version = Label(text=f"เวอร์ชันปัจจุบัน: {APP_VERSION}", font_size='24sp', color=[0.4, 0.4, 0.4, 1], size_hint_y=None, height=dp(40))
            self.lbl_latest_version = Label(text="เวอร์ชันล่าสุด: กำลังตรวจสอบ...", font_size='24sp', color=[0.2, 0.6, 0.85, 1], bold=True, size_hint_y=None, height=dp(40))
            self.lbl_update_status = Label(text="", font_size='20sp', color=[0.9, 0.6, 0.2, 1], size_hint_y=None, height=dp(40))
            
            layout.add_widget(self.lbl_current_version)
            layout.add_widget(self.lbl_latest_version)
            layout.add_widget(self.lbl_update_status)
            
            btn_layout = BoxLayout(size_hint_y=None, height=dp(70), spacing=dp(20))
            
            self.btn_check = SoftButton(text="ตรวจสอบอัพเดท", bg_color=[0.2, 0.6, 0.85, 1])
            self.btn_check.bind(on_release=lambda x: self.check_update())
            
            self.btn_do_update = SoftButton(text="ดาวน์โหลดอัพเดท", bg_color=[0.3, 0.75, 0.45, 1], disabled=True, opacity=0.5)
            self.btn_do_update.bind(on_release=lambda x: self.start_update())
            
            self.btn_restart = SoftButton(text="รีสตาร์ทระบบ", bg_color=[0.9, 0.35, 0.35, 1], disabled=True, opacity=0.5)
            self.btn_restart.bind(on_release=lambda x: self.reboot_system())
            
            btn_layout.add_widget(self.btn_check)
            btn_layout.add_widget(self.btn_do_update)
            btn_layout.add_widget(self.btn_restart)
            
            layout.add_widget(btn_layout)
            layout.add_widget(Widget()) 
            container.add_widget(layout)
            
            self.check_update()
    
    def check_update(self):
        self.lbl_latest_version.text = "เวอร์ชันล่าสุด: กำลังตรวจสอบ..."
        self.lbl_update_status.text = ""
        threading.Thread(target=self._thread_check_update, daemon=True).start()

    def _thread_check_update(self):
        try:
            res = requests.get("http://141.98.19.190:4000/api/coin_machine_hybrid", timeout=5)
            res.raise_for_status()
            data = res.json()
            self.latest_api_data = data
            latest_ver = data.get("version", "Unknown")
            Clock.schedule_once(lambda dt: self._update_version_ui(latest_ver))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.lbl_latest_version, 'text', f"ข้อผิดพลาด: ไม่สามารถเชื่อมต่อ API ได้"))

    def _update_version_ui(self, latest_ver):
        self.lbl_latest_version.text = f"เวอร์ชันล่าสุด: {latest_ver}"
        if latest_ver != APP_VERSION and latest_ver != "Unknown":
            self.btn_do_update.disabled = False
            self.btn_do_update.opacity = 1
            self.lbl_update_status.text = "มีอัพเดทใหม่! กดปุ่มดาวน์โหลดเพื่อติดตั้ง"
            self.lbl_update_status.color = [0.2, 0.6, 0.85, 1]
        else:
            self.btn_do_update.disabled = True
            self.btn_do_update.opacity = 0.5
            self.lbl_update_status.text = "ระบบของคุณเป็นเวอร์ชันล่าสุดแล้ว"
            self.lbl_update_status.color = [0.3, 0.75, 0.45, 1]

    def start_update(self):
        if hasattr(self, 'latest_api_data'):
            self.btn_do_update.disabled = True
            self.btn_do_update.opacity = 0.5
            self.btn_check.disabled = True
            self.btn_check.opacity = 0.5
            self.lbl_update_status.color = [0.9, 0.6, 0.2, 1]
            self.lbl_update_status.text = "กำลังดาวน์โหลดไฟล์... กรุณาอย่าปิดเครื่อง!"
            threading.Thread(target=self._thread_do_update, args=(self.latest_api_data,), daemon=True).start()

    def _thread_do_update(self, api_data):
        files_to_download = api_data.get("data", [])
        total = len(files_to_download)
        success_count = 0
        
        for i, item in enumerate(files_to_download):
            try:
                file_url = item.get("url")
                file_path = item.get("path")
                file_name = item.get("file")
                
                if not file_url or not file_path or not file_name:
                    continue
                    
                if not os.path.exists(file_path):
                    os.makedirs(file_path, exist_ok=True)
                    
                full_path = os.path.join(file_path, file_name)
                
                Clock.schedule_once(lambda dt, f=file_name, c=i+1, t=total: setattr(self.lbl_update_status, 'text', f"ดาวน์โหลด ({c}/{t}): {f}"))
                
                res = requests.get(file_url, timeout=15)
                res.raise_for_status()
                
                with open(full_path, 'wb') as f:
                    f.write(res.content)
                    
                success_count += 1
            except Exception as e:
                print(f"[Update] Error downloading {item.get('file')}: {e}")
                
        Clock.schedule_once(lambda dt: self._update_finished(success_count, total))

    def _update_finished(self, success_count, total):
        self.btn_check.disabled = False
        self.btn_check.opacity = 1
        
        if success_count == total and total > 0:
            self.lbl_update_status.text = f"อัพเดทสำเร็จ ({success_count}/{total} ไฟล์)! กรุณากดปุ่มรีสตาร์ท"
            self.lbl_update_status.color = [0.3, 0.75, 0.45, 1]
            self.btn_restart.disabled = False
            self.btn_restart.opacity = 1
        else:
            self.lbl_update_status.text = f"ดาวน์โหลดไม่สมบูรณ์ ({success_count}/{total} ไฟล์) โปรดลองใหม่อีกครั้ง"
            self.lbl_update_status.color = [0.9, 0.35, 0.35, 1]
            self.btn_do_update.disabled = False
            self.btn_do_update.opacity = 1

    def reboot_system(self):
        self.lbl_update_status.text = "กำลังรีสตาร์ทระบบ..."
        os.system("sudo reboot")
        
    def add_stock_digit(self, digit):
        if self.stock_input == "0": self.stock_input = digit
        else: self.stock_input += digit
    
    def clear_stock_input(self):
        self.stock_input = "0"
        
    def del_stock_digit(self):
        if len(self.stock_input) > 1:
            self.stock_input = self.stock_input[:-1]
        else:
            self.stock_input = "0"

    def execute_stock_action(self, action):
        app = App.get_running_app()
        
        # ล็อคการ Sync ไฟล์ชั่วคราว
        app.is_updating_stock = True
        
        try:
            val = int(self.stock_input)
        except: val = 0
        
        if action == 'add':
            app.coin_stock += val
        elif action == 'set':
            app.coin_stock = val
        elif action == 'clear':
            app.coin_stock = 0
            
        self.stock_input = "0"

        # พยายามเซฟลงไฟล์ ถ้าเซฟไม่เข้า (ติด Permission) ให้เด้งแจ้งเตือนสีแดง!
        try:
            save_coin_state(raise_error=True)
        except Exception as e:
            if hasattr(self, 'show_alert'):
                self.show_alert("เซฟไฟล์ไม่เข้า!", f"ไฟล์ถูกล็อคสิทธิ์ Permission ไว้\nรบกวนรัน sudo chmod 777\nError: {e}", is_error=True)
            Clock.schedule_once(lambda dt: setattr(app, 'is_updating_stock', False), 1.5)
            return

        # ถ้าเซฟไฟล์ผ่าน ค่อยยัดค่าเข้า Memory ของ Hardware 
        global c_gpio
        if c_gpio:
            if hasattr(c_gpio, 'COIN_CONFIG'):
                c_gpio.COIN_CONFIG['coin_stock'] = app.coin_stock
            if hasattr(c_gpio, 'RUN_STATUS'):
                c_gpio.RUN_STATUS['coin_stock'] = app.coin_stock
            if hasattr(c_gpio, 'save_coin_config'):
                c_gpio.save_coin_config()

        # ปลดล็อค Sync
        Clock.schedule_once(lambda dt: setattr(app, 'is_updating_stock', False), 1.5)

        mqtt_payload = {
            "by": "Admin", 
            "type":"coin_stock", 
            "command":"coin_stock", 
            "action":action, 
            "val":val,
            "value": app.coin_stock,
            "message":"ตั้งค่าเหรียญหน้าตู้"
        }
        publish_mqtt_message(Config.MQTT_TOPIC_COMMAND, mqtt_payload)
        
        if hasattr(self, 'show_alert'):
            self.show_alert("สำเร็จ", f"อัปเดตสต็อกเหรียญเป็น {app.coin_stock} แล้ว!")

    def show_alert(self, title, message, is_error=False):
        theme_color = [0.9, 0.35, 0.35, 1] if is_error else [0.3, 0.75, 0.45, 1]
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(20))
        layout.add_widget(Label(text=message, font_size='24sp', bold=True, color=theme_color))
        btn_close = SoftButton(text='ตกลง', bg_color=theme_color, size_hint_y=None, height=dp(60), radius=[15])
        layout.add_widget(btn_close)
        popup = Popup(title=title, title_font=APP_FONT, title_size='24sp', title_align='center',
                      content=layout, size_hint=(0.5, 0.4), separator_color=theme_color)
        btn_close.bind(on_release=popup.dismiss)
        popup.open()

    def save_settings(self):
        try:
            if hasattr(self, 'amount_editor'):
                updated_amounts = self.amount_editor.get_amounts_data()
                if updated_amounts:
                    APP_CONFIG["SELECT_AMOUNT"] = updated_amounts
            
            # บันทึกเฉพาะ System Config ไม่เรียก save_coin_state ซ้อน
            save_system_config()
            self.show_alert("สำเร็จ", "บันทึกยอดเงินเรียบร้อยแล้ว!")
        except Exception as e: 
            self.show_alert("ข้อผิดพลาด", f"การบันทึกล้มเหลว:\n{e}", is_error=True)

    def test_dispense(self, amount):
        coins = _calculate_coins_from_amount(str(amount))
        if coins > 0: c_gpio.start_dispensing(coins,"Workplace")

    def shutdown_system(self):
        App.get_running_app().stop()


class PasswordPopupContent(BoxLayout):
    ssid_name = StringProperty("")
    
    def __init__(self, ssid, confirm_callback, cancel_callback, **kwargs):
        super().__init__(**kwargs)
        self.ssid_name = ssid
        self.confirm_callback = confirm_callback
        self.cancel_callback = cancel_callback
        self.build_keyboard()
        
    def build_keyboard(self):
        chars = "1234567890qwertyuiopasdfghjklzxcvbnm@_+-"
        grid = self.ids.keyboard_grid
        grid.clear_widgets()
        
        for char in chars:
            btn = SoftButton(text=char, font_size='24sp', bg_color=[0.3, 0.4, 0.5, 1], radius=[10])
            btn.bind(on_release=lambda x: self.add_char(x.text)) 
            grid.add_widget(btn)
        
        btn_del = SoftButton(text="<-", font_size='24sp', bg_color=[0.9, 0.35, 0.35, 1], radius=[10])
        btn_del.bind(on_release=lambda x: self.del_char())
        grid.add_widget(btn_del)

        btn_upper = SoftButton(text="Shift", font_size='20sp', bg_color=[0.2, 0.6, 0.85, 1], radius=[10])
        btn_upper.bind(on_release=lambda x: self.toggle_upper(x))
        grid.add_widget(btn_upper)
    
    def add_char(self, char):
        self.ids.input_pass.text += char
        
    def del_char(self):
        self.ids.input_pass.text = self.ids.input_pass.text[:-1]

    def toggle_upper(self, btn):
        grid = self.ids.keyboard_grid
        is_upper = False
        
        for child in grid.children:
            if len(child.text) == 1 and child.text.isalpha():
                if child.text.islower():
                    child.text = child.text.upper()
                    is_upper = True
                else:
                    child.text = child.text.lower()
                    is_upper = False
                    
        if is_upper:
            btn.bg_color = [0.4, 0.75, 1.0, 1]
        else:
            btn.bg_color = [0.2, 0.6, 0.85, 1]
    
    def confirm(self, password):
        self.confirm_callback(self.ssid_name, password)
    
    def cancel(self):
        self.cancel_callback()

class WifiScreen(Screen):
    def on_enter(self):
        self.scan_wifi()
        
    def scan_wifi(self):
        self.ids.status_label.text = "กำลังสแกน..."
        self.ids.rv_wifi.data = []
        threading.Thread(target=self._scan_thread, daemon=True).start()
        
    def _scan_thread(self):
        try:
            cmd = ["sudo", "nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list", "--rescan", "yes"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                Clock.schedule_once(lambda dt: self.update_status(f"Scan Fail: {result.stderr}"))
                return

            lines = result.stdout.strip().split('\n')
            wifi_list = []
            seen = set()
            
            for line in lines:
                if not line.strip(): continue
                parts = line.rsplit(':', 1)
                if len(parts) < 2: continue
                
                ssid = parts[0].replace('\\:', ':') 
                signal = parts[1]
                
                if not ssid: continue
                if ssid not in seen:
                    seen.add(ssid)
                    wifi_list.append({'ssid': ssid, 'signal': signal})
            
            wifi_list.sort(key=lambda x: int(x['signal']) if x['signal'].isdigit() else 0, reverse=True)
            Clock.schedule_once(lambda dt: self.update_list(wifi_list))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_status(f"Error: {e}"))

    def update_list(self, wifi_list):
        self.ids.rv_wifi.data = wifi_list
        self.ids.status_label.text = f"พบ {len(wifi_list)} เครือข่าย"

    def update_status(self, text):
        self.ids.status_label.text = text

    def prompt_password(self, ssid):
        content = PasswordPopupContent(ssid, self.connect_wifi, self.dismiss_popup)
        self.popup = Popup(title="ใส่รหัสผ่าน Wi-Fi", content=content,
                           size_hint=(0.8, 0.8), auto_dismiss=False)
        self.popup.open()
        
    def dismiss_popup(self):
        if hasattr(self, 'popup'):
            self.popup.dismiss()

    def connect_wifi(self, ssid, password):
        self.dismiss_popup()
        self.ids.status_label.text = f"กำลังเชื่อมต่อ {ssid}..."
        threading.Thread(target=self._connect_thread, args=(ssid, password), daemon=True).start()
        
    def _connect_thread(self, ssid, password):
        try:
            cmd = ["sudo", "nmcli", "dev", "wifi", "connect", ssid, "password", password]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                Clock.schedule_once(lambda dt: self.update_status(f"เชื่อมต่อ {ssid} สำเร็จ!"))
                time.sleep(2)
                if check_internet_connection():
                    Clock.schedule_once(lambda dt: self.update_status(f"Internet OK"))
                else:
                    Clock.schedule_once(lambda dt: self.update_status(f"เชื่อมต่อแล้ว แต่ไม่มีเน็ต"))
            else:
                err = result.stderr.strip()
                msg = "รหัสผ่านผิด" if "Secrets were required" in err else "เชื่อมต่อไม่ได้"
                Clock.schedule_once(lambda dt: self.update_status(f"{msg} ({err[:20]}...)"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_status(f"Error: {str(e)}"))

class CoinMachineApp(App):
    SERAIL_ID = StringProperty(Config.SERAIL_ID)
    config = APP_CONFIG
    coin_stock = NumericProperty(0) 
    GET_IP = StringProperty(get_ip())
    APP_VERSION = StringProperty(APP_VERSION)
    
    last_transaction_ref = StringProperty("")
    last_transaction_amount = StringProperty("")
    
    # เพิ่มตัวแปรสถานะ เพื่อล็อคไม่ให้อ่านไฟล์ซ้อนทับกัน
    is_updating_stock = BooleanProperty(False)
    
    def build(self):
        load_config()
        global mqtt_client, c_gpio
        mqtt_client = setup_mqtt()
        if mqtt_client: mqtt_client.loop_start()
        
        c_gpio = coin_dispenser.CoinDispenserManager()

        from kivy.metrics import Metrics
        from kivy.core.window import Window

        def adjust_scale(instance, width, height):
            target_w, target_h = 1024.0, 600.0
            if width > 0 and height > 0:
                scale = min(width / target_w, height / target_h)
                Metrics.density = scale

        Window.bind(on_resize=adjust_scale)
        adjust_scale(Window, Window.width, Window.height)

        Builder.load_string(KV_CODE)
        sm = ScreenManager(transition=FadeTransition(duration=0.2))
        sm.add_widget(WelcomeScreen(name='welcome'))
        sm.add_widget(SelectAmountScreen(name='select_amount'))
        sm.add_widget(PaymentScreen(name='payment'))
        sm.add_widget(PointCollectionPromptScreen(name='point_prompt'))
        sm.add_widget(PhoneInputScreen(name='phone_input'))
        sm.add_widget(SuccessScreen(name='success'))
        sm.add_widget(ErrorScreen(name='error'))
        sm.add_widget(AdminLoginScreen(name='admin_login'))
        sm.add_widget(AdminDashboardScreen(name='admin_dashboard'))
        sm.add_widget(WifiScreen(name='wifi_settings'))
        
        Clock.schedule_interval(self.sync_stock_from_file, 1)

        return sm

    def sync_stock_from_file(self, dt):
        # ถ้า UI กำลังอัปเดตสต็อกอยู่ ให้ข้ามลูปนี้ไปก่อน เพื่อไม่ให้ดึงค่าเก่ามาทับ
        if self.is_updating_stock:
            return

        if os.path.exists(Config.COIN_STATE_FILE):
             try:
                 with open(Config.COIN_STATE_FILE, 'r') as f:
                     data = json.load(f)
                     self.coin_stock = data.get('coin_stock', 0)
                     app.coin_stock = data.get('coin_stock', 0)
             except: pass

    def logout(self):
        self.root.current = 'welcome'

    def on_stop(self):
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        if c_gpio:
            c_gpio.set_relay_state(False)
            if c_gpio.display: c_gpio.display.clear()
        
        if APP_CONFIG.get("auto_reboot", False):
            time.sleep(3)


if __name__ == '__main__':
    try:
        print("Starting Application")
        CoinMachineApp().run()
    except KeyboardInterrupt:
        print("Close By App")
    except Exception as e:
        print(f"Critical Error: {e}")
    finally:
        c_gpio.set_relay_state(False)
        if c_gpio.display:
            c_gpio.display.clear()

        print('Application has closed.')
        if APP_CONFIG.get("auto_reboot", False) == True:
            time.sleep(3)
            os.system("sudo reboot")
