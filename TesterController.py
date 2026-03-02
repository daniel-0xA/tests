import asyncio
import csv
import json
import time
from datetime import datetime
from bleak import BleakClient, BleakScanner

# UUIDs from your ESP-IDF Table
CMD_UUID    = "0000ff01-0000-1000-8000-00805f9b34fb"
STATUS_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
DATA_UUID   = "0000ff03-0000-1000-8000-00805f9b34fb"

class AutoTester:
    def __init__(self):
        self.logs = []
        self.final_status = "UNKNOWN"
        self.start_time = None

    def log_handler(self, sender, data):
        msg = data.decode('utf-8', errors='ignore').strip()
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {msg}")
        self.logs.append({"time": timestamp, "message": msg})

    def status_handler(self, sender, data):
        self.final_status = "PASS" if data[0] == 0x01 else "FAIL"
        print(f"\n>>> TEST FINISHED: {self.final_status} <<<")

    async def save_reports(self):
        filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 1. Save Detailed CSV Log
        with open(f"{filename}.csv", 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["time", "message"])
            writer.writeheader()
            writer.writerows(self.logs)
        
        # 2. Save Summary JSON Report
        summary = {
            "test_date": datetime.now().isoformat(),
            "duration_sec": round(time.time() - self.start_time, 2),
            "result": self.final_status,
            "log_count": len(self.logs)
        }
        with open(f"{filename}.json", 'w') as f:
            json.dump(summary, f, indent=4)
        
        print(f"Reports saved: {filename}.csv and .json")

    async def run(self):
        device = await BleakScanner.find_device_by_name("ESP_AUTO_TESTER")
        if not device:
            print("Tester not found!")
            return

        async with BleakClient(device) as client:
            print(f"Connected to {device.name} ({device.address})")
            self.start_time = time.time()

            # Subscribe to Status and Data
            await client.start_notify(STATUS_UUID, self.status_handler)
            await client.start_notify(DATA_UUID, self.log_handler)

            # Trigger Test
            await client.write_gatt_char(CMD_UUID, bytearray([0x01]))

            # Wait for result or timeout (e.g., 30 seconds)
            timeout = 30
            while self.final_status == "UNKNOWN" and (time.time() - self.start_time) < timeout:
                await asyncio.sleep(0.5)

            await self.save_reports()

if __name__ == "__main__":
    tester = AutoTester()
    asyncio.run(tester.run())

# Why this is the "Pro" way
#  Data Integrity: By using the Bleak start_notify method, you ensure the PC is ready to receive before the test even starts.
#  Traceability: Every log entry gets a PC-side microsecond timestamp. This helps you debug timing issues in your hardware tests.
#  Automation Ready: The JSON summary can be easily picked up by a Jenkins or GitHub Actions runner for automated CI/CD of your hardware.
