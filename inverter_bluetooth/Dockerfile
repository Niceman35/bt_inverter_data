ARG BUILD_FROM
FROM $BUILD_FROM

# Install OS dependencies: Python, pip, and BlueZ (Bluetooth stack)
RUN apk add --no-cache python3 py3-pip bluez

# Set up the working directory
WORKDIR /app

# Install Python dependencies directly
RUN pip3 install bleak paho-mqtt

# Copy your scripts into the container's app directory
COPY inverter_reader.py run.sh /app/

# Set the entrypoint script
CMD [ "/bin/bash", "/app/run.sh" ]