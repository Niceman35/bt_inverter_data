ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies needed for Bluetooth and Python
RUN apk add --no-cache python3 py3-pip bluez

# Set up the working directory and install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip3 install bleak paho-mqtt

# Copy your scripts
COPY inverter_reader.py run.sh /app/

# Set the entrypoint script
CMD [ "/bin/bash", "/app/run.sh" ]