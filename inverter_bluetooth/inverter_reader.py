import logging
import asyncio
import os
import json
import time
from bleak import BleakClient, BleakScanner
from struct import unpack
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion # <--- NEW IMPORT

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

# UPDATED: Changed signature for V2 API to include reason_code and properties
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        # reason_code is a ConnectReasonCode object with human-readable error info
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
                log.info(f"[{i+1}] Address: {device.address}, Name: {device.name if device.name else 'N/A'}, RSSI: {device.rssi}")

        log.info("------------------------------------")
        log.info("ACTION REQUIRED: Copy the correct inverter MAC address and paste it into the add-on configuration, then restart the add-on.")
    except Exception as e:
        log.error(f"Failed to perform Bluetooth scan: {e}")

async def main():
    # 1. Configuration Check
    if not INVERTER_ADDRESS:
        await scan_devices()
        log.warning("Inverter address missing. Exiting script after diagnostic scan.")
        return

    if not all([MQTT_HOST, MQTT_USER, MQTT_PASS]):
        log.error("MQTT configuration variables (MQTT_HOST, MQTT_USER, MQTT_PASS) are missing. Exiting.")
        exit(1)

    # 2. MQTT Setup
    last_discovery_time = 0
    # UPDATED: Added callback_api_version=CallbackAPIVersion.VERSION2
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
        exit(1)

    # 3. Main Loop
    while True:
        try:
            log.info(f"Attempting to read data from inverter at {INVERTER_ADDRESS}...")
            data = await get_data(INVERTER_ADDRESS)

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
            # We catch the error here and retry after the sleep.
            log.error(f"An error occurred during data collection/publishing: {e}. Retrying in 30 seconds...")

        await asyncio.sleep(30)

async def get_data(address):
    def checkBit(numb, bitnum):
        # Convert integer to string "1" or "0" based on bit status
        return "1" if numb & (1 << bitnum) else "0"

    data = {}

    try:
        # UPDATED: Added use_bdaddr=True for potential stability improvement
        async with BleakClient(address, use_bdaddr=True) as client:
            if not client.is_connected:
                log.error("Failed to connect to Bluetooth device.")
                raise ConnectionError("Bluetooth connection failed.")

            # Read first characteristic (e.g., General Status)
            value = bytes(await client.read_gatt_char('00002a03-0000-1000-8000-00805f9b34fb'))
            # valueArr = unpack('<hhhhhhhhhh', value) # Your original unpack format

            # Assuming 'h' is signed short (2 bytes), 10 values = 20 bytes total
            if len(value) < 20:
                raise ValueError("Incomplete data received for characteristic 2a03.")

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

            # Read second characteristic (e.g., Battery & Temperature)
            value = bytes(await client.read_gatt_char('00002a04-0000-1000-8000-00805f9b34fb'))
            if len(value) < 20:
                raise ValueError("Incomplete data received for characteristic 2a04.")

            valueArr = unpack('<hhhhhhhhhh', value)
            data['bat_charge_perc'] = valueArr[0]
            data['int_term_c'] = valueArr[1]
            data['bat_discharge_a'] = valueArr[2]
            data['bat_discharge_wt'] = valueArr[2]*batteryVolts
            data['status_charge_ac'] = checkBit(valueArr[3], 0)
            data['status_charge_solar'] = checkBit(valueArr[3], 1)
            data['status_charge'] = checkBit(valueArr[3], 2)

            # Read third characteristic (e.g., Solar/MPPT)
            value = bytes(await client.read_gatt_char('00002a11-0000-1000-8000-00805f9b34fb'))
            if len(value) < 20:
                raise ValueError("Incomplete data received for characteristic 2a11.")

            valueArr = unpack('<hhhhhhhhhh', value)
            data['solar_a'] = valueArr[5]/10
            data['solar_v'] = valueArr[6]/10
            data['solar_wt'] = valueArr[7]

        return data

    except Exception as e:
        log.error(f"Error reading from Bluetooth device: {e}")
        # Re-raise the exception to be caught by the main loop for retry/logging
        raise

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())