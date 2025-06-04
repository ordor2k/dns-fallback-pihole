#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status

echo "Starting DNS Fallback Pi-hole update process..."

# Define project directory
PROJECT_DIR="/opt/dns-fallback"
SYSTEMD_DIR="/etc/systemd/system"
LOGROTATE_DIR="/etc/logrotate.d"

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./update_dns_fallback.sh"
    exit 1
fi

# Ensure we are in the project's git repository directory for pulling
if [ ! -d ".git" ]; then
    echo "Error: This script must be run from the root of the dns-fallback-pihole git repository."
    echo "Please 'cd' into the directory where you cloned the project (e.g., /home/pi/dns-fallback-pihole)."
    exit 1
fi

# Stop services to avoid conflicts during file replacement
echo "Stopping DNS Fallback services..."
systemctl stop dns-fallback-dashboard.service || { echo "Warning: Dashboard service not running or failed to stop."; }
systemctl stop dns-fallback.service || { echo "Warning: Proxy service not running or failed to stop."; }

# Pull latest changes from git
echo "Pulling latest changes from GitHub..."
git pull || { echo "Error: Failed to pull latest changes. Please check your network or git configuration."; exit 1; }
echo "Latest changes pulled successfully."

# Copy updated files to their system locations
echo "Copying updated project files to system directories..."
cp dns_fallback_proxy.py "$PROJECT_DIR/" || { echo "Error: Failed to copy proxy script."; exit 1; }
cp dns_fallback_dashboard.py "$PROJECT_DIR/" || { echo "Error: Failed to copy dashboard script."; exit 1; }
cp dns-fallback.service "$SYSTEMD_DIR/" || { echo "Error: Failed to copy proxy service file."; exit 1; }
cp dns-fallback-dashboard.service "$SYSTEMD_DIR/" || { echo "Error: Failed to copy dashboard service file."; exit 1; }
cp logrotate/dns-fallback "$LOGROTATE_DIR/" || { echo "Error: Failed to copy logrotate config."; exit 1; }

# Important: DO NOT overwrite config.ini, as it's user-configured.
echo "NOTE: Your 'config.ini' file is NOT overwritten during update to preserve your settings."
echo "      Please check 'CHANGELOG.md' for any new configuration options you might need to add manually to your 'config.ini'."


# Set permissions for copied files (ensure they are correct after copy)
echo "Setting appropriate file permissions..."
chmod 644 "$PROJECT_DIR"/*.py || { echo "Warning: Failed to set permissions for python scripts."; }
chmod 644 "$SYSTEMD_DIR"/dns-fallback.service || { echo "Warning: Failed to set permissions for proxy service file."; }
chmod 644 "$SYSTEMD_DIR"/dns-fallback-dashboard.service || { echo "Warning: Failed to set permissions for dashboard service file."; }
chmod 644 "$LOGROTATE_DIR"/dns-fallback || { echo "Warning: Failed to set permissions for logrotate config."; }

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload || { echo "Error: Failed to reload systemd daemon."; exit 1; }

# Start services
echo "Starting DNS Fallback services..."
systemctl start dns-fallback.service || { echo "Error: Failed to start proxy service."; exit 1; }
systemctl start dns-fallback-dashboard.service || { echo "Error: Failed to start dashboard service."; exit 1; }

# Restart Pi-hole's dnsmasq service
echo "Restarting Pi-hole FTL (dnsmasq) service..."
pihole restartdns || { echo "Warning: Failed to restart Pi-hole DNS. You may need to restart it manually."; }

echo "DNS Fallback Pi-hole update complete! 🎉"
echo "Please remember to check the CHANGELOG.md for any new configuration options or important notes."
