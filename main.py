# -*- coding: utf-8 -*-
# /home/pi5/application/main.py
import threading
import time
import os
import sys
 
# ให้แน่ใจว่าระบบมองเห็นพาธของโฟลเดอร์ปัจจุบัน
sys.path.append('/home/pi5/application')

def run_api():
    from api import app as flask_app
    # รัน Flask ปิด debug และ reloader เพื่อไม่ให้ชนกับ thread หลักเวลา build เป็น exe
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_gui():
    from app import CoinMachineApp
    os.environ['DISPLAY'] = '0:0'
    CoinMachineApp().run()

if __name__ == "__main__":
    print("Starting WashLover Coin Machine (Compiled Version)...")
    
    # รัน API เป็น Background Thread
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    
    time.sleep(2) # รอ API สตาร์ทแป๊บเดียว
    
    # รัน Kivy GUI ใน Main Thread
    run_gui()
