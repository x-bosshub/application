#!/bin/bash
# install.sh
# Complete Installation, Reinstall and Autostart setup for WashLover Coin Machine Hybrid on Raspberry Pi 5

echo "==============================================================="
echo "       Starting Installation/Reinstall for WashLover Coin Machine"
echo "==============================================================="

APP_DIR="/home/pi5/application"

echo "1. Updating system packages..."
sudo apt update -y

echo "2. Installing ngrok..."
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt install ngrok -y

echo "3. Installing System & Hardware Dependencies..."
# network-manager สำหรับสแกน WiFi, rpi-lgpio สำหรับแก้ปัญหา RPi.GPIO บน Pi 5
sudo apt install -y python3-pip network-manager curl git python3-rpi-lgpio python3-gpiozero

echo "4. Installing UI (Kivy & Images) Dependencies..."
# เพิ่ม python3-pil เพื่อให้ Kivy โหลดภาพ QR Code (AsyncImage) ได้สมบูรณ์
sudo apt install -y python3-kivy python3-sdl2 python3-pil

echo "5. Installing Python Libraries (Web & IoT)..."
# ใช้ apt สำหรับแพ็กเกจหลักเพื่อหลีกเลี่ยงข้อจำกัด PEP 668 บน Bookworm
sudo apt install -y python3-flask python3-requests python3-paho-mqtt python3-tz

# ติดตั้งแพ็กเกจเสริมผ่าน pip (ถ้าจำเป็น) โดยอนุญาตให้อนุโลมระบบ
sudo pip3 install pytz --break-system-packages

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

echo "9. Cleaning up previous Autostart configurations (Reinstall mode)..."
echo "Stopping and removing old services..."
sudo systemctl stop coin_app.service 2>/dev/null
sudo systemctl disable coin_app.service 2>/dev/null
sudo rm -f /etc/systemd/system/coin_app.service

sudo systemctl stop coin_api.service 2>/dev/null
sudo systemctl disable coin_api.service 2>/dev/null
sudo rm -f /etc/systemd/system/coin_api.service

sudo systemctl daemon-reload

echo "Removing old Autostart desktop files and scripts..."
sudo rm -f /home/pi5/.config/autostart/coin_app.desktop
sudo rm -f $APP_DIR/run_app.sh

echo "10. Creating Auto Start Services & Scripts..."

# ==========================================
# 10.1 Systemd Service for API (api.py)
# ==========================================
echo "Setting up Background Service for API..."
cat <<EOF | sudo tee /etc/systemd/system/coin_api.service > /dev/null
[Unit]
Description=WashLover Coin Machine API Service
After=network.target

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

# ==========================================
# 10.2 XDG Autostart & Loop Script for APP (app.py - Kivy UI)
# ==========================================
echo "Setting up Desktop Autostart for UI (Wayland/NoVNC compatible)..."

# 1. สร้างสคริปต์สแกนและรันแอปแบบวนลูป (Loop Runner)
cat << 'EOF' > $APP_DIR/run_app.sh
#!/bin/bash
# run_app.sh
# สคริปต์สำหรับรันและตรวจสอบสถานะแอป Kivy UI ของตู้แลกเหรียญ

cd /home/pi5/application

# วนลูปเปิดแอปตลอดเวลา ถ้าแอปปิดหรือแครช จะเปิดใหม่ใน 10
while true; do
    echo "Starting WashLover Coin Machine APP..."
    /usr/bin/python3 app.py
    echo "App crashed or closed. Restarting in 10 seconds..."
    sleep 10
done
EOF

# ตั้งสิทธิ์ให้สคริปต์รันได้
sudo chmod +x $APP_DIR/run_app.sh

# 2. สร้างไฟล์ Autostart ของระบบหน้าจอ (.desktop)
mkdir -p /home/pi5/.config/autostart
cat << EOF > /home/pi5/.config/autostart/coin_app.desktop
[Desktop Entry]
Type=Application
Name=WashLover Coin Machine APP
Exec=/home/pi5/application/run_app.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

# ป้องกันปัญหาไฟล์ติดสิทธิ์ Root ตอนติดตั้งผ่าน sudo
sudo chown -R pi5:pi5 /home/pi5/.config
sudo chown pi5:pi5 $APP_DIR/run_app.sh

echo "11. Enabling and Starting Services..."
sudo systemctl daemon-reload
sudo systemctl enable coin_api.service > /dev/null

# สั่งให้ Service API เริ่มทำงานทันที
sudo systemctl start coin_api.service > /dev/null

echo "==============================================================="
echo "       Installation & Auto Start Setup Completed!              "
echo "       API Service is running in the background.               "
echo "==============================================================="
echo "  ตรวจสอบสถานะ API: sudo systemctl status coin_api             "
echo "  ตรวจสอบสถานะ APP: แอป UI จะเด้งขึ้นมาอัตโนมัติเมื่อหน้าจอ Desktop โหลดเสร็จ"
echo "  *หมายเหตุ: โปรดแน่ใจว่าระบบแสดงผลอยู่ในโหมด Wayland (ค่าเริ่มต้น)"
echo "  เพื่อให้ NoVNC ใช้งานได้ตามปกติ"
echo "==============================================================="
