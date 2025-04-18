
# DNS Fallback for Pi-hole with Unbound

This project contains a resilient DNS setup for Pi-hole using Unbound, with fallback to public DNS servers and a web-based stats dashboard.
⚠️ Note: The fallback logic is handled entirely by the Python proxy (dns_fallback_proxy.py). Unbound remains a standard recursive resolver and is not configured with any forward zones.

## 📦 Installation Instructions

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
- `pi-hole.conf` – Sample Unbound config snippet

---

## ✍️ Author

[ordor2k](https://github.com/ordor2k)
=======
# dns-fallback-pihole
If Unbound fail to retrive DNS records, it will failover to public DNS servers to retrive it.

# DNS Fallback for Pi-hole with Unbound

This project contains a resilient DNS setup for Pi-hole using Unbound, with fallback to public DNS servers and a web-based stats dashboard.

## Features
- Primary: Recursive Unbound DNS
- Fallback: Public DNS (1.1.1.1, 8.8.8.8)
- Logging of fallback events
- Web dashboard showing fallback stats

## Files
- `dns_fallback_proxy.py`: Python DNS proxy with fallback logic
- `dns_fallback_dashboard.py`: Flask app showing live stats
- `dns-fallback.service`: systemd service for the proxy
- `dns-fallback-dashboard.service`: systemd service for the dashboard
- `pi-hole.conf`: Sample Unbound config

## Usage
1. Copy files to your system
2. Enable services with `sudo systemctl enable --now ...`
3. Access dashboard on `http://<your-ip>:8053`

## Author
[Your Name or Handle]