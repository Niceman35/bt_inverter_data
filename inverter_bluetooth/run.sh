#!/usr/bin/env bash
set -e

# These lines read from the user configuration
export INVERTER_ADDRESS=$(jq --raw-output ".inverter_address" /data/options.json)
export MQTT_HOST=$(jq --raw-output ".mqtt_host" /data/options.json)
export MQTT_USER=$(jq --raw-output ".mqtt_user" /data/options.json)
export MQTT_PASS=$(jq --raw-output ".mqtt_pass" /data/options.json)

echo "Starting Inverter Bluetooth Reader..."
echo "Inverter Address: ${INVERTER_ADDRESS}"
echo "MQTT Host: ${MQTT_HOST}"

# Execute the Python script
python3 /app/inverter_reader.py