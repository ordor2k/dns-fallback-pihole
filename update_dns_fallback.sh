#!/bin/bash

echo "Starting DNS Fallback Pi-hole update process..."

# Find script's directory and cd there
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

PROJECT_DIR="/opt/dns-fallback"
SYSTEMD_DIR="/etc/systemd/system"
LOGROTATE_DIR="/etc/logrotate.d"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./update_dns_fallback.sh"
    exit 1
fi

if [ ! -d ".git" ]; then
    echo "Error: This script must be run from the root of the dns-fallback-pihole git repository."
    exit 1
fi

echo "Stopping DNS Fallback services..."
systemctl stop dns-fallback-dashboard.service || { echo "Warning: Dashboard service not running or failed to stop."; }
systemctl stop dns-fallback.service || { echo "Warning: Proxy service not running or failed to stop."; }

echo "Pulling latest changes from GitHub..."
git pull || { echo "Error: Failed to pull latest changes. Please check your network or git configuration."; exit 1; }
echo "Latest changes pulled successfully."

echo "Copying updated project files to system directories..."
cp dns_fallback_proxy.py "$PROJECT_DIR/" || { echo "Error: Failed to copy proxy script."; exit 1; }
cp dns_fallback_dashboard.py "$PROJECT_DIR/" || { echo "Error: Failed to copy dashboard script."; exit 1; }
cp dns-fallback.service "$SYSTEMD_DIR/" || { echo "Error: Failed to copy proxy service file."; exit 1; }
cp dns-fallback-dashboard.service "$SYSTEMD_DIR/" || { echo "Error: Failed to copy dashboard service file."; exit 1; }
if [ -f "logrotate/dns-fallback" ]; then
    cp logrotate/dns-fallback "$LOGROTATE_DIR/" || { echo "Error: Failed to copy logrotate config."; exit 1; }
else
    echo "Warning: logrotate/dns-fallback config not found, skipping."
fi

# Handle config.ini update (with optional replacement)
CONFIG_FILE="$PROJECT_DIR/config.ini"
REPLACE_CONFIG=0
for arg in "$@"; do
    if [ "$arg" == "--replace-config" ]; then
        REPLACE_CONFIG=1
    fi
done

if [ $REPLACE_CONFIG -eq 1 ]; then
    if [ -f "$CONFIG_FILE" ]; then
        BACKUP_FILE="$CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        echo "Backing up existing config.ini to $BACKUP_FILE"
        cp "$CONFIG_FILE" "$BACKUP_FILE" || { echo "Error: Failed to backup config.ini"; exit 1; }
    fi
    cp config.ini "$PROJECT_DIR/" || { echo "Error: Failed to copy config.ini"; exit 1; }
    echo "config.ini replaced."
else
    echo "NOTE: Your 'config.ini' file is NOT overwritten during update to preserve your settings."
    echo "      To replace it, re-run with: sudo ./update_dns_fallback.sh --replace-config"
    echo "      Please check 'CHANGELOG.md' for any new configuration options you might need to add manually to your 'config.ini'."
fi

echo "Setting appropriate file permissions..."
chmod 755 "$PROJECT_DIR"/dns_fallback_proxy.py || { echo "Warning: Failed to set permissions for proxy python script."; }
chmod 755 "$PROJECT_DIR"/dns_fallback_dashboard.py || { echo "Warning: Failed to set permissions for dashboard python script."; }
chmod 644 "$SYSTEMD_DIR"/dns-fallback.service || { echo "Warning: Failed to set permissions for proxy service file."; }
chmod 644 "$SYSTEMD_DIR"/dns-fallback-dashboard.service || { echo "Warning: Failed to set permissions for dashboard service file."; }
chmod 644 "$LOGROTATE_DIR"/dns-fallback || { echo "Warning: Failed to set permissions for logrotate config."; }

echo "Reloading systemd daemon..."
systemctl daemon-reload || { echo "Error: Failed to reload systemd daemon."; exit 1; }

echo "Restarting DNS Fallback services..."
systemctl restart dns-fallback.service || { echo "Error: Failed to restart proxy service."; exit 1; }
systemctl restart dns-fallback-dashboard.service || { echo "Error: Failed to restart dashboard service."; exit 1; }

echo "Restarting Pi-hole FTL (dnsmasq) service..."
pihole reloaddns || { echo "Warning: Failed to restart Pi-hole DNS. You may need to restart it manually."; }

echo "DNS Fallback Pi-hole update complete! 🎉"
echo "Please remember to check the CHANGELOG.md for any new configuration options or important notes."
