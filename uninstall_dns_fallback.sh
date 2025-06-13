#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status

echo "Starting DNS Fallback Pi-hole uninstallation..."

# Define project directory
PROJECT_DIR="/opt/dns-fallback"
PIHOLE_DNS_FILE="/etc/dnsmasq.d/01-pihole.conf" # Standard Pi-hole custom config location

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./uninstall_dns_fallback.sh"
    exit 1
fi

# Stop and disable services
echo "Stopping and disabling DNS Fallback services..."
systemctl stop dns-fallback-dashboard.service || { echo "Warning: Failed to stop dns-fallback-dashboard service."; }
systemctl disable dns-fallback-dashboard.service || { echo "Warning: Failed to disable dns-fallback-dashboard service."; }
systemctl stop dns-fallback.service || { echo "Warning: Failed to stop dns-fallback service."; }
systemctl disable dns-fallback.service || { echo "Warning: Failed to disable dns-fallback service."; }


# Remove systemd service files
echo "Removing systemd service files..."
rm -f /etc/systemd/system/dns-fallback.service || { echo "Warning: Failed to remove dns-fallback.service."; }
rm -f /etc/systemd/system/dns-fallback-dashboard.service || { echo "Warning: Failed to remove dns-fallback-dashboard.service."; }

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload || { echo "Warning: Failed to reload systemd daemon."; }


# Remove dns-fallback configuration from Pi-hole
echo "Removing dns-fallback configuration from Pi-hole..."
if [ -f "$PIHOLE_DNS_FILE" ]; then
    # Use sed to remove the exact line.
    # This specifically targets 'server=127.0.0.1#5353' if it exists.
    sed -i '/^server=127.0.0.1#5353$/d' "$PIHOLE_DNS_FILE"
    echo "DNS Fallback entry removed from Pi-hole configuration."
else
    echo "Pi-hole configuration file not found at $PIHOLE_DNS_FILE. Skipping Pi-hole config removal."
fi

# Restart Pi-hole's dnsmasq service to apply changes
echo "Restarting Pi-hole FTL (dnsmasq) service..."
pihole restartdns || { echo "Warning: Failed to restart Pi-hole DNS. You may need to restart it manually."; }


# Remove logrotate configuration
echo "Removing logrotate configuration..."
rm -f "/etc/logrotate.d/dns-fallback" || { echo "Warning: Failed to remove logrotate config."; }

# Remove project directory and its contents
echo "Removing DNS Fallback files from $PROJECT_DIR..."
rm -rf "$PROJECT_DIR" || { echo "Warning: Failed to remove $PROJECT_DIR. Manual cleanup may be required."; }

# Clean up PID files (if any were left behind unexpectedly)
echo "Cleaning up PID files..."
rm -f /var/run/dns-fallback.pid || { echo "Warning: Failed to remove /var/run/dns-fallback.pid (may not exist)."; }

# Remove the cloned repository directory
echo "Removing the cloned dns-fallback-pihole repository directory..."
rm -rf ../dns-fallback-pihole

echo "DNS Fallback Pi-hole uninstallation complete!"
