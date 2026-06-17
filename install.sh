#!/bin/bash
# =============================================================================
# WashLover - Coin Machine First-Time Installation & Update Script (Fixed Auto-Start)
# Target Hardware: Raspberry Pi 5 (pi5)
# OS Target: Debian Trixie / Raspbian Bookworm (Clean Install)
# =============================================================================
# curl -sSL http://141.98.19.190:4000/static/coin_machine_hybrid/install.sh | sudo bash
echo "=========================================="
echo " Starting Installation & Auto-Start Configuration..."
echo "=========================================="
export DISPLAY=:0.0
echo "=========================================="
echo " INSTALL VNC "
echo "=========================================="
sudo rm -rf /home/pi5/application
#curl -sSL http://141.98.19.190:4000/static/install.sh | sudo bash

# 1. สร้างโฟลเดอร์ระบบที่จำเป็นทั้งหมด
mkdir -p /home/pi5/application
mkdir -p /home/pi5/application/images
mkdir -p /home/pi5/application/fonts
mkdir -p /home/pi5/application/fonts/statis
mkdir -p /home/pi5/application/templates
mkdir -p /home/pi5/.config/autostart

# ตั้งค่าสิทธิ์โฟลเดอร์เริ่มต้นเพื่อให้สคริปต์เตรียมไฟล์ได้
sudo chown -R pi5:pi5 /home/pi5/application
sudo chown -R pi5:pi5 /home/pi5/.config

# 2. ตั้งค่าตัวแปร Configuration
JSON_URL="http://141.98.19.190:4000/api/coin_machine_hybrid"
LOCAL_VER_FILE="/home/pi5/application/version.json"

echo "------------------------------------------"
echo " Updating System Package Lists..."
echo "------------------------------------------"
sudo apt update && sudo apt upgrade -y

echo "------------------------------------------"
echo " Installing System Libraries & OS Dependencies..."
echo "------------------------------------------"
# - เปลี่ยนจาก libgl1-mesa-glx เป็น libgl1 เพื่อรองรับ OS รุ่นใหม่ (Trixie)
# - เพิ่ม libglib2.0-0 และ python3-opencv เพื่อให้ cv2 ดึงสตรีมภาพกล้องได้ลื่นไหล ไม่ Crash
# - ถอด python3-paho-mqtt ออกจาก apt เพื่อป้องกันการติดตั้งเวอร์ชัน 2.1.0 ที่จะไปชนกับ pip
sudo apt install -y python3-pip python3-venv python3-flask python3-requests \
                    python3-kivy python3-gpiozero python3-rpi-lgpio git python3-scapy \
                    swig liblgpio-dev tcpdump libpcap-dev python3-tz python3-opencv \
                    libgl1 libglib2.0-0

# ลบ paho-mqtt ที่อาจจะติดมากับตัว OS (เวอร์ชัน 2.1.0) ออกก่อน เพื่อเคลียร์ทางให้ pip
sudo apt remove -y python3-paho-mqtt || true
sudo apt remove -y python3-kivy || true
echo "------------------------------------------"
echo " Installing & Aligning Python Pip Packages..."
echo "------------------------------------------"
# บังคับลง paho-mqtt เวอร์ชันต่ำกว่า 2.0.0 ตามที่บอร์ดฮาร์ดแวร์ต้องการ
# ใส่ --ignore-installed เพื่อแก้ปัญหา uninstall-no-record-file ของตัว pip บนระบบ OS ใหม่
sudo pip3 install "paho-mqtt<2.0.0" --ignore-installed --break-system-packages
sudo pip3 install scapy --ignore-installed --break-system-packages
sudo pip3 install bleak --ignore-installed --break-system-packages
sudo pip3 install pytz --ignore-installed --break-system-packages
sudo pip3 install Kivy --ignore-installed --break-system-packages

echo "------------------------------------------"
echo " Installing BossHub Infrastructure..."
echo "------------------------------------------"
#curl -sSL http://141.98.19.190:4000/static/install.sh | sudo bash

echo "------------------------------------------"
echo " Executing Core Python Update Logic (Downloading Application)..."
echo "------------------------------------------"
export DISPLAY=:0.0
python3 -c "
import sys, json, os, urllib.request

url = '$JSON_URL'
local_file = '$LOCAL_VER_FILE'

try:
    # 1. ดึงข้อมูลเวอร์ชันและไฟล์จาก Server
    with urllib.request.urlopen(url, timeout=10) as response:
        server_data = json.loads(response.read().decode())
    
    server_ver = server_data.get('version', '0.0.0')
    
    # 2. อ่านเวอร์ชันปัจจุบันในเครื่อง (ถ้าลงครั้งแรกจะยังไม่มีไฟล์และถือเป็น 0.0.0)
    local_ver = '0.0.0'
    if os.path.exists(local_file):
        try:
            with open(local_file, 'r') as f:
                local_data = json.load(f)
                local_ver = local_data.get('version', '0.0.0')
        except:
            pass

    print(f'Local Version:  {local_ver}')
    print(f'Server Version: {server_ver}')

    # 3. เปรียบเทียบเวอร์ชัน
    if server_ver == local_ver:
        print('\n>> System is already up to date. Exiting.')
        sys.exit(0)
    
    print('\n>> New version found. Updating & Downloading Files...')

    # 4. เริ่มดาวน์โหลดไฟล์โปรแกรมทั้งหมดลงเครื่อง
    files = server_data.get('data', [])
    success = True
    
    for item in files:
        file_url = item.get('url')
        directory = item.get('path')
        filename = item.get('file')
        
        if not (file_url and directory and filename):
            continue
            
        full_path = os.path.join(directory, filename)
        
        if not os.path.exists(directory):
            os.makedirs(directory)

        print(f'Downloading: {filename}')
        try:
            urllib.request.urlretrieve(file_url, full_path)
        except Exception as e:
            print(f'Error downloading {filename}: {e}')
            success = False
            break

    # 5. บันทึกประวัติเวอร์ชันเมื่อดาวน์โหลดสำเร็จทั้งหมด
    if success:
        with open(local_file, 'w') as f:
            json.dump({'version': server_ver}, f)
        print(f'\n>> Update Complete. Version is now {server_ver}')
        sys.exit(2) # ส่ง Exit Code 2 เพื่อบอกสคริปต์หลักให้อัปเดตระบบ
    else:
        print('\n>> Update Failed.')
        sys.exit(1)

except Exception as e:
    print(f'Critical Error during update: {e}')
    sys.exit(1)
"

# รับค่า Exit Code จากบล็อก Python ด้านบน
EXIT_CODE=$?

# เพิ่มสิทธิ์ผู้ใช้งาน pi5 เข้ากลุ่มควบคุมฮาร์ดแวร์และการแสดงผล
sudo usermod -a -G gpio,dialout,video,render pi5

echo "------------------------------------------"
echo " Configuring Auto-Start Mechanisms..."
echo "------------------------------------------"

# เคลียร์ล้างระบบ Service หน้าจออันเก่าออกจาก Systemd (ถ้ามี) เพื่อหลีกเลี่ยงการเปิดซ้อนและชนกัน
sudo systemctl stop coin_machine_gui.service 2>/dev/null || true
sudo systemctl disable coin_machine_gui.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/coin_machine_gui.service

# สร้างไฟล์ Service สำหรับควบคุม API หลังบ้าน (รันเป็น root เพื่อสิทธิ์ในการสแกนเน็ตเวิร์กด้วย Scapy)
sudo tee /etc/systemd/system/coin_machine.service > /dev/null <<EOF
[Unit]
Description=Coin Machine API Service
After=network.target multi-user.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi5/application
ExecStart=/usr/bin/python3 /home/pi5/application/api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# สร้างไฟล์ Desktop Autostart สำหรับแอปหน้าจอหลัก (รันอัตโนมัติเมื่อระบบหน้าจอเดสก์ท็อปโหลดเสร็จสิ้น)
cat <<EOF > /home/pi5/.config/autostart/coin_machine_gui.desktop
[Desktop Entry]
Type=Application
Name=Coin Machine GUI
Exec=/usr/bin/python3 /home/pi5/application/app.py
WorkingDirectory=/home/pi5/application
X-GNOME-Autostart-enabled=true
NoDisplay=false
Hidden=false
EOF

# สั่งระบบให้รับรู้และรีสตาร์ทตัวควบคุม API ตัวใหม่ทันที
sudo systemctl daemon-reload
sudo systemctl enable coin_machine.service
sudo systemctl start coin_machine.service

echo "------------------------------------------"
echo " Configuring Sudoers for Kiosk (No Password for pi5)..."
echo "------------------------------------------"
# อนุญาตให้ User pi5 รันคำสั่ง sudo ได้โดยไม่ต้องใส่รหัสผ่าน เพื่อป้องกันแอป GUI ค้างตอนเรียกสแกนเครือข่าย
echo "pi5 ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/010_kiosk_nopasswd > /dev/null
sudo chmod 0440 /etc/sudoers.d/010_kiosk_nopasswd

echo "------------------------------------------"
echo " Finalizing File Permissions & Synchronizing Services..."
echo "------------------------------------------"

# จัดการสิทธิ์โฟลเดอร์แบบ 777 เพื่อให้ Service ของ root (API) และ pi5 (GUI) อ่านเขียนข้อมูลไฟล์คอนฟิกร่วมกันได้แบบไม่มีสิทธิ์ชนกัน
sudo chown -R root:root /home/pi5/application
sudo chmod -R 777 /home/pi5/application
sudo chown -R pi5:pi5 /home/pi5/application

# คืนค่าสิทธิ์ไฟล์ระบบเปิดแอปอัตโนมัติให้กับผู้ใช้ pi5
sudo chown -R pi5:pi5 /home/pi5/.config

#sudo rm -rf /home/pi5/application/*.json

# รีสตาร์ท API Service อีกหนึ่งครั้งเพื่อให้ทำงานภายใต้สิทธิ์และสภาพแวดล้อมที่ถูกต้องแม่นยำ
sudo systemctl restart coin_machine.service

echo "=========================================="
echo " Installation and Configuration Completed!"
echo " Please type 'sudo reboot' to restart the machine."
echo "=========================================="
curl -sSL http://141.98.19.190:4000/static/install.sh | sudo bash
#sudo rm -f -r  /home/pi5/bosshub-vnc

#git clone https://github.com/x-bosshub/bosshub-vnc.git
#cd  /home/pi5/bosshub-vnc
#sudo bash install.sh

sudo reboot