# DNS Fallback for Pi-hole with Unbound

This project contains a resilient DNS setup for Pi-hole using Unbound, with fallback to public DNS servers and a web-based stats dashboard.

## 📦 Installation Instructions

Run these steps on a system that already has Pi-hole and Unbound installed:

### 1. Clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/dns-fallback-pihole.git
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

Make sure your `/etc/unbound/unbound.conf.d/pi-hole.conf` includes this:

```ini
server:
  interface: 127.0.0.1
  port: 5335
  ...
```

🔁 **Note:** The fallback logic is handled by the Python proxy, not by Unbound itself.

### 5. Enable the services

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dns-fallback.service
sudo systemctl enable --now dns-fallback-dashboard.service
```

### 6. Update Pi-hole DNS

In Pi-hole settings:
- Disable all default upstream DNS options
- Set `127.0.0.1#5353` as the upstream server

### 7. View dashboard

Visit `http://<your-pi-ip>:8053` in your browser.
