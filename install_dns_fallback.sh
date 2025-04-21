#!/bin/bash
set -e

echo "🔧 Installing DNS Fallback for Pi-hole..."

# 1. Prompt installation type
echo
echo "Choose installation type:"
echo "  1) Install Proxy + Dashboard"
echo "  2) Install Proxy only"
read -rp "Enter your choice [1 or 2]: " choice

# 2. Install dependencies
apt update
apt install -y python3 python3-pip
pip3 install flask dnslib

# 3. Create target folder and copy files
mkdir -p /usr/local/bin/dns-fallback
cp dns_fallback_proxy.py /usr/local/bin/dns-fallback/
chmod +x /usr/local/bin/dns-fallback/dns_fallback_proxy.py

if [[ "$choice" == "1" ]]; then
    cp dns_fallback_dashboard.py /usr/local/bin/dns-fallback/
    chmod +x /usr/local/bin/dns-fallback/dns_fallback_dashboard.py
fi

# 4. Create log file
touch /var/log/dns-fallback.log
chown $USER:$(id -gn $USER) /var/log/dns-fallback.log

# 5. Create systemd service for proxy
cat <<EOF > /etc/systemd/system/dns-fallback.service
[Unit]
Description=DNS Fallback Proxy
After=network.target

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/dns-fallback/dns_fallback_proxy.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 6. Create systemd service for dashboard if selected
if [[ "$choice" == "1" ]]; then
    cat <<EOF > /etc/systemd/system/dns-fallback-dashboard.service
[Unit]
Description=DNS Fallback Web Dashboard
After=network.target

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/dns-fallback/dns_fallback_dashboard.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF
fi

# 7. Enable and start selected services
systemctl daemon-reload
systemctl enable --now dns-fallback.service

if [[ "$choice" == "1" ]]; then
    systemctl enable --now dns-fallback-dashboard.service
fi

# 8. Final message
echo "✅ Installation complete!"
echo "📌 Set Pi-hole custom DNS: 127.0.0.1#5353"
[[ "$choice" == "1" ]] && echo "🌐 Dashboard: http://<your-pi-ip>:8053"
