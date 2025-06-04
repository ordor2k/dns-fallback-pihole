#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status

echo "Starting DNS Fallback Pi-hole installation..."

# Define project directory
PROJECT_DIR="/opt/dns-fallback"
CONFIG_FILE="${PROJECT_DIR}/config.ini"
PIHOLE_DNS_FILE="/etc/dnsmasq.d/01-pihole.conf" # Standard Pi-hole custom config location

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./install_dns_fallback.sh"
    exit 1
fi

# Create project directory
echo "Creating project directory: $PROJECT_DIR..."
mkdir -p "$PROJECT_DIR" || { echo "Error: Failed to create project directory '$PROJECT_DIR'. Exiting."; exit 1; }
chmod 755 "$PROJECT_DIR" # Ensure directory is executable by others for navigation

# Check for Python3
echo "Checking for python3..."
if ! command -v python3 &> /dev/null; then
    echo "python3 could not be found. Installing python3..."
    apt update && apt install -y python3 || { echo "Error: Failed to install python3. Exiting."; exit 1; }
fi
echo "python3 found."

# Check for pip3
echo "Checking for pip3..."
if ! command -v pip3 &> /dev/null; then
    echo "pip3 could not be found. Installing pip3..."
    apt update && apt install -y python3-pip || { echo "Error: Failed to install pip3. Exiting."; exit 1; }
fi
echo "pip3 found."

# Install Python dependencies
echo "Installing Python dependencies (Flask, dnslib)..."
pip_output=$(pip3 install Flask dnslib 2>&1)
if [ $? -ne 0 ]; then
    echo "Error: Failed to install Python dependencies."
    echo "Output: $pip_output"
    exit 1
fi
echo "Python dependencies installed."

# Copy Python scripts and config file
echo "Copying Python scripts and configuration file to $PROJECT_DIR..."
cp dns_fallback_proxy.py "$PROJECT_DIR/" || { echo "Error: Failed to copy proxy script. Exiting."; exit 1; }
cp dns_fallback_dashboard.py "$PROJECT_DIR/" || { echo "Error: Failed to copy dashboard script. Exiting."; exit 1; }
cp dns-fallback.service /etc/systemd/system/ || { echo "Error: Failed to copy proxy service file. Exiting."; exit 1; }
cp dns-fallback-dashboard.service /etc/systemd/system/ || { echo "Error: Failed to copy dashboard service file. Exiting."; exit 1; }
cp logrotate/dns-fallback /etc/logrotate.d/ || { echo "Error: Failed to copy logrotate config. Exiting."; exit 1; }

# Copy the config file, ensuring it exists for the first time setup
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Copying config.ini to $PROJECT_DIR..."
    cp config.ini "$PROJECT_DIR/" || { echo "Error: Failed to copy config.ini. Exiting."; exit 1; }
    chmod 644 "$CONFIG_FILE" # Set appropriate permissions
else
    echo "config.ini already exists at $PROJECT_DIR. Skipping copy."
fi

# Set ownership for the project directory and files (if running as root, this ensures root owns them)
chown -R root:root "$PROJECT_DIR" || { echo "Warning: Failed to set ownership for $PROJECT_DIR."; }
chmod 644 "$PROJECT_DIR"/*.py || { echo "Warning: Failed to set permissions for python scripts."; }
#chmod 755 "$PROJECT_DIR"/*.sh # If you add any executable shell scripts here


# Create log directory and ensure permissions (if not already done by system)
LOG_DIR="/var/log"
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR" || { echo "Error: Could not create log directory $LOG_DIR. Exiting."; exit 1; }
fi
touch /var/log/dns-fallback.log || { echo "Error: Could not create /var/log/dns-fallback.log. Exiting."; exit 1; }
touch /var/log/dns-fallback_dashboard.log || { echo "Error: Could not create /var/log/dns-fallback_dashboard.log. Exiting."; exit 1; }
chown root:root /var/log/dns-fallback.log || { echo "Warning: Could not set owner for /var/log/dns-fallback.log."; }
chown root:root /var/log/dns-fallback_dashboard.log || { echo "Warning: Could not set owner for /var/log/dns-fallback_dashboard.log."; }
chmod 640 /var/log/dns-fallback.log || { echo "Warning: Could not set permissions for /var/log/dns-fallback.log."; }
chmod 640 /var/log/dns-fallback_dashboard.log || { echo "Warning: Could not set permissions for /var/log/dns-fallback_dashboard.log."; }


# Configure Pi-hole to use the proxy
echo "Configuring Pi-hole to use DNS Fallback Proxy..."
if [ ! -f "$PIHOLE_DNS_FILE" ]; then
    echo "server=127.0.0.1#5353" > "$PIHOLE_DNS_FILE"
    echo "Created new Pi-hole configuration file: $PIHOLE_DNS_FILE"
else
    if ! grep -q "server=127.0.0.1#5353" "$PIHOLE_DNS_FILE"; then
        echo "Adding DNS Fallback entry to existing Pi-hole configuration file: $PIHOLE_DNS_FILE"
        echo "server=127.0.0.1#5353" >> "$PIHOLE_DNS_FILE"
    else
        echo "DNS Fallback entry already exists in Pi-hole configuration."
    fi
fi
chown pihole:pihole "$PIHOLE_DNS_FILE" || { echo "Warning: Failed to set ownership for Pi-hole config file."; }
chmod 644 "$PIHOLE_DNS_FILE" # Pi-hole needs to be able to read this


# Reload systemd daemon and enable services
echo "Reloading systemd daemon..."
systemctl daemon-reload || { echo "Error: Failed to reload systemd daemon. Exiting."; exit 1; }

echo "Enabling and starting DNS Fallback services..."
systemctl enable dns-fallback.service || { echo "Error: Failed to enable dns-fallback service. Exiting."; exit 1; }
systemctl start dns-fallback.service || { echo "Error: Failed to start dns-fallback service. Exiting."; exit 1; }

systemctl enable dns-fallback-dashboard.service || { echo "Error: Failed to enable dns-fallback-dashboard service. Exiting."; exit 1; }
systemctl start dns-fallback-dashboard.service || { echo "Error: Failed to start dns-fallback-dashboard service. Exiting."; exit 1; }

# Restart Pi-hole's dnsmasq service
echo "Restarting Pi-hole FTL (dnsmasq) service..."
sudo systemctl restart pihole-FTL.service || { echo "Warning: Failed to restart Pi-hole DNS. You may need to restart it manually."; }


echo "DNS Fallback Pi-hole installation complete!"
echo "You can check service status with: sudo systemctl status dns-fallback"
echo "You can view proxy logs with: tail -f /var/log/dns-fallback.log"
echo "You can view dashboard logs with: tail -f /var/log/dns-fallback_dashboard.log"
echo "Access the dashboard at: http://<your-pihole-ip>:<dashboard_port>"
