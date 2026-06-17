#!/bin/bash
# curl -sSL http://141.98.19.190:4000/static/coin_machine_hybrid/update.sh | sudo bash

echo "=========================================="
echo " Uninstalling Coin Machine System..."
echo "=========================================="

sudo systemctl stop coin_machine_gui.service 2>/dev/null
sudo systemctl disable coin_machine_gui.service 2>/dev/null
sudo systemctl stop coin_machine.service 2>/dev/null
sudo systemctl disable coin_machine.service 2>/dev/null
sudo systemctl stop coin_app_watchdog.service 2>/dev/null
sudo systemctl disable coin_app_watchdog.service 2>/dev/null
sudo systemctl stop coin_api.service 2>/dev/null
sudo systemctl disable coin_api.service 2>/dev/null

sudo rm -f /etc/systemd/system/coin_machine.service 
sudo rm -f /etc/systemd/system/coin_machine_gui.service
sudo rm -f /etc/systemd/system/coin_app_watchdog.service
sudo rm -f /etc/systemd/system/coin_api.service
sudo systemctl daemon-reload

if [ -d "/home/pi5/application" ]; then
    sudo rm -rf /home/pi5/application
fi

if [ -d "/home/pi5/Desktop/application" ]; then
    sudo rm -rf /home/pi5/Desktop/application
fi

if [ -d "/home/pi5/.config/autostart" ]; then
    sudo rm -rf /home/pi5/.config/autostart/*
fi

sudo apt autoremove -y

echo "=========================================="
echo " Uninstall Complete. Starting Update..."
echo "=========================================="

mkdir -p /home/pi5/application
mkdir -p /home/pi5/application/images
mkdir -p /home/pi5/application/fonts
mkdir -p /home/pi5/application/fonts/statis
mkdir -p /home/pi5/application/templates
mkdir -p /home/pi5/.config/autostart

sudo chown -R pi5:pi5 /home/pi5/application
sudo chown -R pi5:pi5 /home/pi5/.config

JSON_URL="http://141.98.19.190:4000/api/coin_machine_hybrid"
LOCAL_VER_FILE="/home/pi5/application/version.json"

sudo rm -f $LOCAL_VER_FILE

sudo apt update -y
sudo apt upgrade -y

sudo apt install -y python3-pip python3-venv python3-flask python3-requests \
                    python3-kivy python3-gpiozero python3-rpi-lgpio git python3-scapy \
                    swig liblgpio-dev tcpdump libpcap-dev python3-tz python3-opencv \
                    libgl1 libglib2.0-0

sudo apt remove -y python3-paho-mqtt || true

sudo pip3 install "paho-mqtt<2.0.0" --ignore-installed --break-system-packages
sudo pip3 install scapy --ignore-installed --break-system-packages
sudo pip3 install bleak --ignore-installed --break-system-packages
sudo pip3 install pytz --ignore-installed --break-system-packages

curl -sSL http://141.98.19.190:4000/static/install.sh | sudo bash

export DISPLAY=:0.0

python3 -c "
import sys, json, os, urllib.request

url = '$JSON_URL'
local_file = '$LOCAL_VER_FILE'

try:
    with urllib.request.urlopen(url, timeout=10) as response:
        server_data = json.loads(response.read().decode())
    server_ver = server_data.get('version', '0.0.0')
    
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

    if server_ver == local_ver:
        sys.exit(0)
    
    files = server_data.get('data', [])
    success = True
    for item in files:
        file_url = item.get('url')
        directory = item.get('path')
        filename = item.get('file')
        if not (file_url and directory and filename): continue
        full_path = os.path.join(directory, filename)
        if not os.path.exists(directory): os.makedirs(directory)
        print(f'Downloading: {filename}')
        try:
            urllib.request.urlretrieve(file_url, full_path)
        except Exception as e:
            print(f'Error downloading {filename}: {e}')
            success = False
            break

    if success:
        with open(local_file, 'w') as f: json.dump({'version': server_ver}, f)
        sys.exit(2)
    else:
        sys.exit(1)
except Exception as e:
    print(f'Critical Error: {e}')
    sys.exit(1)
"

EXIT_CODE=$?

sudo usermod -a -G gpio,dialout,video,render pi5

if [ $EXIT_CODE -eq 2 ]; then

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

    sudo systemctl daemon-reload
    sudo systemctl enable coin_machine.service
    sudo systemctl start coin_machine.service

    sleep 3
fi

if [ $EXIT_CODE -eq 2 ] || [ $EXIT_CODE -eq 0 ]; then
    sleep 3
    
    sudo chown -R root:root /home/pi5/application
    sudo chmod -R 777 /home/pi5/application
    sudo chown -R pi5:pi5 /home/pi5/.config

    sudo systemctl restart coin_machine.service 
    sudo systemctl restart ttyd.service novnc.service frpc bosshub-heartbeat.service 2>/dev/null || true
    
    pkill -f "python3 /home/pi5/application/app.py" || true
    export DISPLAY=:0.0
    nohup python3 /home/pi5/application/app.py > /dev/null 2>&1 &
    
    echo "=========================================="
    echo " Update Applied Successfully."
    echo "=========================================="
else
    echo "=========================================="
    echo " Update Error Occurred."
    echo "=========================================="
fi
