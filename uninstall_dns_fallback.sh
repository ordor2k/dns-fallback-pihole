#!/bin/bash

echo "🧹 Uninstalling DNS Fallback..."

# Stop and disable services
systemctl stop dns-fallback.service dns-fallback-dashboard.service
systemctl disable dns-fallback.service dns-fallback-dashboard.service

# Remove files
rm -f /etc/systemd/system/dns-fallback.service
rm -f /etc/systemd/system/dns-fallback-dashboard.service
rm -rf /usr/local/bin/dns-fallback
rm -f /var/log/dns-fallback.log

# Remove unbound config if still present
rm -f /etc/unbound/unbound.conf.d/pi-hole.conf

# Reload systemd
systemctl daemon-reload

echo "🗑️ DNS Fallback removed."
