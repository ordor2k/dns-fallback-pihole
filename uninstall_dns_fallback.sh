#!/bin/bash
set -e

echo "🗑️ Uninstalling DNS Fallback for Pi-hole..."

# 1. Stop and disable services
echo "❌ Stopping services..."
systemctl stop dns-fallback.service 2>/dev/null || true
systemctl disable dns-fallback.service 2>/dev/null || true

systemctl stop dns-fallback-dashboard.service 2>/dev/null || true
systemctl disable dns-fallback-dashboard.service 2>/dev/null || true

# 2. Remove systemd service files
echo "🧹 Removing systemd service definitions..."
rm -f /etc/systemd/system/dns-fallback.service
rm -f /etc/systemd/system/dns-fallback-dashboard.service
systemctl daemon-reload

# 3. Ask user if we should delete all installed files and logs
echo
read -rp "🗃️ Do you want to delete all installed files and logs (including this project folder)? [y/N]: " delete_choice

if [[ "$delete_choice" =~ ^[Yy]$ ]]; then
    echo "🚮 Deleting application files..."
    rm -rf /usr/local/bin/dns-fallback
    rm -f /var/log/dns-fallback.log

    # Try to delete current folder if it's dns-fallback-pihole
    current_dir="$(basename "$PWD")"
    if [[ "$current_dir" == "dns-fallback-pihole" ]]; then
        cd .. || exit
        rm -rf dns-fallback-pihole
        echo "🗂️ Deleted project directory dns-fallback-pihole"
    fi

    echo "✅ All application files removed."
else
    echo "📦 Installed files and folder preserved."
fi

echo "✅ Uninstall complete."
