#!/bin/bash
# uninstall.sh
# Complete Uninstallation and cleanup for WashLover Coin Machine Hybrid on Raspberry Pi 5

echo "==============================================================="
echo "       Starting Complete Uninstallation for WashLover         "
echo "==============================================================="

APP_DIR="/home/pi5/application"

echo "1. Stopping active services..."
sudo systemctl stop coin_api.service 2>/dev/null
sudo systemctl stop coin_app.service 2>/dev/null

echo "2. Disabling services from autostart..."
sudo systemctl disable coin_api.service 2>/dev/null
sudo systemctl disable coin_app.service 2>/dev/null

echo "3. Removing systemd service files..."
sudo rm -f /etc/systemd/system/coin_api.service
sudo rm -f /etc/systemd/system/coin_app.service

echo "4. Reloading systemd daemon..."
sudo systemctl daemon-reload
sudo systemctl reset-failed

echo "5. Removing entire application directory..."
if [ -d "$APP_DIR" ]; then
    sudo rm -rf "$APP_DIR"
    echo "Directory $APP_DIR and all its contents have been completely removed."
else
    echo "Directory $APP_DIR does not exist."
fi

echo "6. Removing Ngrok and its repository lists..."
sudo apt-get remove --purge -y ngrok
sudo rm -f /etc/apt/sources.list.d/ngrok.list
sudo rm -f /etc/apt/trusted.gpg.d/ngrok.asc

echo "7. Removing installed Python & UI dependencies..."
# ถอนการติดตั้งเฉพาะแพ็กเกจที่เกี่ยวข้องกับโปรเจกต์ (เก็บ curl, git, network-manager ไว้เพราะจำเป็นต่อระบบ)
sudo apt-get remove --purge -y python3-kivy python3-sdl2 python3-pil python3-flask python3-requests python3-paho-mqtt python3-tz python3-rpi-lgpio python3-gpiozero

echo "8. Removing PIP packages..."
pip3 uninstall -y pytz --break-system-packages

echo "9. Cleaning up unused system packages..."
sudo apt-get autoremove -y
sudo apt-get clean

echo "==============================================================="
echo "       Complete Uninstallation Successfully Finished!          "
echo "       Everything related to the project has been removed.     "
echo "==============================================================="
