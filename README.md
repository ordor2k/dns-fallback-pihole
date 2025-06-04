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
* **update_dns_fallback.sh**: 🔄 **NEW!** Script for easily updating the project files.
* **CHANGELOG.md**: 📝 Documents all notable changes and updates.
* **LICENSE**: 📜 Details the project's licensing information.
* **README.md**: ℹ️ This documentation file you're reading.
* **logrotate/dns-fallback**: 🗂️ Configuration for rotating the proxy's log files.
* **config.ini**: ⚙️ **NEW!** The primary configuration file for all project settings.

---

## ✨ Key Enhancements

Your DNS Fallback Pi-hole now includes significant improvements:

* **Centralized Configuration**: ⚙️ All operational parameters are now easily managed in one place via `config.ini`.
* **Advanced Logging**: 🪵 Detailed, timestamped logs using Python's `logging` module for better insights and troubleshooting. 🔍
* **Robust Health Checks**: 🩺 Smarter detection of primary DNS server issues, with multiple checks and a configurable failure threshold before initiating a fallback. 🚦
* **Improved Installation & Uninstallation**: 🛠️ More resilient setup and cleanup processes, including automatic management of Python dependencies. 🧹
* **Optimized DNS Port**: 📡 The proxy now uses port **5355** by default, avoiding conflicts with mDNS (port 5353) for smoother integration. ➡️

---

## 🚀 Installation

Follow these steps to get DNS Fallback Pi-hole installed on your system.

### Automated Installation

1.  **Clone the Repository**: ⬇️
    ```bash
    git clone https://github.com/ordor2k/dns-fallback-pihole.git
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
    * `dns_port`: The port the DNS proxy will listen on. Default is **`5355`**. Pi-hole will forward queries here. 👂
    * `health_check_interval`: How often (in seconds) the primary DNS health is checked. 🩺
    * `failure_threshold`: Number of consecutive failed checks before a fallback. ⚠️
    * `dashboard_port`: The port for the web dashboard (default is `8053`). 📊

    Save any changes you make to `config.ini`. 💾

3.  **Run the Installation Script**: 🛠️
    Execute the installation script with root privileges:
    ```bash
    sudo bash install_dns_fallback.sh
    ```
    This script will:

    * Create the necessary `/opt/dns-fallback` directory. 📂
    * Install required Python libraries (`Flask`, `dnslib`). 🐍
    * Copy all project files, including your configured `config.ini`, to `/opt/dns-fallback`. ➡️
    * Set up and enable the `dns-fallback.service` (proxy) and `dns-fallback-dashboard.service` (dashboard) in `systemd`. ⚙️
    * Modify `/etc/dnsmasq.d/01-pihole.conf` to direct Pi-hole's upstream queries to your proxy's `dns_port`. ⚙️
    * Restart Pi-hole's DNS resolver. 🔄

### Manual Installation (Advanced)

For users who prefer a step-by-step installation process, you can follow these manual instructions.

**Prerequisites (Ensure these are installed first):**

* **Pi-hole:** Already installed and configured.
* **Unbound (Optional but Recommended):** If you're using it as your primary DNS resolver.
* **Python 3.9+:**
    ```bash
    sudo apt update
    sudo apt install -y python3 python3-pip
    ```

**Manual Installation Steps:**

1.  **Clone the Repository (if you haven't already):**
    ```bash
    git clone [https://github.com/ordor2k/dns-fallback-pihole.git](https://github.com/ordor2k/dns-fallback-pihole.git)
    cd dns-fallback-pihole
    ```

2.  **Define Project Paths:**
    We'll use `/opt/dns-fallback` as the base installation directory.
    ```bash
    PROJECT_DIR="/opt/dns-fallback"
    PIHOLE_DNS_FILE="/etc/dnsmasq.d/01-pihole.conf"
    LOGROTATE_CONFIG="/etc/logrotate.d/dns-fallback"
    SYSTEMD_DIR="/etc/systemd/system"
    ```

3.  **Create Project Directory:** 📁
    ```bash
    sudo mkdir -p "$PROJECT_DIR"
    sudo chmod 755 "$PROJECT_DIR"
    ```

4.  **Copy Project Files:** ➡️
    Copy the Python scripts, `config.ini`, service files, and logrotate config to their respective locations.

    ```bash
    # Copy Python scripts and config.ini
    sudo cp dns_fallback_proxy.py "$PROJECT_DIR/"
    sudo cp dns_fallback_dashboard.py "$PROJECT_DIR/"
    sudo cp config.ini "$PROJECT_DIR/"

    # Copy Systemd service files
    sudo cp dns-fallback.service "$SYSTEMD_DIR/"
    sudo cp dns-fallback-dashboard.service "$SYSTEMD_DIR/"

    # Copy Logrotate configuration
    sudo cp logrotate/dns-fallback "$LOGROTATE_CONFIG"
    ```

5.  **Set File Permissions and Ownership:** 🔐
    Ensure scripts are executable and files are owned by root, with appropriate read permissions.

    ```bash
    sudo chown -R root:root "$PROJECT_DIR"
    sudo chmod 644 "$PROJECT_DIR"/*.py
    sudo chmod 644 "$PROJECT_DIR"/config.ini

    sudo chmod 644 "$SYSTEMD_DIR"/dns-fallback.service
    sudo chmod 644 "$SYSTEMD_DIR"/dns-fallback-dashboard.service

    sudo chmod 644 "$LOGROTATE_CONFIG"
    ```

6.  **Create Log Files and Set Permissions:** 🪵
    Ensure log files exist and have correct permissions for the services to write to them.

    ```bash
    sudo touch /var/log/dns-fallback.log
    sudo touch /var/log/dns-fallback_dashboard.log
    sudo chown root:root /var/log/dns-fallback.log /var/log/dns-fallback_dashboard.log
    sudo chmod 640 /var/log/dns-fallback.log /var/log/dns-fallback_dashboard.log
    ```

7.  **Install Python Dependencies:** 🐍
    ```bash
    pip3 install Flask dnslib
    ```

8.  **Configure Pi-hole to Use the Proxy:** ⚙️
    You need to tell Pi-hole to forward its DNS queries to your proxy running on `127.0.0.1` at the configured `dns_port` (default `5355`).

    ```bash
    # IMPORTANT: Ensure dns_port in /opt/dns-fallback/config.ini matches this!
    PROXY_PORT=$(grep '^dns_port' "$PROJECT_DIR/config.ini" | cut -d'=' -f2 | tr -d '[:space:]')
    echo "Configuring Pi-hole to use proxy on port $PROXY_PORT..."

    if [ ! -f "$PIHOLE_DNS_FILE" ]; then
        echo "server=127.0.0.1#$PROXY_PORT" | sudo tee "$PIHOLE_DNS_FILE" > /dev/null
        echo "Created new Pi-hole configuration file: $PIHOLE_DNS_FILE"
    else
        # Add the line if it doesn't exist
        if ! grep -q "server=127.0.0.1#$PROXY_PORT" "$PIHOLE_DNS_FILE"; then
            echo "Adding DNS Fallback entry to existing Pi-hole configuration file: $PIHOLE_DNS_FILE"
            echo "server=127.0.0.1#$PROXY_PORT" | sudo tee -a "$PIHOLE_DNS_FILE" > /dev/null
        else
            echo "DNS Fallback entry already exists in Pi-hole configuration."
        fi
        # Ensure only the correct port is listed if an old one existed (e.g., from prior manual setup)
        if grep -q "server=127.0.0.1#5353" "$PIHOLE_DNS_FILE" && [ "$PROXY_PORT" != "5353" ]; then
             echo "Detected old proxy port 5353. Removing it..."
             sudo sed -i '/^server=127.0.0.1#5353$/d' "$PIHOLE_DNS_FILE"
        fi
    fi
    sudo chown pihole:pihole "$PIHOLE_DNS_FILE"
    sudo chmod 644 "$PIHOLE_DNS_FILE"
    ```

9.  **Reload Systemd and Start Services:** 🔄
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable dns-fallback.service
    sudo systemctl start dns-fallback.service
    sudo systemctl enable dns-fallback-dashboard.service
    sudo systemctl start dns-fallback-dashboard.service
    ```

10. **Restart Pi-hole's DNS Resolver:** 🔁
    ```bash
    pihole restartdns
    ```

---

## 🔄 Updating the Project

To easily update your DNS Fallback Pi-hole installation to the latest version:

1.  **Navigate to your cloned project directory:**
    ```bash
    cd dns-fallback-pihole # (e.g., /home/pi/dns-fallback-pihole)
    ```

2.  **Run the update script:**
    ```bash
    sudo ./update_dns_fallback.sh
    ```

This script will:
* Stop the proxy and dashboard services.
* Pull the latest changes from the GitHub repository (`git pull`).
* Copy updated Python scripts, `systemd` service files, and `logrotate` configuration to their respective system locations.
* **Preserve your `config.ini` file**, so your custom settings remain intact.
* Reload `systemd` and restart both services.
* Restart Pi-hole's DNS resolver.

**Important:** After updating, always check the `CHANGELOG.md` for any new configuration options that might have been added to the default `config.ini`. You may need to manually add these to your existing `/opt/dns-fallback/config.ini` file.

---

## ✅ Verification & Usage

Confirm your installation is working correctly:

1.  **Check Service Status**: 🚦
    ```bash
    sudo systemctl status dns-fallback.service
    sudo systemctl status dns-fallback-dashboard.service
    ```
    Ensure both show `active (running)`. ✅

2.  **Monitor Logs**: 🪵
    * **Proxy Logs**:
        ```bash
        tail -f /var/log/dns-fallback.log
        ```
    * **Dashboard Logs**:
        ```bash
        tail -f /var/log/dns-fallback_dashboard.log
        ```
    Look for initialization messages, health check updates, and query forwarding. 🔍

3.  **Access the Web Dashboard**: 📊
    Open your web browser and navigate to: `http://<Your-Pihole-IP-Address>:<Dashboard-Port>` (e.g., `http://192.168.1.100:8053`). 🌐

4.  **Test DNS Resolution**: ❓
    * **Direct Proxy Test (from Pi-hole machine)**:
        ```bash
        dig google.com @127.0.0.1 -p 5355
        ```
    * **Via Pi-hole (from any client device)**:
        ```bash
        dig example.com
        ```
    Confirm resolution and check Pi-hole's query log. 🧐

5.  **Test Fallback Mechanism**: ⚠️
    Simulate a failure of your primary DNS (e.g., Unbound):

    * **Stop primary DNS**:
        ```bash
        sudo systemctl stop unbound
        ```
        (Adjust service name as needed). 🛑
    * **Monitor `dns-fallback.log`**: Observe messages indicating health check failures and the proxy switching to fallback. 🪵
    * **Verify DNS still works**: Test resolution from a client device. 🌐
    * **Restart primary DNS**:
        ```bash
        sudo systemctl start unbound
        ```
    * **Monitor `dns-fallback.log`**: Confirm the proxy switches back. 🪵
    * **Verify DNS**: Ensure resolution is now via the primary DNS. ❓

---

## 🗑️ Uninstallation Procedure

The uninstallation process is automated by the `uninstall_dns_fallback.sh` script. This script meticulously removes all components installed by the project.

**Steps:**

1.  **Navigate to the project directory:**
    ```bash
    cd /opt/dns-fallback # Or wherever you cloned/installed the project
    ```

2.  **Execute the uninstallation script:** 🛠️
    ```bash
    sudo ./uninstall_dns_fallback.sh
    ```

**What the `uninstall_dns_fallback.sh` script does:**

* Stops and disables the `dns-fallback.service` and `dns-fallback-dashboard.service`.
* Removes the `systemd` service unit files from `/etc/systemd/system/`.
* Reloads the `systemd` daemon to register the removal of services.
* Removes the `server=127.0.0.1#5355` (or your configured port) line from `/etc/dnsmasq.d/01-pihole.conf`, reverting Pi-hole's upstream DNS configuration.
* Restarts Pi-hole's DNS resolver (`pihole-FTL`) to apply the configuration change.
* Removes the logrotate configuration file for `dns-fallback` from `/etc/logrotate.d/`.
* Deletes the entire project directory (`/opt/dns-fallback/`) and its contents.
* Cleans up any lingering PID files in `/var/run/`.

---

## 🔒 Security Notes

* The DNS fallback proxy listens on `127.0.0.1` (localhost) by default, making it accessible only from the Pi-hole machine itself. This is the **recommended and most secure configuration**. 🛡️
* The dashboard listens on `0.0.0.0` by default, allowing access from any device on your local network. **It is crucial to avoid exposing your Pi-hole directly to the public internet** (e.g., via router port forwarding) if you are not using proper security measures, as this would expose your dashboard as well. ⚠️

---

## 🛠️ Troubleshooting

* **Services not starting**: Check `sudo systemctl status <service_name>.service` and `sudo journalctl -u <service_name>.service` for specific error messages. 🔍
* **DNS resolution issues**: Verify the `dns_port` in `config.ini` matches the setting in `/etc/dnsmasq.d/01-pihole.conf`. Review `dns-fallback.log` for any errors. Ensure your primary DNS (e.g., Unbound) is operational. ❓

---

## 📜 License

This project is licensed under the MIT License - see the `LICENSE` file for details. 📝
