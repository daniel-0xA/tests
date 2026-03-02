#!/usr/bin/env python3
"""
BLE GATT Client Tester for NimBLE GATT Server
Tests all characteristics: CMD, STATUS, DATA, MTU handling
"""

import asyncio
import sys
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

# UUIDs matching the NimBLE server
TESTER_SERVICE_UUID = "000000FF-0000-1000-8000-00805F9B34FB"
CMD_CHAR_UUID = "0000FF01-0000-1000-8000-00805F9B34FB"
STATUS_CHAR_UUID = "0000FF02-0000-1000-8000-00805F9B34FB"
DATA_CHAR_UUID = "0000FF03-0000-1000-8000-00805F9B34FB"
CCCD_UUID = "00002902-0000-1000-8000-00805F9B34FB"

# Global tracking
received_status = []
received_data = []
current_mtu = 23


def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Handle incoming notifications"""
    global received_status, received_data
    char_uuid = characteristic.uuid
    value = bytes(data)
    
    if char_uuid == STATUS_CHAR_UUID:
        print(f"[STATUS NOTIFY] {value.hex()} | {value}")
        received_status.append(value)
    elif char_uuid == DATA_CHAR_UUID:
        print(f"[DATA NOTIFY] {len(value)} bytes: {value.hex()[:64]}...")
        received_data.append(value)
    else:
        print(f"[NOTIFY] {char_uuid}: {value.hex()}")


async def find_device() -> BLEDevice | None:
    """Scan for the NimBLE GATT server device"""
    print("Scanning for BLE devices...")
    devices = await BleakScanner.discover(timeout=5)
    
    if not devices:
        print("No BLE devices found. Ensure Bluetooth is ON.")
        return None

    print(f"{'Name':<30} | {'Address':<20} | {'RSSI':<5}")
    print("-" * 60)
    
    for device in devices:
        name = device.name if device.name else "Unknown"
        print(f"{name:<30} | {device.address:<20} | {device.rssi} dBm")

    # Look for our target device
    for d in devices:
        if d.name and ("NimBLE" in d.name or "ESP" in d.name or "GATT" in d.name):
            print(f"\nFound target device: {d.name} ({d.address})")
            return d
    
    return None


async def request_mtu(client: BleakClient, mtu: int = 512) -> int:
    """Request specific MTU from the server"""
    global current_mtu
    try:
        # Request larger MTU
        await client.get_device().pair()
        # On Windows, MTU negotiation is handled differently
        # Let's check what MTU we got
        mtu_value = mtu  # Default to requested
        print(f"Requested MTU: {mtu}")
        current_mtu = mtu_value
        return mtu_value
    except Exception as e:
        print(f"MTU request error (using default): {e}")
        return 23


async def connect_and_test(address: str = None):
    """Connect to device and test all characteristics"""
    global current_mtu, received_status, received_data
    
    # Reset state
    received_status = []
    received_data = []
    current_mtu = 23
    
    # Find device
    if not address:
        device = await find_device()
        if not device:
            print("Device not found!")
            return
        address = device.address
    
    print(f"\nConnecting to {address}...")
    
    async with BleakClient(address) as client:
        print(f"Connected: {client.is_connected}")
        
        # Request larger MTU
        print("\n" + "="*50)
        print("TEST 0: Request larger MTU")
        print("="*50)
        
        try:
            # Try to negotiate larger MTU
            await client.get_device().pair()
            # On some platforms, MTU is negotiated automatically
            print(f"MTU negotiated: {current_mtu}")
        except Exception as e:
            print(f"Note: {e}")
        
        await asyncio.sleep(0.5)
        
        # Get service
        service = client.services.get_service(TESTER_SERVICE_UUID)
        if not service:
            print(f"Service {TESTER_SERVICE_UUID} not found!")
            print("\nAvailable services:")
            for s in client.services:
                print(f"  {s.uuid}")
            return
        
        print(f"\nService found: {service.uuid}")
        
        # List all characteristics
        print("\nCharacteristics:")
        for char in service.characteristics:
            props = []
            if char.properties & 0x01: props.append("Read")
            if char.properties & 0x02: props.append("Write")
            if char.properties & 0x04: props.append("WriteNoResp")
            if char.properties & 0x08: props.append("Indicate")
            if char.properties & 0x10: props.append("Notify")
            
            print(f"  {char.uuid}")
            print(f"    Properties: {', '.join(props)}")
        
        # Get characteristics
        cmd_char = service.get_characteristic(CMD_CHAR_UUID)
        status_char = service.get_characteristic(STATUS_CHAR_UUID)
        data_char = service.get_characteristic(DATA_CHAR_UUID)
        
        if not all([cmd_char, status_char, data_char]):
            print("ERROR: Missing required characteristics!")
            return
        
        # Enable notifications for STATUS and DATA
        print("\nEnabling notifications...")
        await client.start_notify(status_char, notification_handler)
        await client.start_notify(data_char, notification_handler)
        await asyncio.sleep(0.5)
        
        # ===== TEST 1: Basic Write/Read =====
        print("\n" + "="*50)
        print("TEST 1: Write to CMD characteristic")
        print("="*50)
        
        test_cmd = b"\x01"  # Start test command
        await client.write_gatt_char(cmd_char, test_cmd)
        print(f"Written to CMD: {test_cmd.hex()}")
        
        await asyncio.sleep(0.5)
        
        cmd_value = await client.read_gatt_char(cmd_char)
        print(f"CMD value read: {cmd_value.hex()}")
        
        # ===== TEST 2: Read STATUS =====
        print("\n" + "="*50)
        print("TEST 2: Read STATUS characteristic")
        print("="*50)
        
        status_value = await client.read_gatt_char(status_char)
        print(f"STATUS value: {status_value.hex()}")
        
        # ===== TEST 3: Read DATA =====
        print("\n" + "="*50)
        print("TEST 3: Read DATA characteristic")
        print("="*50)
        
        data_value = await client.read_gatt_char(data_char)
        print(f"DATA value ({len(data_value)} bytes): {data_value.hex()[:64]}...")
        
        # ===== TEST 4: Small data write (fits in default MTU) =====
        print("\n" + "="*50)
        print("TEST 4: Small data write (< MTU)")
        print("="*50)
        
        small_data = b"Hello" * 4  # 20 bytes
        await client.write_gatt_char(data_char, small_data)
        print(f"Written small data: {len(small_data)} bytes")
        
        await asyncio.sleep(0.5)
        
        # ===== TEST 5: Large data write (exceeds default MTU) =====
        print("\n" + "="*50)
        print("TEST 5: Large data write (> default MTU)")
        print("="*50)
        
        # Create data larger than default MTU (23 bytes)
        # Leave some room for ATT header
        large_data = b"A" * 50  # 50 bytes
        await client.write_gatt_char(data_char, large_data)
        print(f"Written large data: {len(large_data)} bytes")
        
        await asyncio.sleep(1)
        
        # ===== TEST 6: Very large data write =====
        print("\n" + "="*50)
        print("TEST 6: Very large data write (100 bytes)")
        print("="*50)
        
        very_large_data = bytes(range(256))[:100]  # 100 bytes of varying data
        await client.write_gatt_char(data_char, very_large_data)
        print(f"Written very large data: {len(very_large_data)} bytes")
        
        await asyncio.sleep(1)
        
        # ===== TEST 7: Write pattern data =====
        print("\n" + "="*50)
        print("TEST 7: Write pattern data")
        print("="*50)
        
        pattern_data = bytes([i % 256 for i in range(64)])
        await client.write_gatt_char(data_char, pattern_data)
        print(f"Written pattern: {pattern_data.hex()}")
        
        await asyncio.sleep(0.5)
        
        # ===== TEST 8: Multiple CMD commands =====
        print("\n" + "="*50)
        print("TEST 8: Multiple CMD commands")
        print("="*50)
        
        for cmd in [b"\x00", b"\x01", b"\x02", b"\xFF"]:
            await client.write_gatt_char(cmd_char, cmd)
            print(f"Written CMD: {cmd.hex()}")
            await asyncio.sleep(0.3)
            
            status = await client.read_gatt_char(status_char)
            print(f"  STATUS: {status.hex()}")
        
        # ===== TEST 9: Read after notifications =====
        print("\n" + "="*50)
        print("TEST 9: DATA read after notifications")
        print("="*50)
        
        final_data = await client.read_gatt_char(data_char)
        print(f"Final DATA ({len(final_data)} bytes): {final_data.hex()[:64]}...")
        
        # ===== SUMMARY =====
        print("\n" + "="*50)
        print("SUMMARY")
        print("="*50)
        print(f"MTU: {current_mtu} bytes")
        print(f"STATUS notifications received: {len(received_status)}")
        print(f"DATA notifications received: {len(received_data)}")
        
        # Show notification details
        if received_data:
            print("\nDATA notifications details:")
            for i, data in enumerate(received_data):
                print(f"  [{i}] {len(data)} bytes: {data.hex()[:32]}...")
        
        print("\nAll tests completed!")


async def mtu_test(address: str):
    """Dedicated MTU test"""
    global current_mtu, received_status, received_data
    
    received_status = []
    received_data = []
    current_mtu = 23
    
    async with BleakClient(address) as client:
        print(f"Connected to {address}")
        
        service = client.services.get_service(TESTER_SERVICE_UUID)
        if not service:
            print("Service not found!")
            return
        
        cmd_char = service.get_characteristic(CMD_CHAR_UUID)
        data_char = service.get_characteristic(DATA_CHAR_UUID)
        
        # Enable DATA notifications
        await client.start_notify(data_char, notification_handler)
        
        print("\n" + "="*50)
        print("MTU TEST: Writing data at various sizes")
        print("="*50)
        
        # Test different sizes
        test_sizes = [10, 20, 23, 30, 50, 100, 200]
        
        for size in test_sizes:
            print(f"\n--- Writing {size} bytes ---")
            test_data = bytes(range(size))
            await client.write_gatt_char(data_char, test_data)
            await asyncio.sleep(1)
        
        print(f"\nNotifications received: {len(received_data)}")
        
        for i, data in enumerate(received_data):
            print(f"  [{i}] {len(data)} bytes")


async def stress_test(address: str):
    """Stress test with rapid writes"""
    global received_data
    
    received_data = []
    
    async with BleakClient(address) as client:
        print(f"Connected to {address}")
        
        service = client.services.get_service(TESTER_SERVICE_UUID)
        data_char = service.get_characteristic(DATA_CHAR_UUID)
        
        await client.start_notify(data_char, notification_handler)
        await asyncio.sleep(0.5)
        
        print("\n" + "="*50)
        print("STRESS TEST: Rapid writes")
        print("="*50)
        
        for i in range(10):
            data = f"Test{i:03d}".encode() * 3
            await client.write_gatt_char(data_char, data)
            await asyncio.sleep(0.1)
        
        await asyncio.sleep(2)
        
        print(f"\nReceived {len(received_data)} notifications")


async def interactive_mode(address: str):
    """Interactive mode for manual testing"""
    async with BleakClient(address) as client:
        print(f"Connected to {address}")
        print("\nAvailable commands:")
        print("  r <char>   - Read characteristic (cmd, status, data)")
        print("  w <char> <hex> - Write hex to characteristic")
        print("  n <char>   - Enable notifications (status, data)")
        print("  mtu <size> - Request MTU size")
        print("  q          - Quit")
        
        service = client.services.get_service(TESTER_SERVICE_UUID)
        cmd_char = service.get_characteristic(CMD_CHAR_UUID)
        status_char = service.get_characteristic(STATUS_CHAR_UUID)
        data_char = service.get_characteristic(DATA_CHAR_UUID)
        
        chars = {
            "cmd": cmd_char,
            "status": status_char,
            "data": data_char
        }
        
        # Enable notifications by default
        await client.start_notify(status_char, notification_handler)
        await client.start_notify(data_char, notification_handler)
        print("Notifications enabled for STATUS and DATA")
        
        while True:
            try:
                cmd = input("\n> ").strip().split()
                if not cmd:
                    continue
                    
                if cmd[0] == "q":
                    break
                    
                elif cmd[0] == "r":
                    if len(cmd) < 2:
                        print("Usage: r <cmd|status|data>")
                        continue
                    char = chars.get(cmd[1])
                    if char:
                        val = await client.read_gatt_char(char)
                        print(f"{cmd[1]}: {val.hex()} ({len(val)} bytes)")
                    else:
                        print(f"Unknown: {cmd[1]}")
                        
                elif cmd[0] == "w":
                    if len(cmd) < 3:
                        print("Usage: w <cmd|status|data> <hex>")
                        continue
                    char = chars.get(cmd[1])
                    if char:
                        data = bytes.fromhex(cmd[2])
                        await client.write_gatt_char(char, data)
                        print(f"Written: {data.hex()} ({len(data)} bytes)")
                    else:
                        print(f"Unknown: {cmd[1]}")
                        
                elif cmd[0] == "n":
                    if len(cmd) < 2:
                        print("Usage: n <status|data>")
                        continue
                    char = chars.get(cmd[1])
                    if char:
                        await client.start_notify(char, notification_handler)
                        print(f"Notifications enabled for {cmd[1]}")
                    else:
                        print(f"Unknown: {cmd[1]}")
                
                elif cmd[0] == "mtu":
                    print("Note: MTU is negotiated automatically on connection")
                        
            except Exception as e:
                print(f"Error: {e}")
                break
        
        print("Disconnected")


async def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "-i" and len(sys.argv) > 2:
            await interactive_mode(sys.argv[2])
        elif sys.argv[1] == "--mtu" and len(sys.argv) > 2:
            await mtu_test(sys.argv[2])
        elif sys.argv[1] == "--stress" and len(sys.argv) > 2:
            await stress_test(sys.argv[2])
        else:
            address = sys.argv[1] if len(sys.argv) > 1 else None
            await connect_and_test(address)
    else:
        await connect_and_test()


if __name__ == "__main__":
    print("""
BLE GATT Client Tester
======================
Usage:
  python ble_test_client.py [address]           - Auto test
  python ble_test_client.py -i <address>        - Interactive mode
  python ble_test_client.py --mtu <address>     - MTU test
  python ble_test_client.py --stress <address> - Stress test
""")
    asyncio.run(main())
