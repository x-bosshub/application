#!/bin/bash
# install.sh
# Installation and Autostart setup for WashLover Coin Machine Hybrid on Raspberry Pi 5

echo "==============================================================="
echo "       Starting Installation for WashLover Coin Machine        "
echo "==============================================================="

APP_DIR="/home/pi5/application"

echo "1. Updating system packages..."
sudo apt update -y

echo "2. Installing ngrok..."
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok -y

echo "3. Installing System & Hardware Dependencies..."
# network-manager สำหรับสแกน WiFi, rpi-lgpio สำหรับแก้ปัญหา RPi.GPIO บน Pi 5
sudo apt install -y python3-pip network-manager curl git python3-rpi-lgpio python3-gpiozero

echo "4. Installing UI (Kivy) Dependencies..."
sudo apt install -y python3-kivy python3-sdl2 

echo "5. Installing Python Libraries (Web & IoT)..."
# ใช้ apt สำหรับแพ็กเกจหลักเพื่อหลีกเลี่ยงข้อจำกัด PEP 668 บน Bookworm
sudo apt install -y python3-flask python3-requests python3-paho-mqtt python3-tz

# ติดตั้งแพ็กเกจเสริมผ่าน pip (ถ้าจำเป็น) โดยอนุญาตให้อนุโลมระบบ
pip3 install pytz --break-system-packages

echo "6. Creating necessary directories..."
mkdir -p $APP_DIR/fonts
mkdir -p $APP_DIR/images
mkdir -p $APP_DIR/templates

echo "7. Downloading required assets (Fonts & Images)..."
# ดาวน์โหลดฟอนต์ Mali-Bold.ttf อัตโนมัติหากยังไม่มีในระบบ
if [ ! -f "$APP_DIR/fonts/Mali-Bold.ttf" ]; then
    echo "Downloading Mali-Bold.ttf..."
    curl -o $APP_DIR/fonts/Mali-Bold.ttf -L "https://github.com/cadsondemak/Mali/raw/master/fonts/ttf/Mali-Bold.ttf"
else
    echo "Font Mali-Bold.ttf already exists."
fi

# ตรวจสอบภาพเป็ด duck.png
if [ ! -f "$APP_DIR/images/duck.png" ]; then
    echo "Notice: Please ensure 'duck.png' is placed in $APP_DIR/images/"
fi

echo "8. Setting up Permissions (chmod 777)..."
sudo chmod -R 777 $APP_DIR

echo "9. Creating Systemd Services for Auto Start..."

# ==========================================
# 9.1 Service for API (api.py)
# ==========================================
cat <<EOF | sudo tee /etc/systemd/system/coin_api.service > /dev/null
[Unit]
Description=WashLover Coin Machine API Service
After=network.target

[Service]
Type=simple
User=pi5
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ==========================================
# 9.2 Service for APP (app.py - Kivy UI)
# ==========================================
cat <<EOF | sudo tee /etc/systemd/system/coin_app.service > /dev/null
[Unit]
Description=WashLover Coin Machine UI Service
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=pi5
WorkingDirectory=$APP_DIR
Environment=DISPLAY=:0.0
Environment=XAUTHORITY=/home/pi5/.Xauthority
ExecStart=/usr/bin/python3 $APP_DIR/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

echo "10. Enabling and Starting Services..."
sudo systemctl daemon-reload
sudo systemctl enable coin_api.service
sudo systemctl enable coin_app.service

# สั่งให้ Service เริ่มทำงานทันที
sudo systemctl restart coin_api.service
sudo systemctl restart coin_app.service

echo "==============================================================="
echo "       Installation & Auto Start Setup Completed!              "
echo "       Services 'coin_api' and 'coin_app' are running.         "
echo "==============================================================="
echo "  ตรวจสอบสถานะ API: sudo systemctl status coin_api             "
echo "  ตรวจสอบสถานะ APP: sudo systemctl status coin_app             "
echo "  *หมายเหตุ: หาก Kivy UI ไม่ขึ้นจอ โปรดตรวจสอบให้แน่ใจว่า        "
echo "  ได้ใช้ sudo raspi-config ปรับ Display เป็น X11 เรียบร้อยแล้ว     "
echo "==============================================================="
