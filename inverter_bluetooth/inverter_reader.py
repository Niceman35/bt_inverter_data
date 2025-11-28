import logging
import asyncio
import os
from bleak import BleakClient
from struct import unpack
import paho.mqtt.client as mqtt
import time
import json

BASE_MQTT_TOPIC = "solar_inverter"
DISCOVERY_PREFIX = "homeassistant"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

INVERTER_ADDRESS = os.environ.get("INVERTER_ADDRESS")
MQTT_HOST = os.environ.get("MQTT_HOST")
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASS = os.environ.get("MQTT_PASS")

if not all([INVERTER_ADDRESS, MQTT_HOST, MQTT_USER, MQTT_PASS]):
    log.error("Configuration variables (INVERTER_ADDRESS, MQTT_HOST, MQTT_USER, MQTT_PASS) are missing. Check your add-on configuration.")
    # Exit gracefully if configuration is missing
    exit(1)

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

def on_connect(client, userdata, flags, rc):
    if rc==0:
        log.info("MQTT connected ok")
    else:
        log.info(f"Connection failed with code {rc}")

def send_mqtt_discovery():
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

        log.info(json.dumps(payload))
        client.publish(config_topic, json.dumps(payload), retain=True)

# --- NEW SCANNING FUNCTION ---
async def scan_devices():
    """Scans for available Bluetooth devices and prints their addresses."""
    log.info("INVERTER_ADDRESS is not configured. Starting Bluetooth device scan...")
    log.info("This scan will take about 5-10 seconds. Please wait.")

    # Increase timeout to ensure comprehensive scanning
    devices = await discover(timeout=10.0)

    log.info("--- Discovered Bluetooth Devices ---")
    if not devices:
        log.info("No Bluetooth devices found.")
        log.info("Ensure your Bluetooth adapter is working and the inverter is powered on.")
        return

    for i, device in enumerate(devices):
        log.info(f"[{i+1}] Address: {device.address}, Name: {device.name if device.name else 'N/A'}")

    log.info("------------------------------------")
    log.info("Copy the correct inverter address and paste it into the add-on configuration, then restart the add-on.")

async def main():
    if not INVERTER_ADDRESS:
        await scan_devices()
        log.warning("Inverter address missing. Exiting script after scan.")
        # Exit the script after scanning
        return

    if not all([MQTT_HOST, MQTT_USER, MQTT_PASS]):
        log.error("MQTT configuration variables (MQTT_HOST, MQTT_USER, MQTT_PASS) are missing. Check your add-on configuration.")
        exit(1)

    last_discovery_time = 0

    client = mqtt.Client("SolarInv")
    client.on_connect=on_connect

    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_HOST)
    client.loop_start()

    while True:
        # Your data extraction logic
        try:
            data = await get_data(INVERTER_ADDRESS)
            for sensor in sensors:
                unique_id = sensor["unique_id"]
                if unique_id in data:
                    client.publish(f"{BASE_MQTT_TOPIC}/{unique_id}/state", data[unique_id])

            current_time = time.time()
            if current_time - last_discovery_time >= 1800:
                send_mqtt_discovery()
                last_discovery_time = current_time

        except Exception as e:  # This will catch all exceptions
            log.error(f"An error occurred: {e}. Retrying in 30 seconds...")

        await asyncio.sleep(30)

async def get_data(address):
    def checkBit(numb, bitnum):
        if numb & (1 << bitnum):
            return "1"
        else:
            return "0"

    data = {}

    async with BleakClient(address) as client:
        value = bytes(await client.read_gatt_char('00002a03-0000-1000-8000-00805f9b34fb'))
        log.info("\tValue: {0} ".format(value.hex(' ')))
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

        value = bytes(await client.read_gatt_char('00002a04-0000-1000-8000-00805f9b34fb'))
        log.info("\tValue: {0} ".format(value.hex(' ')))
        valueArr = unpack('<hhhhhhhhhh', value)
        data['bat_charge_perc'] = valueArr[0]
        data['int_term_c'] = valueArr[1]
        data['bat_discharge_a'] = valueArr[2]
        data['bat_discharge_wt'] = valueArr[2]*batteryVolts
        data['status_charge_ac'] = checkBit(valueArr[3], 0)
        data['status_charge_solar'] = checkBit(valueArr[3], 1)
        data['status_charge'] = checkBit(valueArr[3], 2)

        value = bytes(await client.read_gatt_char('00002a11-0000-1000-8000-00805f9b34fb'))
        log.info("\tValue: {0} ".format(value.hex(' ')))
        valueArr = unpack('<hhhhhhhhhh', value)
        data['solar_a'] = valueArr[5]/10
        data['solar_v'] = valueArr[6]/10
        data['solar_wt'] = valueArr[7]

    log.info(json.dumps(data))
    return data

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

