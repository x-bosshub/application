#!/bin/bash
# curl -sSL http://141.98.19.190:4000/static/coin_machine_hybrid/download.sh | sudo bash

echo "=========================================="
echo " Downloading Coin Machine System..."
echo "=========================================="

# Configuration
JSON_URL="http://141.98.19.190:4000/api/coin_machine_hybrid"
LOCAL_VER_FILE="/home/pi5/application/version.json"

mkdir -p /home/pi5/application
mkdir -p /home/pi5/application/images
mkdir -p /home/pi5/application/fonts

sudo chown -R pi5:pi5 /home/pi5/application
sudo chown -R pi5:pi5 /home/pi5/application/images
sudo chown -R pi5:pi5 /home/pi5/application/fonts

sudo rm -f $LOCAL_VER_FILE

export DISPLAY=:0.0

python3 -c "
import sys, json, os, urllib.request

url = '$JSON_URL'
local_file = '$LOCAL_VER_FILE'

try:
    # 1. Get Server Version
    with urllib.request.urlopen(url, timeout=10) as response:
        server_data = json.loads(response.read().decode())
    
    server_ver = server_data.get('version', '0.0.0')
    
    # 2. Get Local Version
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

    # 3. Compare
    if server_ver == local_ver:
        print('\n>> System is already up to date. Exiting.')
        sys.exit(0)
    
    print('\n>> New version found. Updating...')

    # 4. Download Files
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

    # 5. Write new version file
    if success:
        with open(local_file, 'w') as f:
            json.dump({'version': server_ver}, f)
        print(f'\n>> Update Complete. Version is now {server_ver}')
        sys.exit(2) # Exit code 2 means update success (signal to reboot)
    else:
        print('\n>> Update Failed.')
        sys.exit(1)

except Exception as e:
    print(f'Critical Error: {e}')
    sys.exit(1)
"

# รับค่า Exit Code จาก Python
EXIT_CODE=$?

sudo chown -R root:root /home/pi5/application
sudo chown -R pi5:pi5 /home/pi5/application
sudo usermod -a -G gpio,dialout,video,render pi5
sudo chmod -R 777 /home/pi5/application

if [ $EXIT_CODE -eq 2 ]; then
    echo "Succesd"

elif [ $EXIT_CODE -eq 0 ]; then
    echo "Done."
else
    echo "Error occurred."
fi
