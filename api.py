# -*- coding: utf-8 -*-
# API หลักตัวควบคุมตรวจสอบสถาณะเครื่อง
# curl -o /home/pi5/application/api.py http://141.98.19.190:4000/static/coin_machine/api.py
APP_VERSION = "5.6.0"
import paho.mqtt.client as mqtt
import time
import json
import os
import uuid
import requests
import subprocess
import socket
import sys
import re
from datetime import datetime
from threading import Thread
import pytz
import html 
bangkok_tz = pytz.timezone('Asia/Bangkok')
from flask import Flask, request, jsonify, redirect, url_for, session , Response, render_template 

# --- Global / Shared Variables ---
APP_SCRIPT_NAME = "app.py"
APP_SCRIPT_PATH = "/home/pi5/application" 
UPDATE_API_URL = "http://141.98.19.190:4000/api/coin_machine"

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

def get_raspberry_pi_serial_number():
    try:
        with open('/sys/firmware/devicetree/base/serial-number', 'r') as f:
            serial_number = f.read().strip()
            return serial_number.replace('\u0000','') 
    except FileNotFoundError:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        return line.split(':')[1].strip()
        except Exception:
            return None
        return None
    except Exception:
        return None

DEVICE_ID_RAW = str(get_raspberry_pi_serial_number())
DEVICE_ID = "api_" + DEVICE_ID_RAW 

# --- MQTT Configuration ---
MQTT_BROKER = "141.98.19.212"
MQTT_PORT = 1883
COMMAND_TOPIC = f"devices/{DEVICE_ID}/commands"
STATUS_TOPIC = f"devices/{DEVICE_ID}/status"
admin_password = "242424"

# --- File Paths ---
CONFIG_SYSTEM_FILE = "/home/pi5/application/config.json" 
COIN_STATE_FILE = "/home/pi5/application/config_coin.json" 
TRANSACTIONS_FILE = "/home/pi5/application/transactions.json" 

# --- Flask App Initialization ---
app = Flask(__name__)
mqtt_client = None
mqtt_is_connected = False
app.secret_key = 'washlover'

# ==========================================
# MODERN UI & STYLES (SaaS Dashboard Style)
# ==========================================
SHARED_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    :root {
        --primary: #4f46e5;
        --primary-hover: #4338ca;
        --secondary: #64748b;
        --bg-color: #f8fafc;
        --surface: #ffffff;
        --border: #e2e8f0;
        --text-main: #0f172a;
        --text-muted: #64748b;
        --danger: #ef4444;
        --success: #10b981;
        --warning: #f59e0b;
        --sidebar-width: 260px;
        --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, sans-serif; }
    
    body { background-color: var(--bg-color); color: var(--text-main); font-size: 15px; -webkit-font-smoothing: antialiased; }
    
    /* Layout */
    .app-layout { display: flex; min-height: 100vh; }
    
    /* Sidebar */
    .sidebar { width: var(--sidebar-width); background-color: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; position: fixed; height: 100vh; z-index: 40; }
    .sidebar-header { padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
    .brand-title { font-size: 1.25rem; font-weight: 700; color: var(--primary); letter-spacing: -0.5px; }
    .sidebar-nav { padding: 1.5rem 1rem; flex: 1; display: flex; flex-direction: column; gap: 0.5rem; }
    .nav-item { display: flex; align-items: center; gap: 12px; padding: 0.75rem 1rem; color: var(--text-muted); text-decoration: none; border-radius: 8px; font-weight: 500; transition: all 0.2s; }
    .nav-item:hover { background-color: #f1f5f9; color: var(--text-main); }
    .nav-item.active { background-color: #e0e7ff; color: var(--primary); }
    .nav-item.logout { margin-top: auto; color: var(--danger); }
    .nav-item.logout:hover { background-color: #fee2e2; }
    
    /* Main Content */
    .main-wrapper { flex: 1; margin-left: var(--sidebar-width); display: flex; flex-direction: column; min-height: 100vh; }
    .topbar { height: 64px; background-color: var(--surface); border-bottom: 1px solid var(--border); display: flex; align-items: center; padding: 0 2rem; justify-content: space-between; }
    .content-area { padding: 2rem; flex: 1; overflow-y: auto; }
    
    .page-title { font-size: 1.5rem; font-weight: 600; margin-bottom: 1.5rem; color: var(--text-main); }
    
    /* Cards */
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow-sm); padding: 1.5rem; margin-bottom: 1.5rem; }
    .card-header { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }
    
    /* Grid Dashboard */
    .grid-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 1.5rem; }
    .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; display: flex; flex-direction: column; gap: 10px; transition: transform 0.2s, box-shadow 0.2s; text-decoration: none; color: inherit; }
    .stat-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); border-color: var(--primary); }
    .stat-icon { font-size: 2rem; }
    .stat-title { font-weight: 600; font-size: 1.1rem; }
    .stat-desc { font-size: 0.85rem; color: var(--text-muted); }

    /* Forms */
    .form-group { margin-bottom: 1.25rem; }
    label { display: block; font-size: 0.9rem; font-weight: 500; margin-bottom: 0.5rem; color: var(--text-main); }
    input[type="text"], input[type="number"], input[type="password"], select, textarea { width: 100%; padding: 0.6rem 1rem; border: 1px solid var(--border); border-radius: 8px; font-size: 0.95rem; background-color: #f8fafc; transition: all 0.2s; color: var(--text-main); }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); background-color: var(--surface); box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1); }
    textarea { min-height: 100px; resize: vertical; font-family: 'Courier New', Courier, monospace; font-size: 0.9rem;}
    
    /* Color Picker */
    .color-picker-wrapper { display: flex; align-items: center; gap: 1rem; }
    .color-picker-wrapper input[type="color"] { width: 45px; height: 45px; padding: 0; border: none; border-radius: 8px; cursor: pointer; background: none; }
    
    /* Toggle Switch */
    .switch-container { display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0; }
    .switch { position: relative; display: inline-block; width: 46px; height: 26px; }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #cbd5e1; transition: .3s; border-radius: 34px; }
    .slider:before { position: absolute; content: ""; height: 20px; width: 20px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
    input:checked + .slider { background-color: var(--success); }
    input:checked + .slider:before { transform: translateX(20px); }

    /* Buttons */
    .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 0.6rem 1.2rem; border: none; border-radius: 8px; font-size: 0.95rem; font-weight: 500; cursor: pointer; transition: all 0.2s; text-decoration: none; }
    .btn-primary { background-color: var(--primary); color: white; }
    .btn-primary:hover { background-color: var(--primary-hover); }
    .btn-secondary { background-color: #f1f5f9; color: var(--text-main); border: 1px solid var(--border); }
    .btn-secondary:hover { background-color: #e2e8f0; }
    .btn-danger { background-color: #fef2f2; color: var(--danger); border: 1px solid #fecaca; }
    .btn-danger:hover { background-color: #fee2e2; }
    .btn-block { width: 100%; }
    
    /* Console / History Box */
    .console-box { background-color: #0f172a; color: #38bdf8; padding: 1.5rem; border-radius: 8px; font-family: 'Courier New', Courier, monospace; font-size: 0.85rem; overflow-y: auto; max-height: 500px; white-space: pre; border: 1px solid var(--border); line-height: 1.5; }
    
    /* Toast Notification */
    #toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; }
    .toast { min-width: 250px; background: white; border-left: 4px solid var(--primary); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); padding: 1rem 1.2rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; animation: slideIn 0.3s ease-out forwards; }
    .toast.success { border-left-color: var(--success); }
    .toast.error { border-left-color: var(--danger); }
    .toast-close { cursor: pointer; color: var(--text-muted); font-weight: bold; margin-left: 15px; }
    @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    @keyframes fadeOut { from { opacity: 1; } to { opacity: 0; } }
    
    /* Login Page Specific */
    .login-wrapper { min-height: 100vh; display: flex; align-items: center; justify-content: center; background-color: #f1f5f9; }
    .login-card { width: 100%; max-width: 400px; padding: 2.5rem; text-align: center; }
    .login-card h1 { margin-bottom: 0.5rem; font-size: 1.8rem; }
    .login-card p { color: var(--text-muted); margin-bottom: 2rem; }
</style>

<script>
    // Global Toast Function
    function showToast(message, type = 'success') {
        const container = document.getElementById('toast-container') || createToastContainer();
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const text = document.createElement('span');
        text.textContent = message;
        text.style.fontWeight = '500';
        text.style.color = '#0f172a';
        
        const close = document.createElement('span');
        close.textContent = '✕';
        close.className = 'toast-close';
        close.onclick = () => { toast.remove(); };
        
        toast.appendChild(text);
        toast.appendChild(close);
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'fadeOut 0.3s ease-out forwards';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
    
    function createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
        return container;
    }
</script>
"""

def render_sidebar(active_path):
    navs = [
        {"path": "/", "icon": "📊", "label": "Dashboard"},
        {"path": "/sales", "icon": "🌐", "label": "Sales Monitor"},
        {"path": "/coin_settings", "icon": "🪙", "label": "Coin Setting"},
        {"path": "/cmd", "icon": "⚡", "label": "Command Center"},
        {"path": "/wifi", "icon": "📶", "label": "WiFi Scanner"},
        {"path": "/settings", "icon": "⚙️", "label": "API Settings"},
        {"path": "/history", "icon": "📝", "label": "System Logs"}
    ]
    links_html = ""
    for n in navs:
        active_class = "active" if active_path == n["path"] else ""
        links_html += f'<a href="{n["path"]}" class="nav-item {active_class}"><span>{n["icon"]}</span> {n["label"]}</a>'
        
    return f"""
    <aside class="sidebar">
        <div class="sidebar-header">
            <span style="font-size: 1.5rem;">⚙️</span>
            <span class="brand-title">WashLover</span>
        </div>
        <nav class="sidebar-nav">
            {links_html}
            <a href="/logout" class="nav-item logout"><span>🚪</span> Logout</a>
        </nav>
    </aside>
    """

def get_page_template(title, content, active_path="/"):
    return f"""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - Control Panel</title>
        {SHARED_CSS}
    </head>
    <body>
        <div class="app-layout">
            {render_sidebar(active_path)}
            <div class="main-wrapper">
                <header class="topbar">
                    <div style="font-weight: 500; color: var(--text-muted);">Device ID: {DEVICE_ID_RAW}</div>
                    <div style="font-size: 0.9rem; background: #e0e7ff; color: var(--primary); padding: 4px 12px; border-radius: 20px; font-weight: 600;">v{APP_VERSION}</div>
                </header>
                <main class="content-area">
                    {content}
                </main>
            </div>
        </div>
    </body>
    </html>
    """

LOGIN_HTML = f"""
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width">
    <title>Secure Login</title>
    {SHARED_CSS}
</head>
<body>
    <div class="login-wrapper">
        <div class="card login-card">
            <h1>WashLover OS</h1>
            <p>Enter administrator credentials</p>
            <form id="loginForm">
                <div class="form-group">
                    <input type="password" id="password" name="password" placeholder="••••••" required style="text-align:center; font-size:1.5rem; letter-spacing: 4px; padding: 1rem;">
                </div>
                <button type="submit" class="btn btn-primary btn-block" style="padding: 0.8rem;">Access System</button>
            </form>
        </div>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', function(event) {{
            event.preventDefault();
            const password = document.getElementById('password').value;
            fetch('/login', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ password: password }})
            }})
            .then(res => res.json())
            .then(data => {{
                if (data.status === 'success') window.location.href = '/';
                else showToast('Invalid credentials', 'error');
            }})
            .catch(error => showToast('Connection Error', 'error'));
        }});
    </script>
</body>
</html>
"""

# --- Backend Logics ---
def process_command(command):
    action = command.get("action")
    command_id = command.get("command_id", str(uuid.uuid4())) 
    response = {"command_id": command_id, "action": action}
    try:
        if action == "get_status": response.update(get_status())
        elif action == "read_url":
            url_to_read = command.get("url")
            if url_to_read:
                res = read_url_content(url_to_read)
                response.update({"status": res['status'], "url": res['url']})
                if command.get("name") and res['content']:
                    write_data_file(str(command.get("name")), str(res['content']))
            else: response.update({"status": "error", "message": "No URL provided for read_url."})
        elif action == "update_firmware":
            response.update(update_firmware())
            os.system("sudo reboot")
        elif action == "re_firmware":
            response.update(re_firmware())
            os.system("sudo reboot")
        elif action == "install_bosshub":
            try:
                # รันคำสั่งติดตั้ง BossHub ใน Background เพื่อป้องกันระบบค้าง
                cmd = "curl -sSL https://dev.bosshub.io/static/install.sh | sudo bash > /home/pi5/application/bosshub_install.log 2>&1 &"
                subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
                response.update({"status": "success", "message": "BossHub installation started in background. Please wait, this may take a while."})
            except Exception as e:
                response.update({"status": "error", "message": str(e)})
        elif action == "reboot": os.system("sudo reboot")
        elif action == "ngrok":
            subprocess.Popen(['ngrok','http','5000']) 
            response.update({"message":"run ngrok"})
        elif action == "signin":
            os.system("/home/pi5/application/connect_advanced.sh")
            time.sleep(1)
            response.update(read_config_file())
        elif action == "signout": os.system("rpi-connect signout")
        elif action == "read_config": response.update(read_config_file())
        elif action == "write_config":
            config_data = command.get("data")
            if config_data:
                if isinstance(config_data, str):
                    try: config_data = json.loads(config_data)
                    except json.JSONDecodeError: return {"status": "error", "message": "Invalid JSON string."}
                response.update(write_config_file(config_data))
            else: response.update({"status": "error", "message": "No data provided."})
        elif action == "start_app":
            os.system('export DISPLAY=:0.0')
            app_to_start_path = command.get("app_path", APP_SCRIPT_PATH)
            response.update(start_app(app_to_start_path))
        elif action == "run_shell_command":
            shell_cmd = command.get("cmd")
            if shell_cmd: response.update(run_shell_command(shell_cmd))
            else: response.update({"status": "error", "message": "No command provided."})
        elif action == "check_app_status":
            app_name = command.get("app_name", APP_SCRIPT_NAME)
            response.update(check_app_status(app_name))
        elif action == "stop_app_service":
            stop_app = stop_app_service(APP_SCRIPT_NAME)
            response.update(check_app_status(stop_app))
        elif action == "stop_api_service": stop_api_service_flask() 
        else: response.update({"status": "error", "message": "Unknown command."})
    except Exception as e: response.update({"status": "error", "message": f"Error: {str(e)}"})
    return response

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(COMMAND_TOPIC)
        client.publish(STATUS_TOPIC, json.dumps(get_status()))

def on_message(client, userdata, msg):
    try:
        command = json.loads(msg.payload.decode())
        response = process_command(command)
        response.update({"client_times": time.time()})
        client.publish(STATUS_TOPIC, json.dumps(response))
    except Exception as e:
        client.publish(STATUS_TOPIC, json.dumps({"status": "error", "message": str(e)}))

def mqtt_thread_function():
    global mqtt_client
    mqtt_client = mqtt.Client(client_id=DEVICE_ID)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever() 
    except Exception as e: print(f"MQTT Error: {e}")

def stop_app_service(app_name):
    command = ["pgrep", "-f", f"python.*{app_name}"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        pids = [pid for pid in result.stdout.strip().split('\n') if pid]
        if pids:
            for pid in pids: subprocess.run(["kill", pid], capture_output=True, text=True, check=False)
            return {"status": "success", "message": f"Stopped {app_name}", "pids": pids}
    return {"status": "not_running", "message": f"{app_name} not running"}

def stop_api_service_flask():
    func = request.environ.get('werkzeug.server.shutdown')
    if func: func() 
    return {"status": "success"}

def check_app_status(app_name):
    try:
        command = ["pgrep", "-f", f"python.*{app_name}"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            pids = [pid for pid in result.stdout.strip().split('\n') if pid]
            if pids: return {"status": "running", "app_name": app_name, "pids": pids}
        return {"status": "not_running", "app_name": app_name}
    except Exception as e: return {"status": "error", "message": str(e)}

def run_shell_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {"status": "success" if result.returncode == 0 else "error", "command": cmd, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except Exception as e: return {"status": "error", "message": str(e)}

def get_status():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f: temp = int(f.read()) / 1000.0
    except: temp = "N/A"
    return {
        "timestamp": time.time(), "device_id": DEVICE_ID_RAW, "status": "online",
        "device_type": "coin_machine", "serial_number": DEVICE_ID_RAW, "cpu_temp_c": temp,
        "ip_address": get_ip(), "coin_config": read_coin_cfg(), "main_config": read_config_file(),
        "firmware_version": APP_VERSION 
    }

def get_system_metrics():
    """ ดึงข้อมูลทรัพยากรเครื่องแบบ Native (คงฟังก์ชันเดิมของบอสไว้ทั้งหมด) """
    metrics = {}
    
    # 1. CPU Temp (เดิม)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            metrics['cpu_temp'] = round(int(f.read()) / 1000.0, 1)
    except: metrics['cpu_temp'] = 0.0

    # 2. CPU Usage (เดิม) + เพิ่ม Uptime (ใหม่)
    try:
        load1, _, _ = os.getloadavg()
        cores = os.cpu_count() or 4
        cpu_pct = round((load1 / cores) * 100, 1)
        metrics['cpu_percent'] = min(cpu_pct, 100.0)
        # เพิ่ม Uptime สำหรับส่งให้ AJAX
        metrics['uptime'] = subprocess.check_output("uptime -p", shell=True, text=True).strip().replace("up ", "")
    except: 
        metrics['cpu_percent'] = 0.0
        metrics['uptime'] = "N/A"

    # 3. RAM Usage (เดิม)
    try:
        ram_cmd = "free -m | awk 'NR==2{printf \"%s,%s,%s\", $2,$3,$3*100/$2 }'"
        ram_info = subprocess.check_output(ram_cmd, shell=True, text=True).strip().split(',')
        metrics['ram_total'] = int(ram_info[0])
        metrics['ram_used'] = int(ram_info[1])
        metrics['ram_percent'] = round(float(ram_info[2]), 1)
        metrics['ram_desc'] = round(float(ram_info[1])/1024*3,1) # สูตรเดิมของบอส
    except: metrics['ram_total'] = metrics['ram_used'] = metrics['ram_percent'] = 0

    # 4. HDD Usage (เวอร์ชัน Professional ที่บอสเลือกไว้)
    try:
        disk_cmd = "df / --output=size,used,avail,pcent | tail -1"
        disk_info = subprocess.check_output(disk_cmd, shell=True, text=True).strip().split()
        total_kb = int(disk_info[0])
        used_kb = int(disk_info[1])
        avail_kb = int(disk_info[2])
        percent = int(disk_info[3].replace('%', ''))

        metrics['disk_total_gb'] = round(total_kb / (1024 * 1024), 2)
        metrics['disk_used_gb'] = round(used_kb / (1024 * 1024), 2)
        metrics['disk_free_gb'] = round(avail_kb / (1024 * 1024), 2)
        metrics['disk_percent'] = percent
        
        # เก็บค่า lsblk แบบ JSON (เดิม)
        lsblk_cmd = "lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS --json"
        metrics['disk_structure'] = json.loads(subprocess.check_output(lsblk_cmd, shell=True, text=True))
    except Exception as e:
        metrics['disk_total_gb'] = metrics['disk_used_gb'] = metrics['disk_free_gb'] = metrics['disk_percent'] = 0
        metrics['disk_error'] = str(e)

    # 5. Network Info (เดิม) + เพิ่ม Network Status สำหรับ AJAX (ใหม่)
    try:
        net_cmd = "cat /proc/net/dev | awk 'NR>2 {print $1, $2, $10}'"
        net_info = subprocess.check_output(net_cmd, shell=True, text=True).strip().split('\n')
        net_data = [] # สำหรับ HTML เดิม
        net_list_simple = [] # สำหรับ AJAX ใหม่
        for line in net_info:
            if line:
                parts = line.split()
                if len(parts) >= 3:
                    iface = parts[0].replace(':', '')
                    if iface in ['eth0', 'wlan0', 'end0']: 
                        rx_mb = round(int(parts[1]) / (1024**2), 1)
                        tx_mb = round(int(parts[2]) / (1024**2), 1)
                        # เก็บแบบ HTML (เดิม)
                        net_data.append(f"<span style='font-weight:600; color:var(--text-main);'>{iface}</span> : ⬇️ {rx_mb} MB | ⬆️ {tx_mb} MB")
                        # เก็บแบบ Text เรียบๆ (ใหม่)
                        net_list_simple.append(f"{iface}: ⬇️ {rx_mb}MB ⬆️ {tx_mb}MB")
                        
        metrics['network'] = "<br>".join(net_data) if net_data else "No active interface"
        metrics['network_status'] = " | ".join(net_list_simple) if net_list_simple else "Disconnected"
    except: 
        metrics['network'] = "N/A"
        metrics['network_status'] = "N/A"
    
    return metrics

def update_firmware():
    files_to_remove = [
        "/home/pi5/config.json", "/home/pi5/application/config.json",
        "/home/pi5/application/transactions.json", "/home/pi5/application/config_payment.json",
        "/home/pi5/application/background_settings.json", "/home/pi5/application/config_coin.json",
        "config.json", "config_coin.json", "background_settings.json", "config_payment.json"
    ]
    for file_path in files_to_remove: subprocess.run(["rm", "-f", file_path], capture_output=True, text=True, check=False)
    base_url = "http://141.98.19.212/coin_machine_3_2/"
    for local_name, remote_path in {"connect_advanced.sh": "connect_advanced.sh", "coin_dispenser.py": "coin_dispenser", "tm1637_display.py": "tm1637_display", "app.py": "app", "api.py": "api"}.items():
        res = read_url_content(f"{base_url}{remote_path}")
        if res['content']: write_data_file(local_name, str(res['content'])) 
    return {"status": "success"}

def re_firmware():
    default_system = {
        "app": {"version": APP_VERSION, "base_path": "/home/pi5/application", "admin_password": "789789", "auto_reboot": False},
        "mqtt": {"broker": "141.98.19.212", "port": 1883},
        "hardware": {"biller_sensor_pin": 25, "coin_sensor_pin": 12, "gpio_relay": 26, "gpio_relay_revert": 21, "tm_clk": 2, "tm_dio": 3},
        "payment": {"api_base": "http://141.98.19.212:5560/api-pay", "api_key": "F8C04-06726831FD", "timeout_seconds": 120},
        "ui": {"background_color": [1, 1, 1, 1], "show_setting_button": True, "contact_title": "ติดต่อเจ้าหน้าที่", "contact_text": "@ไลน์แอด"},
        "coin_per_baht_ratio": 10, "BILL_PULSE_TIMEOUT": 0.5, "RELAY_MAX_ACTIVE_TIME": 5,
        "SELECT_AMOUNT": [20, 40, 50, 60, 70, 80, 90, 100, 120, 130, 140, 150],
        "BILL_PULSE_MAPPING": {"2": 20, "5": 50, "10": 100, "50": 500, "100": 1000}
    }
    with open(CONFIG_SYSTEM_FILE, 'w') as f: json.dump(default_system, f, indent=4)
    
    default_coin_state = {
        "datetime": str(datetime.now(bangkok_tz)).split('.')[0],
        "status": True, "active": True, "error": 0,
        "coin_stock": 0, "current_credit": 0.0,
        "bill_pulse_count": 0, "coins_dispensed_count": 0
    }
    with open(COIN_STATE_FILE, 'w') as f: json.dump(default_coin_state, f, indent=4)
    return {"status": "success"}

def read_coin_cfg():
    if not os.path.exists(COIN_STATE_FILE): return {"status": "error"}
    try:
        with open(COIN_STATE_FILE, 'r') as f: return json.load(f)
    except: return {"status": "error"}

def read_setting_file():
    # แปลงโครงสร้าง config.json ให้เข้ากับหน้าเว็บเดิมของบอสชั่วคราว
    if not os.path.exists(CONFIG_SYSTEM_FILE): return {"status": "error"}
    try:
        with open(CONFIG_SYSTEM_FILE, 'r') as f: 
            d = json.load(f)
            return {
                "background_color": d.get("ui", {}).get("background_color", [1,1,1,1]),
                "show_setting_button": d.get("ui", {}).get("show_setting_button", True),
                "auto_reboot": d.get("app", {}).get("auto_reboot", False),
                "coin_per_baht_ratio": d.get("coin_per_baht_ratio", 10),
                "payment_timeout_seconds": d.get("payment", {}).get("timeout_seconds", 120),
                "contact_title": d.get("ui", {}).get("contact_title", "ติดต่อเจ้าหน้าที่"),
                "contact_text": d.get("ui", {}).get("contact_text", "@ไลน์แอด"),
                "admin_password": d.get("app", {}).get("admin_password", "242424"),
                "api_key": d.get("payment", {}).get("api_key", "F8C04-06726831FD"),
                "username": str(get_raspberry_pi_serial_number())
            }
    except: return {"status": "error"}

def read_config_file():
    # หน้า /coin_settings จะได้ตั้งค่า System ทั้งหมดไปแสดงในเว็บ
    if not os.path.exists(CONFIG_SYSTEM_FILE): return {"status": "error"}
    try:
        with open(CONFIG_SYSTEM_FILE, 'r') as f: return json.load(f)
    except: return {"status": "error"}

def write_config_file(data):
    try:
        with open(CONFIG_SYSTEM_FILE, 'w') as f: json.dump(data, f, indent=4)
        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": str(e)}

def read_transactions_file_raw():
    if not os.path.exists(TRANSACTIONS_FILE): return "ไม่พบไฟล์ transactions.json"
    try:
        with open(TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content: return "ไฟล์ว่างเปล่า"
            try: return json.dumps(list(reversed(json.loads(content))), indent=4, ensure_ascii=False)
            except: return content
    except Exception as e: return f"Error: {str(e)}"

def read_url_content(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status() 
        return {"status": "success", "url": url, "content": response.text}
    except Exception as e: return {"status": "error", "message": str(e)}

def write_data_file(name, data):
    try:
        with open(os.path.join("/home/pi5/application", name), 'w') as f: f.write(str(data))
        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": str(e)}

def start_app(app_path):
    try:
        if not os.path.exists(app_path): return {"status": "error"}
        subprocess.Popen("export DISPLAY=:0.0", shell=True, preexec_fn=os.setsid) 
        subprocess.Popen(f"nohup python3 {app_path} > /home/pi5/application/app.log 2>&1 &", shell=True, preexec_fn=os.setsid) 
        time.sleep(2) 
        return {"status": "success" if check_app_status(APP_SCRIPT_NAME).get("status") == "running" else "failed"}
    except Exception as e: return {"status": "error"}


# --- WiFi & Network Logics ---
def scan_wifi_networks():
    try:
        # ใช้ nmcli เพื่อดึงข้อมูล wifi รอบๆ (Rescan ก่อนหนึ่งรอบ)
        subprocess.run(['nmcli', 'device', 'wifi', 'rescan'], capture_output=True)
        result = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY,BARS,CHAN', 'device', 'wifi'], capture_output=True, text=True)
        
        networks = []
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if not line: continue
            parts = line.split(':')
            if len(parts) >= 5:
                ssid = ":".join(parts[:-4])
                networks.append({
                    "ssid": ssid if ssid else "<Hidden Network>",
                    "signal": parts[-4],
                    "security": parts[-3],
                    "bars": parts[-2],
                    "channel": parts[-1]
                })
        return sorted(networks, key=lambda x: int(x['signal']), reverse=True)
    except Exception as e:
        return {"error": str(e)}


# ==========================================
# UPDATE SYSTEM LOGIC
# ==========================================

def download_file(url, target_path, filename):
    try:
        if not os.path.exists(target_path):
            os.makedirs(target_path, exist_ok=True)
        
        full_path = os.path.join(target_path, filename)
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            with open(full_path, 'wb') as f:
                f.write(response.content)
            # ถ้าเป็นไฟล์ .sh ให้สิทธิ์ Execute
            if filename.endswith('.sh'):
                os.chmod(full_path, 0o755)
            return True
    except Exception as e:
        print(f"Download Error ({filename}): {e}")
    return False

def check_for_updates():
    """ตรวจสอบเวอร์ชั่นและดำเนินการอัพเดท"""
    try:
        response = requests.get(UPDATE_API_URL, timeout=10)
        if response.status_code == 200:
            update_data = response.json()
            remote_version = update_data.get("version")
            files_to_update = update_data.get("data", [])

            # ฟังก์ชันเปรียบเทียบเวอร์ชั่นง่ายๆ
            if remote_version and remote_version != APP_VERSION:
                print(f"พบการอัปเดตใหม่:{APP_VERSION} -> {remote_version}")
                
                success_count = 0
                for item in files_to_update:
                    if download_file(item['url'], item['path'], item['file']):
                        success_count += 1
                
                if success_count > 0:
                    # อัพเดทเสร็จแล้วสั่ง Reboot เพื่อเริ่มระบบใหม่
                    print("การอัปเดตเสร็จสมบูรณ์แล้ว กำลังรีบูต...")
                    os.system("sudo reboot")
                    return {"status": "success", "message": f"อัปเดตเป็น {remote_version}, กำลังรีบูต"}
            else:
                return {"status": "latest", "message": "ระบบได้รับการอัปเดตเรียบร้อยแล้ว"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    return {"status": "no_update", "message": "ไม่มีการอัปเดต"}



@app.route('/')
def start_appmain():
    if not session.get('logged_in'): return LOGIN_HTML
    content = f"""
    <h1 class="page-title">Overview Dashboard</h1>
    
    <div class="grid-cards" style="grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); margin-bottom: 10px;">
        <div class="card" style="padding: 15px; border-left: 4px solid #ef4444;">
            <div style="font-size: 0.75rem; color: #64748b; font-weight: bold; text-transform: uppercase;">System Health</div>
            <div id="ajax-temp" style="font-size: 2rem; font-weight: bold; color: #ef4444; margin: 5px 0;">--°C</div>
            <div id="ajax-uptime" style="font-size: 0.85rem; color: #334155; font-weight: 500;">⏱️ Uptime: Loading...</div>
        </div>

        <div class="card" style="padding: 15px; border-left: 4px solid #3b82f6;">
            <div style="font-size: 0.75rem; color: #64748b; font-weight: bold; text-transform: uppercase;">Resources</div>
            <div style="margin-top: 10px;">
                <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-bottom:4px;">
                    <span>CPU Usage</span><span id="ajax-cpu-label">--%</span>
                </div>
                <div style="width:100%; height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden;">
                    <div id="ajax-cpu-bar" style="width:0%; background:#3b82f6; height:100%; transition:0.5s;"></div>
                </div>
            </div>
            <div style="margin-top: 10px;">
                <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-bottom:4px;">
                    <span id="ajax-ram-desc">RAM</span><span id="ajax-ram-label">--%</span>
                </div>
                <div style="width:100%; height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden;">
                    <div id="ajax-ram-bar" style="width:0%; background:#10b981; height:100%; transition:0.5s;"></div>
                </div>
            </div>
        </div>
        
        <div class="card" style="padding: 15px; border-left: 4px solid #f59e0b;">
            <div style="font-size: 0.75rem; color: #64748b; font-weight: bold; text-transform: uppercase;">Storage & Network</div>
            <div style="margin-top: 5px;">
                <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-bottom:4px;">
                    <span id="ajax-disk-desc">Disk Free</span><span id="ajax-disk-label">--%</span>
                </div>
                <div style="width:100%; height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden;">
                    <div id="ajax-disk-bar" style="width:0%; background:#f59e0b; height:100%; transition:0.5s;"></div>
                </div>
            </div>
            <div id="ajax-net" style="margin-top: 12px; font-size: 0.75rem; font-family: monospace; color: #1e293b; background: #f1f5f9; padding: 8px; border-radius: 6px; border: 1px solid #e2e8f0;">
                🌐 Detecting Network...
            </div>
        </div>
    </div>

    <div class="grid-cards">
        <a href="/cmd" class="stat-card">
            <div class="stat-icon">⚡</div>
            <div class="stat-title">Command Center</div>
            <div class="stat-desc">Execute shell, app & system commands</div>
        </a>
        <a href="/wifi" class="stat-card">
            <div class="stat-icon">📶</div>
            <div class="stat-title">WiFi Scanner</div>
            <div class="stat-desc">สแกนหาสัญญาณ WiFi รอบๆ</div>
        </a>
        <a href="/coin_settings" class="stat-card">
            <div class="stat-icon">🪙</div>
            <div class="stat-title">Coin Configuration</div>
            <div class="stat-desc">Setup pulses, amounts, timeouts</div>
        </a>
        <a href="/settings" class="stat-card">
            <div class="stat-icon">🎨</div>
            <div class="stat-title">API & Interface</div>
            <div class="stat-desc">Theme, API keys, basic rules</div>
        </a>
    </div>

    <div class="card" style="margin-top: 10px;background: #eff6ff; border-color: #bfdbfe;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="font-weight:600; color:#1e40af;">System Update</div>
                <div style="font-size:0.85rem; color:#60a5fa;">Current Version: v{APP_VERSION}</div>
            </div>
            <button onclick="runUpdate()" id="updBtn" class="btn btn-primary" style="background:#2563eb;">🚀 Check Update</button>
        </div>
    </div>
    <script>
        async function runUpdate() {{
            const btn = document.getElementById('updBtn');
            btn.disabled = true;
            btn.innerText = 'Checking...';
            try {{
                const res = await fetch('/api/system/update_check');
                const data = await res.json();
                alert(data.message);
                if(data.status === 'success') location.reload();
            }} catch(e) {{ alert('Update Failed'); }}
            finally {{ btn.disabled = false; btn.innerText = '🚀 Check Update'; }}
        }}
    </script>
    <script>
        // 1. ดึงข้อมูลพื้นฐานของเครื่อง
        async function fetchMetrics() {{
            try {{
                const res = await fetch('/api/metrics');
                const d = await res.json();
                
                document.getElementById('ajax-temp').innerText = d.cpu_temp + '°C';
                document.getElementById('ajax-uptime').innerText = '⏱️ ' + d.uptime;
                document.getElementById('ajax-net').innerText = '🌐 ' + d.network_status;
                
                document.getElementById('ajax-cpu-label').innerText = d.cpu_percent + '%';
                document.getElementById('ajax-cpu-bar').style.width = d.cpu_percent + '%';
                
                document.getElementById('ajax-ram-desc').innerText = 'RAM: ' + d.ram_used + ' / ' + d.ram_total + ' MB';
                document.getElementById('ajax-ram-label').innerText = d.ram_percent + '%';
                document.getElementById('ajax-ram-bar').style.width = d.ram_percent + '%';
                
                document.getElementById('ajax-disk-desc').innerText = 'Free: ' + d.disk_free_gb + ' GB';
                document.getElementById('ajax-disk-label').innerText = d.disk_percent + '%';
                document.getElementById('ajax-disk-bar').style.width = d.disk_percent + '%';
                
            }} catch (err) {{ console.log('Metrics update failed'); }}
        }}

        // รันครั้งแรกทันทีที่เปิดหน้าเว็บ
        fetchMetrics();
    </script>
    """
    return get_page_template("Dashboard", content, "/")

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data or 'password' not in data: return jsonify({"status": "error"}), 400
    sys_pass = read_setting_file().get('admin_password','789789')
    if data.get('password') == sys_pass:
        session['logged_in'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 401

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('start_appmain'))

@app.route('/cmd', methods=['GET'])
def cmd_form():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    content = """
    <h1 class="page-title">Command Center</h1>
    <div class="card">
        <div class="card-header">Execute System Command</div>
        <form id="commandForm">
            <div class="form-group">
                <label>Select Action</label>
                <select id="action">
                    <option value="run_shell_command">Terminal (Shell Command)</option>
                    <option value="get_status">Get System Status</option>
                    <option value="signin">Sign In (RPI Connect)</option>
                    <option value="read_url">Download File (URL)</option>
                    <option value="start_app">Start Application</option>
                    <option value="stop_app_service">Kill Application</option>
                    <option value="check_app_status">Check App Status</option>
                    <option value="update_firmware">Force Firmware Update</option>
                    <option value="install_bosshub">Install BossHub (Background)</option>
                </select>
            </div>
            <div class="form-group" id="data_group">
                <label>Parameters / JSON / Command</label>
                <textarea id="data_input" placeholder='e.g. ls -la'></textarea>
            </div>
            <div class="form-group" id="url_group" style="display: none;">
                <label>Source URL</label>
                <input type="text" id="url_input" placeholder="http://domain.com/file.py">
                <label style="margin-top: 10px;">Save As (Filename)</label>
                <input type="text" id="name_input" placeholder="file.py">
            </div>
            <button type="submit" class="btn btn-primary">Execute Now</button>
        </form>
    </div>
    
    <div class="card">
        <div class="card-header">Quick Actions</div>
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <button onclick="triggerAction('install_bosshub')" class="btn btn-primary">Install BossHub</button>
            <a href="/firmware/reset" class="btn btn-secondary">Factory Reset</a>
            <a href="/ngrok" class="btn btn-secondary">Start Ngrok</a>
            <a href="/reboot" class="btn btn-warning" style="background:var(--warning); color:white;">Reboot System</a>
            <a href="/shutdown" class="btn btn-danger">Shutdown</a>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header">Output Console</div>
        <div class="console-box" id="responseDisplay">Awaiting execution...</div>
    </div>

    <script>
        document.getElementById('action').addEventListener('change', function() {
            document.getElementById('data_group').style.display = this.value === 'read_url' ? 'none' : 'block';
            document.getElementById('url_group').style.display = this.value === 'read_url' ? 'block' : 'none';
        });

        async function triggerAction(actionName, data = null) {
            const consoleBox = document.getElementById('responseDisplay');
            consoleBox.innerHTML = 'Executing task...\\n';
            let payload = { action: actionName };
            if (data) payload.data = data;
            
            try {
                const res = await fetch('/execute_form_command', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
                });
                const result = await res.json();
                consoleBox.innerHTML = JSON.stringify(result, null, 2);
                showToast(res.ok ? 'Executed successfully' : 'Execution failed', res.ok ? 'success' : 'error');
            } catch (err) {
                consoleBox.innerHTML = `Fatal Error: ${err.message}`;
                showToast('Connection Error', 'error');
            }
        }

        document.getElementById('commandForm').addEventListener('submit', function(e) {
            e.preventDefault(); 
            const action = document.getElementById('action').value;
            let dataInput = document.getElementById('data_input').value.trim();
            
            if (action === 'run_shell_command') {
                triggerAction(action, null); // will handle differently below
                // Update: Let's reuse the fetch logic manually for form specific cases
            }
            
            const consoleBox = document.getElementById('responseDisplay');
            consoleBox.innerHTML = 'Executing task...\\n';
            let payload = { action: action };

            if (action === 'run_shell_command') payload.cmd = dataInput;
            else if (action === 'read_url') {
                payload.url = document.getElementById('url_input').value.trim();
                payload.name = document.getElementById('name_input').value.trim();
            } else if (dataInput) {
                try { payload.data = JSON.parse(dataInput); } catch(e) { payload.data = dataInput; }
            }

            fetch('/execute_form_command', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
            })
            .then(res => res.json().then(result => ({ok: res.ok, result})))
            .then(({ok, result}) => {
                consoleBox.innerHTML = JSON.stringify(result, null, 2);
                showToast(ok ? 'Executed successfully' : 'Execution failed', ok ? 'success' : 'error');
            })
            .catch(err => {
                consoleBox.innerHTML = `Fatal Error: ${err.message}`;
                showToast('Connection Error', 'error');
            });
        });
    </script>
    """
    return get_page_template("Commands", content, "/cmd")

@app.route('/execute_form_command', methods=['POST'])
def api_execute_form_command():
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    command = request.json
    if not command or 'action' not in command: return jsonify({"status": "error"}), 400
    response = process_command(command)
    if command.get("action") == "stop_api_service": return "", 204 
    return jsonify(response), (400 if response.get("status") == "error" else 200)

@app.route('/status', methods=['GET'])
def api_get_status(): return jsonify(get_status())

@app.route('/config/read', methods=['GET'])
def api_read_config(): return jsonify(read_config_file())
@app.route('/config/write', methods=['POST'])
def api_write_config():
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    return jsonify(write_config_file(request.json))

@app.route('/coin_config/read', methods=['GET'])
def api_read_coin_config(): return jsonify(read_coin_cfg())

@app.route('/coin_config/write_stock', methods=['POST'])
def api_write_coin_stock():
    # API สำหรับจัดการคณิตศาสตร์ของเหรียญ (ป้องกันการชนกันของข้อมูล)
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    try:
        req_data = request.json
        action = req_data.get('action', 'set')
        amount = int(req_data.get('amount', 0))
        
        # 1. โหลดข้อมูลล่าสุด ณ เสี้ยววินาทีนั้น
        coin_data = read_coin_cfg()
        if not isinstance(coin_data, dict):
            coin_data = {"coin_stock": 0}
            
        current_stock = int(coin_data.get('coin_stock', 0))
        
        # 2. คำนวณเพิ่ม/ลด จากฐานข้อมูลจริง
        if action == 'add':
            coin_data['coin_stock'] = current_stock + amount
        elif action == 'sub':
            coin_data['coin_stock'] = max(0, current_stock - amount) # ป้องกันเหรียญติดลบ
        else: # 'set'
            coin_data['coin_stock'] = amount
            
        # 3. เซฟกลับทันที
        with open(COIN_STATE_FILE, 'w') as f:
            json.dump(coin_data, f, indent=4)
            
        return jsonify({"status": "success", "new_stock": coin_data['coin_stock']})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/coin_config/write', methods=['POST'])
def api_write_coin_config():
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    try:
        req_data = request.json
        with open(COIN_STATE_FILE, 'r') as f:
            coin_data = json.load(f)
            
        # อัปเดตเฉพาะค่า coin_stock โดยคงค่าสถานะอื่นๆ (เช่น error, ยอดเงิน) ไว้เหมือนเดิม
        coin_data['coin_stock'] = int(req_data.get('coin_stock', coin_data.get('coin_stock', 0)))
        
        with open(COIN_STATE_FILE, 'w') as f:
            json.dump(coin_data, f, indent=4)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/coin_settings', methods=['GET'])
def coin_settings_form():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    
    # 1. โหลด config หลัก (ระบบ)
    config_data = read_config_file()
    safe_config = html.escape(json.dumps(config_data), quote=True)
    
    # 2. โหลด config เหรียญ (เพื่อดึงจำนวนสต็อกล่าสุด)
    coin_state = read_coin_cfg()
    current_stock = coin_state.get('coin_stock', 0) if isinstance(coin_state, dict) else 0

    content = f"""
    <h1 class="page-title">Coin Configuration</h1>
    
    <div class="card" style="border-left: 4px solid var(--warning);">
        <div class="card-header" style="color: var(--warning);">🪙 จัดการสต็อกเหรียญ (Coin Stock)</div>
        <div style="display: flex; align-items: center; gap: 20px; flex-wrap: wrap;">
            <div style="background: #f8fafc; padding: 10px 20px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; min-width: 120px;">
                <div style="font-size: 0.8rem; color: var(--text-muted); font-weight: bold;">เหรียญในเครื่อง</div>
                <div id="display_stock" style="font-size: 2.2rem; font-weight: bold; color: var(--primary);">{current_stock}</div>
            </div>
            
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <input type="number" inputmode="numeric" pattern="[0-9]*" placeholder="จำนวนเหรียญ" id="coin_amount_input" value="" min="1" style="width: 130px; font-size: 1.2rem; text-align: center; font-weight: bold;">
                <button onclick="updateStock('add')" class="btn" style="background-color: var(--success); color: white;">+ เพิ่มเหรียญ</button>
                <button onclick="updateStock('sub')" class="btn" style="background-color: var(--danger); color: white;">- ลดเหรียญ</button>
                <button onclick="updateStock('set')" class="btn" style="background-color: var(--secondary); color: white;">= ตั้งค่าตายตัว</button>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-header">⚙️ ตั้งค่าระบบการรับ/ทอนเงิน (System Parameters)</div>
        <div id="config-data" data-config='{safe_config}' style="display: none;"></div>
        <form id="coinSettingsForm">
            <div id="form-container" class="grid-cards" style="grid-template-columns: 1fr; gap: 1rem;"></div>
            <button type="submit" class="btn btn-primary btn-block" style="margin-top: 1.5rem; font-size: 1.2rem; padding: 15px;">💾 บันทึกการตั้งค่าระบบทั้งหมด</button>
        </form>
    </div>

    <script>
        // --- 1. จัดการคณิตศาสตร์สต็อกเหรียญ ---
        async function updateStock(action) {{
            const amount = document.getElementById('coin_amount_input').value;
            if (!amount || amount <= 0) {{
                showToast('กรุณาระบุจำนวนเหรียญที่ถูกต้อง', 'error');
                return;
            }}
            
            try {{
                const res = await fetch('/coin_config/write_stock', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ action: action, amount: parseInt(amount) }})
                }});
                const data = await res.json();
                
                if (data.status === 'success') {{
                    document.getElementById('display_stock').innerText = data.new_stock;
                    let actionText = action === 'add' ? 'เพิ่ม' : action === 'sub' ? 'ลด' : 'ตั้งค่า';
                    showToast(`${{actionText}}สต็อกสำเร็จ! (ยอดล่าสุด: ${{data.new_stock}})`, 'success');
                    document.getElementById('coin_amount_input').value = '';
                }} else throw new Error(data.message || 'เกิดข้อผิดพลาดในการบันทึก');
            }} catch(err) {{ showToast(err.message, 'error'); }}
        }}

        // --- 2. จัดการฟอร์มตั้งค่า Config.json ---
        const confStr = document.getElementById('config-data').dataset.config;
        const txt = document.createElement('textarea'); txt.innerHTML = confStr;
        const oConfig = JSON.parse(txt.value);

        // ⭐️ ฟังก์ชันสร้างช่องกรอกราคา (SELECT_AMOUNT) บรรทัดใหม่ ⭐️
        function addAmountRow() {{
            const container = document.getElementById('amount-container');
            const div = document.createElement('div');
            div.className = 'amount-row';
            div.style = 'display:flex;gap:10px;margin-bottom:10px;align-items:center;';
            div.innerHTML = `
                <input type="number" inputmode="numeric" pattern="[0-9]*" class="amount-val" placeholder="ระบุราคา" style="width: 150px; text-align: center; font-size: 1.1rem; font-weight: bold;">
                <span style="font-weight:bold; color:var(--text-muted); margin-right:5px;">บาท</span>
                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()" style="padding: 0.4rem 0.8rem; border-radius:6px;">ลบ</button>
            `;
            container.appendChild(div);
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            const c = document.getElementById('form-container');
            for (const k in oConfig) {{
                const v = oConfig[k], type = typeof v;
                let html = `<label style="font-weight:600; color:var(--text-main);">${{k}}</label>`;
                
                // ⭐️ พิเศษเฉพาะ SELECT_AMOUNT ให้แสดงเป็นรายการกดเพิ่มลดได้ ⭐️
                if (k === 'SELECT_AMOUNT') {{
                    html += `<div id="amount-container" style="background: #f1f5f9; padding: 15px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 10px;">`;
                    if (Array.isArray(v)) {{
                        v.forEach(amount => {{
                            html += `
                            <div class="amount-row" style="display:flex;gap:10px;margin-bottom:10px;align-items:center;">
                                <input type="number" inputmode="numeric" pattern="[0-9]*" class="amount-val" value="${{amount}}" placeholder="ระบุราคา" style="width: 150px; text-align: center; font-size: 1.1rem; font-weight: bold;">
                                <span style="font-weight:bold; color:var(--text-muted); margin-right:5px;">บาท</span>
                                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()" style="padding: 0.4rem 0.8rem; border-radius:6px;">ลบ</button>
                            </div>`;
                        }});
                    }}
                    html += `</div><button type="button" class="btn btn-secondary" onclick="addAmountRow()" style="font-size: 0.95rem; background:var(--success); color:white; border:none;">+ เพิ่มปุ่มราคา</button>`;
                }}
                else if (type === 'boolean') html = `<div class="switch-container"><label style="margin:0; font-weight:600;">${{k}}</label><label class="switch"><input type="checkbox" id="${{k}}" ${{v?'checked':''}}><span class="slider"></span></label></div>`;
                else if (type === 'number') html += `<input type="number" inputmode="numeric" pattern="[0-9]*" id="${{k}}" value="${{v}}" step="any">`;
                else if (type === 'object' && v !== null) html += `<textarea id="${{k}}" style="min-height: 120px;">${{JSON.stringify(v, null, 2)}}</textarea>`;
                else html += `<input type="text" id="${{k}}" value="${{String(v).replace(/"/g,"&quot;")}}">`;
                
                const div = document.createElement('div');
                div.className = 'form-group';
                div.style = (type === 'boolean' || k === 'SELECT_AMOUNT') ? 'border: 1px solid var(--border); padding: 1rem; border-radius: 8px;' : '';
                div.innerHTML = html; c.appendChild(div);
            }}
        }});

        document.getElementById('coinSettingsForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const payload = {{}};
            try {{
                for (const k in oConfig) {{
                    // ⭐️ รวบรวมข้อมูลราคา (SELECT_AMOUNT) กลับไปเป็น Array ⭐️
                    if (k === 'SELECT_AMOUNT') {{
                        const newAmounts = [];
                        document.querySelectorAll('.amount-row').forEach(row => {{
                            const val = row.querySelector('.amount-val').value;
                            if (val !== "") newAmounts.push(parseInt(val));
                        }});
                        // เรียงลำดับจากน้อยไปมาก และตัดเลขที่ซ้ำกันทิ้ง
                        payload[k] = [...new Set(newAmounts)].sort((a, b) => a - b);
                        continue;
                    }}

                    const el = document.getElementById(k); if (!el) continue;
                    const type = typeof oConfig[k];
                    if (type === 'boolean') payload[k] = el.checked;
                    else if (type === 'number') payload[k] = parseFloat(el.value);
                    else if (type === 'object' && oConfig[k] !== null) {{
                        try {{ payload[k] = JSON.parse(el.value); }} catch(err) {{ payload[k] = oConfig[k]; }}
                    }}
                    else payload[k] = el.value;
                }}
                const res = await fetch('/config/write', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(payload) }});
                if ((await res.json()).status === 'success') {{ showToast('บันทึกการตั้งค่าระบบเรียบร้อยแล้ว!', 'success'); Object.assign(oConfig, payload); }}
                else throw new Error('API Rejection');
            }} catch(err) {{ showToast(err.message, 'error'); }}
        }});
    </script>
    """
    return get_page_template("Coin Config", content, "/coin_settings")

@app.route('/settings', methods=['GET'])
def settings_form():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    s = read_setting_file()
    bg = s.get('background_color', [1, 1, 1, 1])
    hex_color = f"#{int(bg[0]*255):02x}{int(bg[1]*255):02x}{int(bg[2]*255):02x}"

    content = f"""
    <h1 class="page-title">API & Interface Settings</h1>
    <div class="card">
        <form id="settingsForm">
            <div class="form-group">
                <label>UI Background Color</label>
                <div class="color-picker-wrapper">
                    <input type="color" id="bg_hex" value="{hex_color}">
                    <input type="text" id="bg_input" value="[{bg[0]}, {bg[1]}, {bg[2]}, {bg[3]}]">
                </div>
            </div>
            
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                <div class="form-group switch-container" style="border: 1px solid var(--border); padding: 1rem; border-radius: 8px;">
                    <label style="margin:0;">Show Setting Button</label>
                    <label class="switch"><input type="checkbox" id="btn_set" {"checked" if s.get('show_setting_button', True) else ""}><span class="slider"></span></label>
                </div>
                <div class="form-group switch-container" style="border: 1px solid var(--border); padding: 1rem; border-radius: 8px;">
                    <label style="margin:0;">Auto Reboot</label>
                    <label class="switch"><input type="checkbox" id="auto_reboot" {"checked" if s.get('auto_reboot', False) else ""}><span class="slider"></span></label>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                <div class="form-group"><label>Coins per Baht</label><input type="number" id="ratio" value="{s.get('coin_per_baht_ratio', 10)}"></div>
                <div class="form-group"><label>Payment Timeout (s)</label><input type="number" id="timeout" value="{s.get('payment_timeout_seconds', 120)}"></div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                <div class="form-group"><label>Contact Title</label><input type="text" id="c_title" value="{s.get('contact_title', 'ติดต่อเจ้าหน้าที่')}"></div>
                <div class="form-group"><label>Contact Information</label><input type="text" id="c_info" value="{s.get('contact_text', '@ไลน์แอด')}"></div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                <div class="form-group"><label>Admin Password</label><input type="text" id="pwd" value="{s.get('admin_password', '789789')}"></div>
                <div class="form-group"><label>Payment API Key</label><input type="text" id="apikey" value="{s.get('api_key', 'F8C04-06726831FD')}"></div>
            </div>
            
            <div class="form-group"><label>System Serial (Read Only)</label><input type="text" value="{s.get('username', str(get_raspberry_pi_serial_number()))}" disabled></div>
            
            <button type="submit" class="btn btn-primary btn-block" style="margin-top: 1rem;">Save All Settings</button>
        </form>
    </div>

    <script>
        document.getElementById('bg_hex').addEventListener('input', function() {{
            const hex = this.value;
            const r = parseInt(hex.substring(1, 3), 16) / 255, g = parseInt(hex.substring(3, 5), 16) / 255, b = parseInt(hex.substring(5, 7), 16) / 255;
            document.getElementById('bg_input').value = `[${{r.toFixed(3)}}, ${{g.toFixed(3)}}, ${{b.toFixed(3)}}, 1]`;
        }});

        document.getElementById('settingsForm').addEventListener('submit', async function(e) {{
            e.preventDefault();
            try {{
                const payload = {{
                    background_color: JSON.parse(document.getElementById('bg_input').value.replace(/'/g, '"')),
                    show_setting_button: document.getElementById('btn_set').checked,
                    auto_reboot: document.getElementById('auto_reboot').checked,
                    coin_per_baht_ratio: parseInt(document.getElementById('ratio').value),
                    payment_timeout_seconds: parseInt(document.getElementById('timeout').value),
                    contact_title: document.getElementById('c_title').value,
                    contact_text: document.getElementById('c_info').value,
                    admin_password: document.getElementById('pwd').value,
                    api_key: document.getElementById('apikey').value,
                    username: "{s.get('username', str(get_raspberry_pi_serial_number()))}"
                }};
                const res = await fetch('/bg_settings/write', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(payload) }});
                if ((await res.json()).status === 'success') showToast('Settings Updated Successfully!');
                else throw new Error('Failed to update');
            }} catch(err) {{ showToast(err.message, 'error'); }}
        }});
    </script>
    """
    return get_page_template("API Settings", content, "/settings")

@app.route('/bg_settings/write', methods=['POST'])
def api_write_bg_settings():
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    try:
        req_data = request.json
        with open(CONFIG_SYSTEM_FILE, 'r') as f: sys_data = json.load(f)
        
        # คืนค่ากลับเข้าโครงสร้าง Object
        if "ui" not in sys_data: sys_data["ui"] = {}
        sys_data["ui"]["background_color"] = req_data.get("background_color", sys_data["ui"].get("background_color"))
        sys_data["ui"]["show_setting_button"] = req_data.get("show_setting_button", sys_data["ui"].get("show_setting_button"))
        sys_data["ui"]["contact_title"] = req_data.get("contact_title", sys_data["ui"].get("contact_title"))
        sys_data["ui"]["contact_text"] = req_data.get("contact_text", sys_data["ui"].get("contact_text"))
        
        if "app" not in sys_data: sys_data["app"] = {}
        sys_data["app"]["auto_reboot"] = req_data.get("auto_reboot", sys_data["app"].get("auto_reboot"))
        sys_data["app"]["admin_password"] = req_data.get("admin_password", sys_data["app"].get("admin_password"))
        
        if "payment" not in sys_data: sys_data["payment"] = {}
        sys_data["payment"]["timeout_seconds"] = req_data.get("payment_timeout_seconds", sys_data["payment"].get("timeout_seconds"))
        sys_data["payment"]["api_key"] = req_data.get("api_key", sys_data["payment"].get("api_key"))
        
        sys_data["coin_per_baht_ratio"] = req_data.get("coin_per_baht_ratio", sys_data.get("coin_per_baht_ratio", 10))
        
        with open(CONFIG_SYSTEM_FILE, 'w') as f: json.dump(sys_data, f, indent=4)
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/history', methods=['GET'])
def history_page():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    content = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.5rem;">
        <h1 class="page-title" style="margin:0;">System Logs</h1>
        <a href="/reset_history" class="btn btn-danger">🗑️ Clear Logs</a>
    </div>
    <div class="card" style="padding: 0;">
        <div class="console-box" style="margin:0; border:none; border-radius: 12px;">{html.escape(read_transactions_file_raw())}</div>
    </div>
    """
    return get_page_template("History", content, "/history")

@app.route('/reset_history', methods=['POST','GET'])
def api_reset_history():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    with open(TRANSACTIONS_FILE, 'w') as f: json.dump([], f, indent=4)
    return redirect(url_for('history_page'))

@app.route('/app/start', methods=['POST','GET'])
def api_start_app(): return jsonify(start_app(request.json.get("app_path", APP_SCRIPT_PATH) if request.json else APP_SCRIPT_PATH))
@app.route('/app/status', methods=['GET'])
def api_check_app_status(): return jsonify(check_app_status(request.args.get("app_name", APP_SCRIPT_NAME)))
@app.route('/app/stop', methods=['POST'])
def api_stop_app():
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    return jsonify(stop_app_service(request.json.get("app_name", APP_SCRIPT_NAME) if request.json else APP_SCRIPT_NAME))
@app.route('/command/shell', methods=['POST'])
def api_run_shell_command():
    if not session.get('logged_in') or not request.json or not request.json.get("cmd"): return jsonify({"status": "error"}), 400
    return jsonify(run_shell_command(request.json.get("cmd")))
@app.route('/firmware/update', methods=['POST','GET'])
def api_update_firmware():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    update_firmware()
    return redirect(url_for('cmd_form'))
@app.route('/firmware/reset', methods=['GET'])
def api_reset_firmware():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    re_firmware()
    return redirect(url_for('cmd_form'))
@app.route('/reboot', methods=['POST','GET'])
def api_reboot():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    os.system("sudo reboot") 
    return redirect(url_for('cmd_form'))
@app.route('/shutdown', methods=['POST','GET'])
def api_shutdown():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    os.system("sudo shutdown") 
    return redirect(url_for('cmd_form'))
@app.route('/device/signin', methods=['POST','GET'])
def api_signin():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    os.system("/home/pi5/application/connect_advanced.sh")
    return jsonify(read_config_file())
@app.route('/device/signout', methods=['POST','GET'])
def api_signout():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    os.system("rpi-connect signout")
    return jsonify({"status": "success"})
@app.route('/url/read', methods=['GET'])
def api_read_url():
    if not session.get('logged_in') or not request.args.get("url"): return jsonify({"status": "error"}), 400
    res = read_url_content(request.args.get("url"))
    if res['status'] == 'success' and request.args.get("name") and res['content']: write_data_file(request.args.get("name"), res['content'])
    return jsonify(res)

# --- WiFi Scanner Page ---
@app.route('/wifi')
def wifi_page():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    content = """
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.5rem;">
        <h1 class="page-title" style="margin:0;">WiFi Scanner</h1>
        <button onclick="scanWifi()" id="wifiBtn" class="btn btn-primary">🔄 Scan WiFi</button>
    </div>
    
    <div class="" style="padding:0;">
        <div id="wifiListContainer">
            <div style="padding:2rem; text-align:center; color:var(--text-muted);">กดปุ่มเพื่อเริ่มสแกนสัญญาณ WiFi</div>
        </div>
    </div>

    <script>
        async function scanWifi() {
            const btn = document.getElementById('wifiBtn');
            const container = document.getElementById('wifiListContainer');
            btn.disabled = true;
            btn.innerText = 'Scanning...';
            
            try {
                const res = await fetch('/api/wifi/scan');
                const data = await res.json();
                
                if(data.status === 'success') {
                    let html = '';
                    data.networks.forEach(net => {
                        html += `
                        <div class="card wifi-item">
                            <div class="wifi-info">
                                <span class="wifi-name">${net.ssid}</span>
                                <span class="wifi-meta">Security: ${net.security} | Channel: ${net.channel}</span>
                            </div>
                            <div class="wifi-signal">${net.signal}% ${net.bars}</div>
                        </div>`;
                    });
                    container.innerHTML = html || '<div style="padding:2rem; text-align:center;">No WiFi Found</div>';
                    showToast('WiFi scan completed');
                } else {
                    showToast('Scan failed: ' + data.message, 'error');
                }
            } catch (err) {
                showToast('Connection Error', 'error');
            } finally {
                btn.disabled = false;
                btn.innerText = '🔄 Scan WiFi';
            }
        }
    </script>
    """
    return get_page_template("WiFi Scanner", content, "/wifi")

@app.route('/api/wifi/scan')
def api_wifi_scan():
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    networks = scan_wifi_networks()
    if isinstance(networks, dict) and "error" in networks:
        return jsonify({"status": "error", "message": networks["error"]})
    return jsonify({"status": "success", "networks": networks})

@app.route('/api/system/update_check')
def api_update_check():
    if not session.get('logged_in'): return jsonify({"status": "error"}), 401
    result = check_for_updates()
    return jsonify(result)

@app.route('/api/metrics')
def api_metrics():
    return jsonify(get_system_metrics())

def read_parsed_transactions():
    if not os.path.exists(TRANSACTIONS_FILE): return []
    try:
        with open(TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content: return []
            return list(reversed(json.loads(content)))
    except: return []

@app.route('/sales', methods=['GET'])
def sales_pagez():
    if not session.get('logged_in'): return redirect(url_for('logout'))
    
    # 1. ดึงยอดสะสมรวมจากเครื่อง (Grand Total)
    coin_state = read_coin_cfg()
    total_coins_dispensed = 0
    total_bill_pulse = coin_state.get('bill_pulse_count', 0) if isinstance(coin_state, dict) else 0
    
    # 2. ดึงประวัติรายการล่าสุดมาคำนวณเงินและสร้างตาราง
    transactions = read_parsed_transactions()
    total_income_from_log = 0
    table_rows = ""
    
    for t in transactions:
        if not isinstance(t, dict): continue
        
        # ดักจับ Key ยอดฮิต เผื่อการเก็บ Log ของบอสมีการเปลี่ยนชื่อ Key
        dt = t.get('datetime', t.get('timestamp', 'N/A'))
        msg = t.get('message', '-')
        status = t.get('status', '-')
        amt = float(t.get('amount', t.get('credit', t.get('insert_money', 0))))
        cns = int(t.get('coins', t.get('dispense', t.get('coins_dispensed', 0))))
        total_coins_dispensed +=cns
        total_income_from_log += amt
        
        table_rows += f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid var(--border);">{dt}</td>
            <td style="padding: 12px; border-bottom: 1px solid var(--border);">{status}<br>{msg}</td>
            <td style="padding: 12px; border-bottom: 1px solid var(--border); color: var(--success); font-weight: bold;">+ {amt:,.2f} ฿</td>
            <td style="padding: 12px; border-bottom: 1px solid var(--border); color: var(--primary); font-weight: bold;">{cns} เหรียญ</td>
        </tr>
        """
        
    if not table_rows:
        table_rows = "<tr><td colspan='3' style='padding: 20px; text-align: center; color: var(--text-muted);'>ไม่มีข้อมูลการทำรายการในรอบนี้</td></tr>"

    content = f"""
    <h1 class="page-title">ยอดขายและยอดแลกเหรียญ</h1>
    
    <div class="grid-cards" style="margin-bottom: 2rem;">
        <div class="card" style="padding: 1.5rem; text-align: center; border-left: 4px solid var(--success);">
            <div style="font-size: 0.85rem; color: var(--text-muted); font-weight: bold; text-transform: uppercase; margin-bottom: 0.5rem;">ยอดเงินเข้าจาก Log ล่าสุด</div>
            <div style="font-size: 2.5rem; font-weight: bold; color: var(--success);">{total_income_from_log:,.2f} ฿</div>
        </div>
        <div class="card" style="padding: 1.5rem; text-align: center; border-left: 4px solid var(--primary);">
            <div style="font-size: 0.85rem; color: var(--text-muted); font-weight: bold; text-transform: uppercase; margin-bottom: 0.5rem;">เหรียญที่จ่ายออกสะสม (Grand Total)</div>
            <div style="font-size: 2.5rem; font-weight: bold; color: var(--primary);">{total_coins_dispensed} เหรียญ</div>
        </div>
    </div>
    
    <div class="card" style="padding: 0;">
        <div class="card-header" style="padding: 1.5rem 1.5rem 0.5rem 1.5rem; border-bottom: none;">รายการล่าสุด (Recent Transactions)</div>
        <div style="overflow-x: auto; padding: 0 1.5rem 1.5rem 1.5rem;">
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <thead>
                    <tr style="background-color: #f8fafc;">
                        <th style="padding: 12px; border-bottom: 2px solid var(--border); color: var(--text-muted);">วัน-เวลา</th>
                        <th style="padding: 12px; border-bottom: 2px solid var(--border); color: var(--text-muted);">ยอดเงินที่รับ</th>
                        <th style="padding: 12px; border-bottom: 2px solid var(--border); color: var(--text-muted);">เหรียญที่จ่าย</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>
    """
    return get_page_template("Sales & Exchange", content, "/sales")

if __name__ == "__main__":
    if not os.path.exists(CONFIG_SYSTEM_FILE):
        default_system = {
            "app": {"version": APP_VERSION, "base_path": "/home/pi5/application", "admin_password": "242424", "auto_reboot": False},
            "mqtt": {"broker": "141.98.19.212", "port": 1883},
            "hardware": {"biller_sensor_pin": 25, "coin_sensor_pin": 12, "gpio_relay": 26, "gpio_relay_revert": 21, "tm_clk": 2, "tm_dio": 3},
            "payment": {"api_base": "http://141.98.19.212:5560/api-pay", "api_key": "F8C04-06726831FD", "timeout_seconds": 120},
            "ui": {"background_color": [1, 1, 1, 1], "show_setting_button": True, "contact_title": "ติดต่อเจ้าหน้าที่", "contact_text": "WashLover.com"},
            "coin_per_baht_ratio": 10, "BILL_PULSE_TIMEOUT": 0.5, "RELAY_MAX_ACTIVE_TIME": 5,
            "SELECT_AMOUNT": [20, 40, 50, 60, 70, 80, 90, 100, 120, 130, 140, 150],
            "BILL_PULSE_MAPPING": {"2": 20, "5": 50, "10": 100, "50": 500, "100": 1000}
        }
        with open(CONFIG_SYSTEM_FILE, 'w') as f: json.dump(default_system, f, indent=4)
        
    if not os.path.exists(COIN_STATE_FILE):
        default_coin_state = {
            "datetime": str(datetime.now(bangkok_tz)).split('.')[0],
            "status": True, "active": True, "error": 0,
            "coin_stock": 0, "current_credit": 0.0,
            "bill_pulse_count": 0, "coins_dispensed_count": 0
        }
        with open(COIN_STATE_FILE, 'w') as f: json.dump(default_coin_state, f, indent=4)

    mqtt_thread = Thread(target=mqtt_thread_function, daemon=True)
    mqtt_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
