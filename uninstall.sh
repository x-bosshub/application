#!/bin/bash
# uninstall.sh
# Complete Uninstallation and Service removal for WashLover Coin Machine Hybrid on Raspberry Pi 5

echo "==============================================================="
echo "       Starting Uninstallation for WashLover Coin Machine     "
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

echo "5. Removing downloaded assets..."
if [ -f "$APP_DIR/fonts/Mali-Bold.ttf" ]; then
    echo "Removing Mali-Bold.ttf..."
    rm -f "$APP_DIR/fonts/Mali-Bold.ttf"
else
    echo "No downloaded font assets found."
fi

echo "==============================================================="
echo "       Uninstallation Completed Successfully!                  "
echo "       Services 'coin_api' and 'coin_app' have been removed.   "
echo "==============================================================="
