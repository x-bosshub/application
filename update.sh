#!/bin/bash
# update.sh
# Application Update Script for WashLover Coin Machine Hybrid on Raspberry Pi 5

echo "==============================================================="
echo "       Starting Update for WashLover Coin Machine              "
echo "==============================================================="

APP_DIR="/home/pi5/application"

echo "1. Stopping active services..."
sudo systemctl stop coin_api.service 2>/dev/null
sudo systemctl stop coin_app.service 2>/dev/null

echo "2. Updating application source code..."
# ตรวจสอบว่าใช้งานระบบ Git หรือไม่
if [ -d "$APP_DIR/.git" ]; then
    echo "Git repository detected. Pulling latest changes from remote..."
    cd $APP_DIR
    # ดึงโค้ดล่าสุดจาก Branch ปัจจุบัน
    git pull
else
    echo "Notice: No Git repository found in $APP_DIR."
    echo "Skipping Git pull. (If you update files manually via FTP/SFTP, make sure they are in place)."
fi

echo "3. Updating directory permissions..."
sudo chmod -R 777 $APP_DIR

echo "4. Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "5. Starting services..."
sudo systemctl start coin_api.service
sudo systemctl start coin_app.service

echo "==============================================================="
echo "       Update Completed Successfully!                          "
echo "       Services 'coin_api' and 'coin_app' are running.         "
echo "==============================================================="
echo "  ตรวจสอบสถานะ API: sudo systemctl status coin_api             "
echo "  ตรวจสอบสถานะ APP: sudo systemctl status coin_app             "
echo "==============================================================="
