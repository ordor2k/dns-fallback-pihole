# DNS Fallback for Pi-hole with Unbound

This project provides a resilient DNS solution for Pi-hole using Unbound as the primary recursive resolver and a Python proxy to handle fallback to public DNS servers (like 1.1.1.1 or 8.8.8.8) in case Unbound fails. It includes a live web dashboard to monitor DNS queries and fallbacks.

⚠️ **Note:** The fallback logic is handled entirely by the Python proxy (`dns_fallback_proxy.py`). Unbound is not configured with any forward zones and continues to operate as a standard recursive resolver.

---

## ⚡ Automatic Installation (Recommended)

```bash
git clone https://github.com/ordor2k/dns-fallback-pihole.git
cd dns-fallback-pihole
sudo bash install_dns_fallback.sh
```

Once completed:
- Set Pi-hole custom DNS to: `127.0.0.1#5353`
- Access the dashboard via: `http://<your-pi-ip>:8053`

To uninstall:
```bash
sudo bash uninstall_dns_fallback.sh
```

---

## 🛠️ Manual Installation (Advanced)

Make sure you have **Pi-hole and Unbound** already installed on your system.

### 1. Clone this repo

```bash
git clone https://github.com/ordor2k/dns-fallback-pihole.git
cd dns-fallback-pihole
```

### 2. Install dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip
sudo pip3 install flask dnslib
```

### 3. Copy scripts and services

```bash
sudo cp dns_fallback_proxy.py /usr/local/bin/
sudo cp dns_fallback_dashboard.py /usr/local/bin/
sudo chmod +x /usr/local/bin/*.py
sudo cp dns-fallback*.service /etc/systemd/system/
sudo cp logrotate/dns-fallback /etc/logrotate.d/dns-fallback
```

### 4. Ensure Unbound is Listening on Port 5335

Edit `/etc/unbound/unbound.conf.d/pi-hole.conf` to include:

```ini
server:
  interface: 127.0.0.1
  port: 5335
  ...
```

### 5. Enable and start the services

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dns-fallback.service
sudo systemctl enable --now dns-fallback-dashboard.service
```

### 6. Configure Pi-hole to use the proxy

In Pi-hole's **DNS settings**, set `127.0.0.1#5353` as the only upstream DNS server.

### 7. View the dashboard

Open in your browser:  
`http://<your-pi-ip>:8053`

---

## ✅ Features

- Uses Unbound as the primary recursive resolver
- Fallbacks to public DNS if Unbound fails or times out
- Logs and counts fallback events
- Web dashboard with stats, charts, and CSV downloads
- Log cleaner and retention manager

---

## 📁 Included Files

- `dns_fallback_proxy.py` – DNS proxy with fallback logic
- `dns_fallback_dashboard.py` – Flask web dashboard
- `dns-fallback.service` – systemd service for the proxy
- `dns-fallback-dashboard.service` – systemd service for the dashboard
- `install_dns_fallback.sh` – Auto installation script
- `uninstall_dns_fallback.sh` – Auto uninstall script

---

## ✍️ Author

[ordor2k](https://github.com/ordor2k)
