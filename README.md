# 🪙 WashLover Coin Exchange Machine (Hybrid)

ระบบซอฟต์แวร์และฮาร์ดแวร์สำหรับควบคุม **ตู้แลกเหรียญอัตโนมัติ (Coin Exchange Machine)** ออกแบบมาเพื่อทำงานบน **Raspberry Pi 5** โดยเฉพาะ รองรับการรับธนบัตร, การชำระเงินผ่าน QR Code (PromptPay), ระบบสะสมคะแนนผ่านเบอร์โทรศัพท์, และมีหน้า Dashboard แบบ Web-based สำหรับจัดการหลังบ้าน

## 🌟 ฟีเจอร์หลัก (Key Features)
* **Kivy UI Kiosk:** หน้าจอ UI แบบสัมผัสสำหรับให้ลูกค้าทำรายการ แลกเหรียญ และกรอกเบอร์โทรศัพท์สะสมคะแนน
* **Hardware Integration:** ควบคุมอุปกรณ์ผ่าน GPIO 
  * เครื่องรับธนบัตร (Biller)
  * เครื่องจ่ายเหรียญ (Coin Dispenser / Hopper)
  * รีเลย์ควบคุมมอเตอร์พร้อมระบบเบรก (Hard Brake)
  * หน้าจอแสดงผล 7-Segment (TM1637)
* **Web Dashboard (Flask):** ระบบหลังบ้าน (SaaS Style) สำหรับมอนิเตอร์สถานะตู้ (CPU, RAM, Temp), ดูยอดขาย, สแกน WiFi, ตั้งค่าจำนวนเหรียญ และสั่งการ (Remote Commands)
* **MQTT Client:** รายงานสถานะเครื่องและรับคำสั่ง (Dispense, Reboot, Reset) แบบ Real-time ผ่านระบบ Cloud
* **Auto Update:** ระบบตรวจสอบและดาวน์โหลดอัปเดตไฟล์ซอร์สโค้ดอัตโนมัติ (OTA)

## 🖥️ ฮาร์ดแวร์ที่รองรับ (Hardware Requirements)
* Raspberry Pi 5 (OS: Debian Bookworm)
* หน้าจอ Touchscreen
* เครื่องรับธนบัตร (Pulse) -> เชื่อมต่อ `GPIO 25`
* เซนเซอร์เหรียญตกลง (Pulse) -> เชื่อมต่อ `GPIO 12`
* Relay ควบคุมมอเตอร์ (DRV8871) -> `GPIO 26` (IN1), `GPIO 21` (IN2)
* รีเลย์เปิด/ปิดไฟบิลเลอร์ -> `GPIO 13`
* หน้าจอ 7-Segment TM1637 -> `CLK: GPIO 2`, `DIO: GPIO 3`

## 📁 โครงสร้างโปรเจกต์ (Project Structure)
```text
/home/pi5/application/
├── app.py                     # Kivy Application (หน้าจอฝั่งลูกค้า)
├── api.py                     # Flask Web Server (หน้า Dashboard หลังบ้าน)
├── coin_dispenser.py          # สคริปต์หลักจัดการฮาร์ดแวร์ (Biller, Relay, Coin)
├── tm1637_display.py          # ไดรเวอร์สำหรับคุมจอ 7-Segment
├── install.sh                 # สคริปต์ติดตั้ง Dependencies & Auto Start Services
├── config.json                # ไฟล์ตั้งค่าระบบ (API Key, Network, UI)
├── config_coin.json           # ไฟล์เก็บสถานะการจ่ายเหรียญ (จำนวนคงเหลือ)
├── transactions.json          # ไฟล์เก็บประวัติการทำรายการ (Logs)
├── fonts/                     # โฟลเดอร์เก็บฟอนต์ (Mali-Bold.ttf)
└── images/                    # โฟลเดอร์เก็บรูปภาพประกอบ (duck.png ฯลฯ)

```
## 🚀 วิธีการติดตั้ง (Installation Guide)
 1. **Clone โปรเจกต์ลง Raspberry Pi 5**
   ต้องวางโปรเจกต์ไว้ที่ /home/pi5/application เท่านั้น (ตาม Path ที่ระบุไว้ในซอร์สโค้ด)
   ```bash
   cd /home/pi5
   git clone https://github.com/x-bosshub/application.git
   cd application
   
   ```
 2. **สลับระบบภาพเป็น X11 (สำคัญมากสำหรับ Raspberry Pi 5)**
   เนื่องจาก Kivy มีปัญหากับ Wayland ให้ทำการสลับไปใช้ X11
   * พิมพ์คำสั่ง sudo raspi-config
   * เลือก Advanced Options -> Wayland -> เลือก X11
   * Reboot เครื่อง 1 รอบ
 3. **รันสคริปต์ติดตั้งแบบอัตโนมัติ**
   สคริปต์จะทำการติดตั้ง Dependencies, สร้างโฟลเดอร์, ดาวน์โหลดฟอนต์, ให้สิทธิ์ไฟล์ และตั้งค่า Auto Start Service
   ```bash
   chmod +x install.sh
   sudo ./install.sh
   
   ```
## ⚙️ การทำงานของ Services (Systemd)
หลังติดตั้งเสร็จ ระบบจะรัน 2 Services อัตโนมัติ:
 * coin_app.service: ควบคุมหน้าจอ UI (app.py)
 * coin_api.service: ควบคุม Dashboard & Web API (api.py)
**คำสั่งตรวจสอบสถานะ:**
```bash
sudo systemctl status coin_app
sudo systemctl status coin_api

```
**คำสั่งดู Log แบบ Real-time:**
```bash
journalctl -u coin_app.service -f
journalctl -u coin_api.service -f

```
## 🌐 การเข้าใช้งาน Dashboard
เข้าดูสถานะของเครื่องหรือสั่งการได้ผ่าน Web Browser ของคอมพิวเตอร์หรือสมาร์ทโฟนที่อยู่ในวง LAN เดียวกัน
 * **URL:** http://<IP_ADDRESS_OF_PI>:5000
 * **รหัสผ่านเริ่มต้น:** 242424 (หรือตั้งค่าใน UI หน้าตู้)
*Developed & Maintained by BossHub Team*
```
