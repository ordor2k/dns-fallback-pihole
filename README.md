# 🛡️ DNS Fallback Pi-hole 🚀

Enhance your Pi-hole's reliability with this robust DNS proxy! 🌟 It automatically manages DNS traffic, directing queries to your local Unbound (or another primary DNS) and seamlessly switching to a public fallback DNS (like Cloudflare's 1.1.1.1 or Google's 8.8.8.8) when needed. This ensures continuous internet access and ad-blocking! 🚫

## 📂 Project Files

* **dns-fallback-dashboard.service**: ⚙️ Systemd service for the web dashboard.
* **dns-fallback.service**: ⚙️ Systemd service for the core DNS proxy.
* **dns_fallback_dashboard.py**: 🐍 Python script for the web-based dashboard interface.
* **dns_fallback_proxy.py**: 🐍 The central Python script handling DNS queries and fallback logic.
* **install_dns_fallback.sh**: 🛠️ Installation script for setting up the entire project.
* **pi-hole.conf**: ⚙️ Pi-hole configuration snippet to direct queries to the proxy.
* **uninstall_dns_fallback.sh**: 🛠️ Script for a complete removal of the project components.
* **CHANGELOG.md**: 📝 Documents all notable changes and updates.
* **LICENSE**: 📜 Details the project's licensing information.
* **README.md**: ℹ️ This documentation file you're reading.
* **logrotate/dns-fallback**: 🗂️ Configuration for rotating the proxy's log files.
* **config.ini**: ⚙️ **NEW!** The primary configuration file for all project settings.

## ✨ Key Enhancements

Your DNS Fallback Pi-hole now includes significant improvements:

* **Centralized Configuration (`config.ini`)**: ⚙️ All operational parameters are now easily manageable in one place.
* **Advanced Logging**: 🪵 Detailed, timestamped logs using Python's `logging` module for better insights and troubleshooting. 🔍
* **Robust Health Checks**: 🩺 Smarter detection of primary DNS server issues, with multiple checks and a configurable failure threshold before initiating a fallback. 🚦
* **Improved Installation & Uninstallation**: 🛠️ More resilient setup and cleanup processes, including automatic management of Python dependencies. 🧹
* **Optimized DNS Port**: 📡 The proxy now uses port **53053** by default, avoiding conflicts with mDNS (port 5353) for smoother integration. ➡️

## 🚀 Installation

Follow these steps to get DNS Fallback Pi-hole installed on your system:

1.  **Clone the Repository**: ⬇️
    ```bash
    git clone [https://github.com/ordor2k/dns-fallback-pihole.git](https://github.com/ordor2k/dns-fallback-pihole.git)
    cd dns-fallback-pihole
    ```

2.  **Configure `config.ini`**: ⚙️
    The `config.ini` file holds all default settings. **It's crucial to review and adjust these settings to match your specific network setup before proceeding.**

    Open the file in your preferred text editor:
    ```bash
    nano config.ini
    ```
    Pay special attention to these key parameters:

    * `primary_dns`: The IP address of your main DNS resolver (e.g., `127.0.0.1` for local Unbound). 🏠
    * `fallback_dns`: The IP address of the public DNS server for fallback (e.g., `1.1.1.1`, `8.8.8.8`). 🌐
    * `dns_port`: The port the DNS proxy will listen on. Default is **`53053`**. Pi-hole will forward queries here. 👂
    * `health_check_interval`: How often (in seconds) the primary DNS health is checked. 🩺
    * `failure_threshold`: Number of consecutive failed checks before a fallback. ⚠️
    * `dashboard_port`: The port for the web dashboard (default is `8053`). 📊

    Save any changes you make to `config.ini`. 💾

3.  **Run the Installation Script**: 🛠️
    Execute the installation script with root privileges:
    ```bash
    sudo ./install_dns_fallback.sh
    ```
    This script will:

    * Create the necessary `/opt/dns-fallback` directory. 📂
    * Install required Python libraries (`Flask`, `dnslib`). 🐍
    * Copy all project files, including your configured `config.ini`, to `/opt/dns-fallback`. ➡️
    * Set up and enable the `dns-fallback.service` (proxy) and `dns-fallback-dashboard.service` (dashboard) in `systemd`. ⚙️
    * Modify `/etc/dnsmasq.d/01-pihole.conf` to direct Pi-hole's upstream queries to your proxy's `dns_port`. ⚙️
    * Restart Pi-hole's DNS resolver. 🔄

## ⚙️ Configuration Details

All runtime settings are managed via the `config.ini` file, typically located at `/opt/dns-fallback/config.ini`. You can modify this file directly if you need to change settings after installation.

```ini
[Proxy]
# Primary DNS server, usually your local Unbound instance or another upstream DNS
primary_dns = 127.0.0.1

# Fallback DNS server to use if primary is unhealthy (e.g., Cloudflare, Google, OpenDNS)
fallback_dns = 1.1.1.1

# The port the DNS fallback proxy will listen on (Pi-hole will forward to this)
dns_port = 53053

# Interval (in seconds) between health checks of the primary DNS server
health_check_interval = 10

# Number of consecutive health check failures before switching to fallback DNS
failure_threshold = 3

# Path for the proxy's log file
log_file = /var/log/dns-fallback.log

# Path for the proxy's PID file
pid_file = /var/run/dns-fallback.pid

# Buffer size for UDP DNS packets
buffer_size = 4096

[Dashboard]
# The port the dashboard web interface will listen on
dashboard_port = 8053

# Path for the dashboard's log file. Can be the same as proxy log or separate.
# If you want a separate log for the dashboard, uncomment the line below:
# dashboard_log_file = /var/log/dns-fallback_dashboard.log
After updating config.ini:

Restart the proxy service for changes to take effect:
Bash

sudo systemctl restart dns-fallback.service
Restart the dashboard service (if its port or logging was changed):
Bash

sudo systemctl restart dns-fallback-dashboard.service
Crucially, if you modify dns_port in config.ini, you MUST also update pi-hole.conf and restart Pi-hole:
Bash

sudo sed -i 's/^server=127.0.0.1#OLD_PORT$/server=127.0.0.1#NEW_PORT/' /etc/dnsmasq.d/01-pihole.conf
# Replace OLD_PORT with your previous port and NEW_PORT with the new one (e.g., 53053)
sudo pihole restartdns
✅ Verification & Usage
Confirm your installation is working correctly:

Check Service Status: 🚦

Bash

sudo systemctl status dns-fallback.service
sudo systemctl status dns-fallback-dashboard.service
Ensure both show active (running). ✅

Monitor Logs: 🪵

Proxy Logs:
Bash

tail -f /var/log/dns-fallback.log
Dashboard Logs:
Bash

tail -f /var/log/dns-fallback_dashboard.log
Look for initialization messages, health check updates, and query forwarding. 🔍

Access the Web Dashboard: 📊
Open your web browser and navigate to: http://<Your-Pihole-IP-Address>:<Dashboard-Port> (e.g., http://192.168.1.100:8053). 🌐

Test DNS Resolution: ❓

Direct Proxy Test (from Pi-hole machine):
Bash

dig google.com @127.0.0.1 -p 53053
Via Pi-hole (from any client device):
Bash

dig example.com
Confirm resolution and check Pi-hole's query log. 🧐
Test Fallback Mechanism: ⚠️
Simulate a failure of your primary DNS (e.g., Unbound):

Stop primary DNS:
Bash

sudo systemctl stop unbound
(Adjust service name as needed). 🛑
Monitor dns-fallback.log: Observe messages indicating health check failures and the proxy switching to fallback. 🪵
Verify DNS still works: Test resolution from a client device. 🌐
Restart primary DNS:
Bash

sudo systemctl start unbound
Monitor dns-fallback.log: Confirm the proxy switches back. 🪵
Verify DNS: Ensure resolution is now via the primary DNS. ❓
🗑️ Uninstallation
To completely remove DNS Fallback Pi-hole from your system:

Bash

cd dns-fallback-pihole # Ensure you are in the project directory
sudo ./uninstall_dns_fallback.sh
This script will safely stop/disable services, remove all installed files, clean logrotate configurations, and restore Pi-hole's original upstream DNS settings. 🧹

🔒 Security Notes
The proxy listens on 127.0.0.1 (localhost) by default, making it accessible only from the Pi-hole machine itself. This is the recommended and most secure configuration. 🛡️
The dashboard listens on 0.0.0.0 by default, allowing access from any device on your local network. It is crucial to avoid exposing your Pi-hole directly to the public internet (e.g., via router port forwarding) if you are not using proper security measures, as this would expose your dashboard as well. ⚠️
🛠️ Troubleshooting
Services not starting: Check sudo systemctl status <service_name>.service and sudo journalctl -u <service_name>.service for specific error messages. 🔍
DNS resolution issues: Verify the dns_port in config.ini matches the setting in /etc/dnsmasq.d/01-pihole.conf. Review dns-fallback.log for any errors. Ensure your primary DNS (e.g., Unbound) is operational. ❓
📜 License
This project is licensed under the MIT License - see the LICENSE file for details. 📝
