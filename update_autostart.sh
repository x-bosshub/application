#!/bin/bash
# curl -sSL http://141.98.19.190:4000/static/coin_machine/update_autostart.sh | sudo bash

echo "=========================================="
echo " Setup AutoStart Coin Machine System..."
echo "=========================================="

echo ">> Stopping and disabling services..."
sudo systemctl stop coin_machine_gui.service 2>/dev/null
sudo systemctl disable coin_machine_gui.service 2>/dev/null
sudo systemctl stop coin_machine.service 2>/dev/null
sudo systemctl disable coin_machine.service 2>/dev/null
sudo systemctl stop coin_app_watchdog.service 2>/dev/null
sudo systemctl disable coin_app_watchdog.service 2>/dev/null
sudo systemctl stop coin_api.service 2>/dev/null
sudo systemctl disable coin_api.service 2>/dev/null

# 2. Remove Systemd Service Files
echo ">> Removing service files..."
sudo rm -f /etc/systemd/system/coin_machine.service 
sudo rm -f /etc/systemd/system/coin_machine_gui.service
sudo rm -f /etc/systemd/system/coin_app_watchdog.service
sudo rm -f /etc/systemd/system/coin_api.service

# 3. Remove Old Autostart
echo ">> Removing autostart directory..."
if [ -d "/home/pi5/.config/autostart" ]; then
    sudo rm -r -f /home/pi5/.config/autostart/*
    echo "   [OK] /home/pi5/.config/autostart removed."
else
    echo "   [Skip] Directory not found."
fi

# ข้ามการลบ .Xauthority เพื่อป้องกัน Kivy Error หาจอไม่เจอ
# echo ">> Removing Xauthority directory..."
# if [ -d "/home/pi5/.Xauthority" ]; then
#     sudo rm -r -f /home/pi5/.Xauthority
#     echo "   [OK] /home/pi5/.Xauthority removed."
# else
#     echo "   [Skip] Directory not found."
# fi
# 4. Create New Systemd Service
echo ">> Creating new systemd service..."
sudo tee /etc/systemd/system/coin_machine.service > /dev/null <<EOF
[Unit]
Description=Coin Machine API Service
After=network.target multi-user.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi5/application
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi5/.Xauthority
ExecStart=/home/pi5/application/CoinMachine
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 5. Apply Permissions and Start Service
echo ">> Starting service..."
sudo chown -R root:root /home/pi5/application
sudo chmod -R 775 /home/pi5/application

sudo systemctl daemon-reload
sudo systemctl enable coin_machine.service
sudo systemctl start coin_machine.service

echo "=========================================="
echo " AutoStart Setup Complete."
echo "=========================================="
