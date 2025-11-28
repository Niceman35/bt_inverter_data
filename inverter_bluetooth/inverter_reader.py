import logging
import asyncio
import os
import json
import time
from bleak import BleakClient, BleakScanner # BleakScanner reinstated
from struct import unpack
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

BASE_MQTT_TOPIC = "solar_inverter"
DISCOVERY_PREFIX = "homeassistant"

# Set up logging for the add-on logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Configuration from Environment (Mandatory) ---
INVERTER_ADDRESS = os.environ.get("INVERTER_ADDRESS")
MQTT_HOST = os.environ.get("MQTT_HOST")
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASS = os.environ.get("MQTT_PASS")
# --------------------------------------------------

sensors = [
    {"name": "AC IN Voltage", "unit": "V", "unique_id": "ac_in_v", "device_class": "voltage"},
    {"name": "AC IN Frequency", "unit": "Hz", "unique_id": "ac_in_hz", "device_class": "frequency"},
    {"name": "AC OUT Voltage", "unit": "V", "unique_id": "ac_out_v", "device_class": "voltage"},
    {"name": "AC OUT Frequency", "unit": "Hz", "unique_id": "ac_out_hz", "device_class": "frequency"},
    {"name": "Output Load", "unit": "VA", "unique_id": "power_va", "device_class": "apparent_power"},
    {"name": "Output Power", "unit": "W", "unique_id": "power_wt", "device_class": "power"},
    {"name": "Load percent", "unit": "%", "unique_id": "power_load", "device_class": "power_factor"},
    {"name": "Bus Voltage", "unit": "V", "unique_id": "mainbus_v", "device_class": "voltage"},
    {"name": "Internal Temperature", "unit": "\u00b0C", "unique_id": "int_term_c", "device_class": "temperature"},
    {"name": "Battery Voltage", "unit": "V", "unique_id": "battery_v", "device_class": "voltage"},
    {"name": "Battery Charge Current", "unit": "A", "unique_id": "bat_charge_a", "device_class": "current"},
    {"name": "Battery Charge Power", "unit": "W", "unique_id": "bat_charge_wt", "device_class": "power"},
    {"name": "Battery Capacity", "unit": "%", "unique_id": "bat_charge_perc", "device_class": "battery"},
    {"name": "Battery Discharge Current", "unit": "A", "unique_id": "bat_discharge_a", "device_class": "current"},
    {"name": "Battery Discharge Power", "unit": "W", "unique_id": "bat_discharge_wt", "device_class": "power"},
    {"name": "Status Charging", "unit": "", "unique_id": "status_charge"},
    {"name": "Status Solar Charging", "unit": "", "unique_id": "status_charge_solar"},
    {"name": "Status AC Charging", "unit": "", "unique_id": "status_charge_ac"},
    {"name": "Solar Current", "unit": "A", "unique_id": "solar_a", "device_class": "current"},
    {"name": "Solar Voltage", "unit": "V", "unique_id": "solar_v", "device_class": "voltage"},
    {"name": "Solar Power", "unit": "W", "unique_id": "solar_wt", "device_class": "power"},
]
# CHARACTERISTIC_MAP removed as per request

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        log.error(f"MQTT connection failed: {reason_code}")
    else:
        log.info("MQTT connected successfully.")

def send_mqtt_discovery(client):
    log.info("Sending Home Assistant MQTT discovery messages...")
    for sensor in sensors:
        config_topic = f"{DISCOVERY_PREFIX}/sensor/{sensor['unique_id']}/config"
        state_topic = f"{BASE_MQTT_TOPIC}/{sensor['unique_id']}/state"

        payload = {
            "name": sensor["name"],
            "stat_t": state_topic,
            "unit_of_meas": sensor["unit"],
            "uniq_id": sensor["unique_id"],
            "dev": {
                "ids": "solar_inverter_bt",
                "name": "Solar Inverter BT",
                "mdl": "SOL5K48V",
                "mf": "SolTherm"
            }
        }
        device_class = sensor.get("device_class")
        if device_class:
            payload["dev_cla"] = device_class
            payload["stat_cla"] = "measurement"

        client.publish(config_topic, json.dumps(payload), retain=True)
    log.info("MQTT discovery messages sent.")

async def scan_devices():
    """Scans for available Bluetooth devices and prints their addresses."""
    log.info("INVERTER_ADDRESS is not configured. Starting Bluetooth device scan...")
    log.info("This scan will take about 10 seconds. Please ensure your inverter is on.")

    try:
        devices = await BleakScanner.discover(timeout=10.0)

        log.info("--- Discovered Bluetooth Devices ---")
        if not devices:
            log.info("No Bluetooth devices found. Check if Bluetooth is enabled and the inverter is in range.")
        else:
            for i, device in enumerate(devices):
                rssi = getattr(device, 'rssi', 'N/A')
                log.info(f"[{i+1}] Address: {device.address}, Name: {device.name if device.name else 'N/A'}, RSSI: {rssi}")
                log.info(f"      ---> Full Device Object (Debug): {repr(device)}")

        log.info("------------------------------------")
        log.info("ACTION REQUIRED: Copy the correct inverter MAC address and paste it into the add-on configuration, then restart the add-on.")
    except Exception as e:
        log.error(f"Failed to perform Bluetooth scan: {e}")

async def run_diagnostic_dump(address):
    """Connects to the device and attempts to read all characteristics with the 'read' property."""
    log.info("--- Starting DIAGNOSTIC MODE: Attempting to read all readable characteristics ---")
    try:
        async with BleakClient(address, use_bdaddr=True) as client:
            if not client.is_connected:
                log.error("Failed to connect for diagnostic dump.")
                return

            log.info("Successfully connected for diagnostic dump.")

            characteristics = client.services.characteristics

            log.info("--- Characteristic Read Dump ---")

            results = []

            for char_uuid, characteristic in characteristics.items():
                handle = characteristic.handle
                properties = characteristic.properties

                if 'read' in properties:
                    log.info(f"Attempting to read from HANDLE: {handle} | UUID: {char_uuid} | Properties: {properties}")
                    try:
                        # Wait for a brief moment before reading, sometimes helps stability
                        await asyncio.sleep(0.01)
                        value = await client.read_gatt_char(handle)
                        hex_value = value.hex()
                        length = len(value)

                        results.append(f"  ✅ SUCCESS | HANDLE: {handle:<4} | UUID: {char_uuid} | Length: {length:<3} bytes | Value (Hex): {hex_value}")
                    except Exception as e:
                        results.append(f"  ❌ FAILED  | HANDLE: {handle:<4} | UUID: {char_uuid} | Error: {e}")
                else:
                    results.append(f"  ⏭️ SKIPPED | HANDLE: {handle:<4} | UUID: {char_uuid} | Properties: {properties} (No 'read' property)")

            log.info("--- FINAL DIAGNOSTIC READ RESULTS ---")
            for result in results:
                log.info(result)
            log.info("-------------------------------------")
            log.info("Diagnostic Mode Complete. Check the logs for data. The script will now wait 30 seconds to retry.")

    except Exception as e:
        log.error(f"Error during diagnostic dump: {e}")


async def main():
    # 1. Configuration Check
    if not INVERTER_ADDRESS:
        await scan_devices() # scan_devices reinstated here
        log.warning("Inverter address missing. Exiting script after diagnostic scan.")
        return

    if False:
        log.warning("DIAGNOSTIC_MODE is ENABLED. The script will only attempt to read all characteristics and will NOT publish data to MQTT.")
        while True:
            try:
                await run_diagnostic_dump(INVERTER_ADDRESS)
            except Exception as e:
                log.error(f"Error in diagnostic mode loop: {e}. Retrying in 30 seconds...")
            await asyncio.sleep(30)
        return

    if not all([MQTT_HOST, MQTT_USER, MQTT_PASS]):
        log.error("MQTT configuration variables (MQTT_HOST, MQTT_USER, MQTT_PASS) are missing. Exiting.")
        return

    # 2. MQTT Setup
    last_discovery_time = 0
    client = mqtt.Client(
        client_id="SolarInv",
        callback_api_version=CallbackAPIVersion.VERSION2
    )
    client.on_connect = on_connect

    try:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_HOST)
        client.loop_start()
    except Exception as e:
        log.error(f"Failed to connect to MQTT broker at {MQTT_HOST}: {e}. Exiting.")
        return

    # 3. Main Loop
    while True:
        try:
            log.info(f"Attempting to read data from inverter at {INVERTER_ADDRESS}...")

            data = await get_data(INVERTER_ADDRESS)

            log.info(f"Collected Data: {data}")

            for sensor in sensors:
                unique_id = sensor["unique_id"]
                if unique_id in data:
                    client.publish(f"{BASE_MQTT_TOPIC}/{unique_id}/state", data[unique_id], retain=False)

            log.info("Data published successfully. Waiting for 30 seconds.")

            current_time = time.time()
            # Send discovery every 30 minutes (1800 seconds)
            if current_time - last_discovery_time >= 1800:
                send_mqtt_discovery(client)
                last_discovery_time = current_time

        except Exception as e:
            log.error(f"An error occurred during data collection/publishing: {e}. Retrying in 30 seconds...")

        await asyncio.sleep(30)

async def get_data(address):
    def checkBit(numb, bitnum):
        # Convert integer to string "1" or "0" based on bit status
        return "1" if numb & (1 << bitnum) else "0"

    data = {}

    try:
        # Added use_bdaddr=True for potential stability improvement
        async with BleakClient(address, use_bdaddr=True) as client:
            if not client.is_connected:
                log.error("Failed to connect to Bluetooth device.")
                raise ConnectionError("Bluetooth connection failed.")

            log.info("Successfully connected.")

            # Hardcoded integer handles found via diagnostic mode for this inverter model
            handle_2a03 = 28
            handle_2a04 = 31
            handle_2a11 = 62

            # --- Read first characteristic (General Status, Handle 55) ---
            log.info(f"Reading General Status from handle {handle_2a03}...")
            value = bytes(await client.read_gatt_char(handle_2a03))

            # Assuming 'h' is signed short (2 bytes), 10 values = 20 bytes total
            if len(value) < 20:
                raise ValueError(f"Incomplete data received for General Status (2a03). Expected 20 bytes, got {len(value)}.")

            valueArr = unpack('<hhhhhhhhhh', value)

            batteryVolts = valueArr[8]/100
            data['ac_in_v'] = valueArr[0]/10
            data['ac_in_hz'] = valueArr[1]/10
            data['ac_out_v'] = valueArr[2]/10
            data['ac_out_hz'] = valueArr[3]/10
            data['power_va'] = valueArr[4]
            data['power_wt'] = valueArr[5]
            data['power_load'] = valueArr[6]
            data['mainbus_v'] = valueArr[7]
            data['battery_v'] = batteryVolts
            data['bat_charge_a'] = valueArr[9]
            data['bat_charge_wt'] = valueArr[9]*batteryVolts

            # --- Read second characteristic (Battery & Temperature, Handle 52) ---
            log.info(f"Reading Battery & Temp from handle {handle_2a04}...")
            value = bytes(await client.read_gatt_char(handle_2a04))
            if len(value) < 20:
                raise ValueError(f"Incomplete data received for Battery & Temperature (2a04). Expected 20 bytes, got {len(value)}.")

            valueArr = unpack('<hhhhhhhhhh', value)
            data['bat_charge_perc'] = valueArr[0]
            data['int_term_c'] = valueArr[1]
            data['bat_discharge_a'] = valueArr[2]
            data['bat_discharge_wt'] = valueArr[2]*batteryVolts
            data['status_charge_ac'] = checkBit(valueArr[3], 0)
            data['status_charge_solar'] = checkBit(valueArr[3], 1)
            data['status_charge'] = checkBit(valueArr[3], 2)

            # --- Read third characteristic (Solar/MPPT, Handle 58) ---
            log.info(f"Reading Solar/MPPT from handle {handle_2a11}...")
            value = bytes(await client.read_gatt_char(handle_2a11))
            if len(value) < 20:
                raise ValueError(f"Incomplete data received for Solar/MPPT (2a11). Expected 20 bytes, got {len(value)}.")

            valueArr = unpack('<hhhhhhhhhh', value)
            data['solar_a'] = valueArr[5]/10
            data['solar_v'] = valueArr[6]/10
            data['solar_wt'] = valueArr[7]

        return data

    except Exception as e:
        log.error(f"Error reading from Bluetooth device: {e}")
        raise

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())