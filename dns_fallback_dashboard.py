import os
import sys
import logging
import logging.handlers
import configparser
import time
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for

# --- Configuration File Path ---
CONFIG_FILE = "/opt/dns-fallback/config.ini"

# --- Load Configuration ---
config = configparser.ConfigParser()
if not os.path.exists(CONFIG_FILE):
    # Fallback to defaults if config is missing for dashboard, but log a critical error
    LOG_FILE_PATH = "/var/log/dns-fallback.log"
    PID_FILE_PATH = "/var/run/dns-fallback.pid"
    DASHBOARD_PORT = 8053
    DASHBOARD_LOG_FILE = LOG_FILE_PATH # Default to main log file if not specified
else:
    try:
        config.read(CONFIG_FILE)
        # Dashboard settings
        # Dashboard needs proxy's log and PID files to display status
        LOG_FILE_PATH = config.get('Proxy', 'log_file', fallback="/var/log/dns-fallback.log")
        PID_FILE_PATH = config.get('Proxy', 'pid_file', fallback="/var/run/dns-fallback.pid")
        DASHBOARD_PORT = config.getint('Dashboard', 'dashboard_port', fallback=8053)
        # Check for separate dashboard log file, default to main log file if not set
        DASHBOARD_LOG_FILE = config.get('Dashboard', 'dashboard_log_file', fallback=LOG_FILE_PATH)
    except Exception as e:
        # If config parsing fails, fallback to defaults
        LOG_FILE_PATH = "/var/log/dns-fallback.log"
        PID_FILE_PATH = "/var/run/dns-fallback.pid"
        DASHBOARD_PORT = 8053
        DASHBOARD_LOG_FILE = LOG_FILE_PATH
        sys.stderr.write(f"CRITICAL: Error reading configuration file {CONFIG_FILE} for dashboard: {e}. Using default settings.\n")

# --- Logger Setup for Dashboard ---
dashboard_log_dir = os.path.dirname(DASHBOARD_LOG_FILE)
if not os.path.exists(dashboard_log_dir):
    try:
        os.makedirs(dashboard_log_dir, exist_ok=True)
    except OSError as e:
        sys.exit(f"Error: Could not create dashboard log directory {dashboard_log_dir}: {e}")

dashboard_logger = logging.getLogger('dns_fallback_dashboard')
dashboard_logger.setLevel(logging.INFO)

file_handler_dashboard = logging.handlers.RotatingFileHandler(
    DASHBOARD_LOG_FILE,
    maxBytes=5 * 1024 * 1024, # Smaller dashboard log file size
    backupCount=2
)
formatter_dashboard = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler_dashboard.setFormatter(formatter_dashboard)
dashboard_logger.addHandler(file_handler_dashboard)

# Console handler for dashboard (useful for Flask's output during development/testing)
console_handler_dashboard = logging.StreamHandler(sys.stdout)
console_handler_dashboard.setFormatter(formatter_dashboard)
dashboard_logger.addHandler(console_handler_dashboard)

dashboard_logger.info("DNS Fallback Dashboard logger initialized.")
# --- End Logger Setup ---

app = Flask(__name__)

# HTML template for the dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="10"> <title>DNS Fallback Pi-hole Dashboard</title>
    <style>
        body { font-family: 'Arial', sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
        .container { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 900px; margin: auto; }
        h1, h2 { color: #0056b3; }
        pre { background-color: #eee; padding: 15px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; max-height: 500px; }
        .status { margin-bottom: 20px; padding: 10px; border-radius: 5px; font-weight: bold; }
        .status.ok { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .status.warning { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .status.error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .refresh-button { padding: 8px 15px; background-color: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin-top: 10px; }
        .refresh-button:hover { background-color: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>DNS Fallback Pi-hole Dashboard</h1>

        <p>This dashboard provides a quick overview of the DNS Fallback Proxy status.</p>

        <div class="status {{ status_class }}">
            <p><strong>Proxy Status:</strong> {{ pid_status }}</p>
            <p><strong>Active DNS:</strong> {{ active_dns_server }}</p>
            <p><strong>Last Status Update:</strong> {{ last_status_update }}</p>
            <p><strong>Health Check Interval:</strong> {{ health_check_interval }} seconds</p>
            <p><strong>Failure Threshold:</strong> {{ failure_threshold }} consecutive failures</p>
        </div>

        <a href="{{ url_for('index') }}" class="refresh-button">Refresh Now</a>

        <h2>Proxy Log ({{ log_file_path }})</h2>
        <pre>{{ log_content }}</pre>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """
    Renders the main dashboard page, displaying proxy status and logs.
    """
    dashboard_logger.info(f"Dashboard accessed by {request.remote_addr}.")

    log_content = "Log file not found or inaccessible."
    pid_status = "PID file not found. Proxy may not be running."
    active_dns_server = "Unknown"
    last_status_update = "N/A"
    status_class = "error" # Default status

    # Get configuration values for display
    primary_dns = config.get('Proxy', 'primary_dns', fallback='N/A')
    fallback_dns = config.get('Proxy', 'fallback_dns', fallback='N/A')
    health_check_interval = config.get('Proxy', 'health_check_interval', fallback='N/A')
    failure_threshold = config.get('Proxy', 'failure_threshold', fallback='N/A')

    # Read log file content
    try:
        if os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, 'r') as f:
                log_content = f.read()
            # Attempt to determine status from log content
            if log_content:
                latest_switch_to_primary = None
                latest_switch_to_fallback = None
                proxy_started = False
                
                # Iterate lines in reverse for efficiency
                for line in reversed(log_content.splitlines()):
                    if "DNS Fallback Proxy listening on" in line:
                        proxy_started = True
                    if "Primary DNS is now healthy. Switching back." in line:
                        latest_switch_to_primary = line
                        break # Found the most recent switch to primary
                    elif "Primary DNS is unhealthy" in line and "Switching to fallback" in line:
                        latest_switch_to_fallback = line
                        break # Found the most recent switch to fallback
                
                if latest_switch_to_primary:
                    active_dns_server = f"Primary ({primary_dns})"
                    status_class = "ok"
                    try:
                        # Extract timestamp from log line: YYYY-MM-DD HH:MM:SS,ms - LEVEL - Message
                        timestamp_str = latest_switch_to_primary.split(' - ')[0]
                        dt_object = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        last_status_update = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass # Fallback to N/A if parsing fails

                elif latest_switch_to_fallback:
                    active_dns_server = f"Fallback ({fallback_dns})"
                    status_class = "warning"
                    try:
                        timestamp_str = latest_switch_to_fallback.split(' - ')[0]
                        dt_object = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        last_status_update = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass

                elif proxy_started:
                    # If proxy started but no switch events, assume primary is active
                    active_dns_server = f"Primary ({primary_dns}) (default)"
                    status_class = "ok"
                    # Try to find the start time from logs
                    for line in log_content.splitlines():
                        if "DNS Fallback Proxy listening on" in line:
                            try:
                                timestamp_str = line.split(' - ')[0]
                                dt_object = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                                last_status_update = dt_object.strftime('%Y-%m-%d %H:%M:%S')
                                break
                            except ValueError:
                                pass
                else:
                    active_dns_server = "Unknown (Proxy might not have started successfully)"
                    status_class = "error"
            else:
                log_content = "Log file is empty."
                active_dns_server = "Unknown (Log file empty)"
                status_class = "warning"

        else:
            dashboard_logger.warning(f"Log file not found at {LOG_FILE_PATH}.")
            log_content = "Log file not found. Ensure proxy is running and configured correctly."
            active_dns_server = "Unknown (Log file missing)"

    except FileNotFoundError:
        dashboard_logger.error(f"Log file path incorrect or file does not exist: {LOG_FILE_PATH}")
        log_content = f"Log file not found at '{LOG_FILE_PATH}'. Check configuration."
    except IOError as e:
        dashboard_logger.error(f"Error reading log file {LOG_FILE_PATH}: {e}")
        log_content = f"Error reading log file: {e}"
    except Exception as e:
        dashboard_logger.exception("An unexpected error occurred while processing log file.")
        log_content = f"An unexpected error occurred reading logs: {e}"


    # Check PID file status
    try:
        if os.path.exists(PID_FILE_PATH):
            with open(PID_FILE_PATH, 'r') as f:
                pid = f.read().strip()
                pid_status = f"Proxy running with PID: {pid}"
                # If active_dns_server is still 'Unknown', assume running and healthy.
                if active_dns_server.startswith("Unknown"):
                    active_dns_server = f"Primary ({primary_dns}) (assumed)"
                    status_class = "ok"
                dashboard_logger.info(f"PID file found: {PID_FILE_PATH}.")
        else:
            pid_status = "PID file not found. Proxy may not be running or path is incorrect."
            status_class = "error" # If PID file not found, proxy is likely not running.
            dashboard_logger.warning(f"PID file not found at {PID_FILE_PATH}.")
    except FileNotFoundError:
        dashboard_logger.error(f"PID file path incorrect or file does not exist: {PID_FILE_PATH}")
        pid_status = f"PID file not found at '{PID_FILE_PATH}'. Check configuration."
    except IOError as e:
        dashboard_logger.error(f"Error reading PID file {PID_FILE_PATH}: {e}")
        pid_status = f"Error reading PID file: {e}"
    except Exception as e:
        dashboard_logger.exception("An unexpected error occurred while processing PID file.")
        pid_status = f"An unexpected error occurred reading PID file: {e}"


    return render_template_string(
        HTML_TEMPLATE,
        log_content=log_content,
        log_file_path=LOG_FILE_PATH,
        pid_status=pid_status,
        active_dns_server=active_dns_server,
        last_status_update=last_status_update,
        status_class=status_class,
        health_check_interval=health_check_interval,
        failure_threshold=failure_threshold
    )

if __name__ == '__main__':
    dashboard_logger.info(f"DNS Fallback Dashboard running on http://0.0.0.0:{DASHBOARD_PORT}")
    app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=False) # debug=False for production
