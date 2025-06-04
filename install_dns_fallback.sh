#!/bin/bash
set -e

echo "🔧 Installing DNS Fallback for Pi-hole..."

# 1. Update & install dependencies
apt update
apt install -y python3 python3-pip
pip3 install flask dnslib

# 2. Create target folder and copy core files
mkdir -p /usr/local/bin/dns-fallback
cp dns_fallback_proxy.py /usr/local/bin/dns-fallback/
cp dns_fallback_dashboard.py /usr/local/bin/dns-fallback/

# 3. Set permissions
chmod +x /usr/local/bin/dns-fallback/dns_fallback_proxy.py
chmod +x /usr/local/bin/dns-fallback/dns_fallback_dashboard.py

# 4. Log file
touch /var/log/dns-fallback.log
chown pihole:pihole /var/log/dns-fallback.log

# 5. Install logrotate config
cp logrotate/dns-fallback /etc/logrotate.d/dns-fallback

# 6. Systemd services (with environment variables for port configuration)
cat <<EOF > /etc/systemd/system/dns-fallback.service
[Unit]
Description=DNS Fallback Proxy
After=network.target

[Service]
User=pihole
Environment=DNS_LISTEN_PORT=5355
Environment=PRIMARY_DNS_PORT=5335
ExecStart=/usr/bin/python3 /usr/local/bin/dns-fallback/dns_fallback_proxy.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat <<EOF > /etc/systemd/system/dns-fallback-dashboard.service
[Unit]
Description=DNS Fallback Web Dashboard
After=network.target

[Service]
User=pihole
Environment=DASHBOARD_PORT=8053
ExecStart=/usr/bin/python3 /usr/local/bin/dns-fallback/dns_fallback_dashboard.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 7. Start services
systemctl daemon-reload
systemctl enable --now dns-fallback.service
systemctl enable --now dns-fallback-dashboard.service

echo "✅ Installation complete!"
echo "📌 Set Pi-hole custom DNS: 127.0.0.1#5355"
echo "🌐 Dashboard: http://<your-pi-ip>:8053"
