import asyncio
import logging
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakBluetoothNotAvailableError

# Use the UUIDs we defined in the ESP-IDF C code
SERVICE_UUID = "000000ff-0000-1000-8000-00805f9b34fb"
CMD_UUID     = "0000ff01-0000-1000-8000-00805f9b34fb"
STATUS_UUID  = "0000ff02-0000-1000-8000-00805f9b34fb"
DATA_UUID    = "0000ff03-0000-1000-8000-00805f9b34fb"

# Callback for the "Serial Pipe" logs
def notification_handler(sender, data):
    print(f"[LOG]: {data.decode('utf-8', errors='ignore').strip()}")

# Callback for the Status (Pass/Fail)
def status_handler(sender, data):
    result = "PASS" if data[0] == 0x01 else "FAIL"
    print(f"*** TEST RESULT RECEIVED: {result} ***")

async def run_tester():
    try:
        devName = "nimble-ble-spp-svr1"#"OpenOBD" #"VEEPEAK"
        print(f"Scanning for {devName}...")
        device = await BleakScanner.find_device_by_name(devName)
        
        if not device:
            print(f"Tester not found. Check if {devName} is advertising.")
            return

        async with BleakClient(device) as client:
            print(f"Connected to {device.address}")

            # 1. Subscribe to Status and Logs
            await client.start_notify(STATUS_UUID, status_handler)
            await client.start_notify(DATA_UUID, notification_handler)

            # 2. Send START command (0x01)
            print("Sending START command...")
            await client.write_gatt_char(CMD_UUID, bytearray([0x01]))

            # 3. Keep the script running while the test executes
            print("Waiting for test results (Press Ctrl+C to stop)...")
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            finally:
                await client.stop_notify(STATUS_UUID)
                await client.stop_notify(DATA_UUID)
    except BleakBluetoothNotAvailableError as e:
        print("\n" + "="*60)
        print("ERROR: Bluetooth is not available!")
        print("="*60)
        print("\nPlease do the following:")
        print("  1. Turn ON Bluetooth in Windows Settings")
        print("     Settings > Bluetooth & devices > Toggle Bluetooth ON")
        print("")
        print("  2. Or click the Bluetooth icon in the system tray")
        print("     and enable Bluetooth")
        print("")
        print("  3. If using a USB Bluetooth adapter,")
        print("     make sure it's plugged in and drivers are installed")
        print("="*60 + "\n")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_tester())

#   Summary of the Flow
#   ESP32 starts advertising.
#   Python Script finds the device and connects.
#   Python Script "Subscribes" to your Log and Status characteristics.
#   Python Script writes 0x01 to the Command characteristic.
#   ESP32 triggers the hw_test_task on Core 1.
#   ESP32 pushes logs into the Ring Buffer, which the ble_tx_task on Core 0 sends to the PC.
#   Python Script prints the logs in real-time.

# Key Integration Points
#  UUID Format: Bleak requires the full 128-bit UUID. For 16-bit UUIDs (like 0xFF01), the format is 0000XXXX-0000-1000-8000-00805f9b34fb.
#  Notifications: The start_notify call internally writes 0x0001 to the CCCD descriptor we defined in your ESP-IDF table (IDX_CHAR_DATA_CFG).
#  Auto-MTU: When using BleakClient, the OS typically negotiates the highest possible MTU and Data Length Extension (DLE) supported by your Bluetooth adapter and the ESP32.