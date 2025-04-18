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
