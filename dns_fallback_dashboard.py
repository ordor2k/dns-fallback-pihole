from flask import Flask, render_template_string, send_file, Response, request, redirect, url_for, flash
import os
from collections import defaultdict
import re
import time
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dns-dashboard-secret-change-me')
LOG_FILE = os.environ.get('DNS_LOG_FILE', '/var/log/dns-fallback.log')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>DNS Fallback Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='0.9em' font-size='90'>📡</text></svg>">
    <style>
        body { font-family: Arial; margin: 2em; background: #f8f9fa; color: #333; transition: background 0.3s; }
        h1 { color: #007bff; }
        table { width: 100%; border-collapse: collapse; margin-top: 1em; }
        th, td { padding: 8px 12px; border: 1px solid #ccc; text-align: left; }
        th { background: #007bff; color: #fff; }
        body.dark-mode { background: #121212; color: #eee; }
        body.dark-mode th { background: #333; color: #eee; }
        .toggle { position: fixed; top: 1em; right: 2em; z-index: 1000; }
        .download-panel { margin-top: 2em; width: 240px; background: #f0f0f0; padding: 1em; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .download-panel h3 { margin-top: 0; font-size: 1.2em; }
        .download-panel button { width: 100%; margin: 4px 0; padding: 8px; }
        .dark-mode .download-panel { background: #1e1e1e; color: #ddd; }
        .dark-mode .download-panel button { background: #333; color: #fff; border: 1px solid #555; }
        .log-cleaner { margin-top: 3em; padding: 1em; border: 1px solid #ccc; background: #fdfdfd; max-width: 320px; }
        .dark-mode .log-cleaner { background: #1e1e1e; border-color: #444; color: #ddd; }
        .flash-message { margin-top: 1em; padding: 0.5em 1em; border-radius: 5px; font-weight: bold; }
        .flash-success { background: #dff0d8; border: 1px solid #b2dba1; color: #3c763d; }
        .flash-error { background: #f8d7da; border: 1px solid #f5c2c7; color: #842029; }
        .error-message { background: #f8d7da; border: 1px solid #f5c2c7; color: #842029; padding: 1em; margin: 1em 0; border-radius: 5px; }
        @keyframes fadeout { from { opacity: 1; } to { opacity: 0; } }
    </style>
</head>
<body>
    <div class="toggle">
        <label><input type="checkbox" id="darkToggle"> 🌙 Dark Mode</label>
    </div>
    <h1>DNS Fallback Dashboard</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            <div id="flashMessage" class="flash-message {{ 'flash-success' if messages[0][0] == 'success' else 'flash-error' }}">{{ messages[0][1] }}</div>
        {% endif %}
    {% endwith %}
    
    {% if error %}
        <div class="error-message">{{ error }}</div>
    {% endif %}
    
    <p>Total Queries: <strong>{{ total }}</strong></p>
    <p>Fallbacks Used: <strong>{{ fallback }}</strong></p>
    <p>Success Rate: <strong>{{ success_rate }}%</strong></p>
    
    <h2>Top 10 Fallback Domains</h2>
    <table>
        <tr><th>Domain</th><th>Count</th></tr>
        {% for domain, count in top_domains %}
        <tr><td>{{ domain }}</td><td>{{ count }}</td></tr>
        {% endfor %}
        {% if not top_domains %}
        <tr><td colspan="2">No fallback domains found</td></tr>
        {% endif %}
    </table>

    <div class="download-panel">
        <h3>📦 Downloads</h3>
        <a href="/download-log"><button>⬇️ Full Log</button></a>
        <a href="/download-fallbacks"><button>🎯 Fallbacks Only</button></a>
        <a href="/download-queries"><button>🔍 Queries Only</button></a>
        <a href="/download-domains"><button>📊 Unique Domains CSV</button></a>
    </div>

    <div class="log-cleaner">
        <h3>🧹 Clean Log</h3>
        <form method="post" action="/clean-log" onsubmit="return confirm('Are you sure you want to clean the log?');">
            <label>Remove entries older than <input type="number" name="days" value="7" min="1" max="365"> days</label>
            <button type="submit">🧽 Clean Log</button>
        </form>
    </div>
    <script>
        const toggle = document.getElementById('darkToggle');
        if (localStorage.getItem('dark-mode') === 'true') {
            toggle.checked = true;
            document.body.classList.add('dark-mode');
        }
        toggle.addEventListener('change', () => {
            const enabled = toggle.checked;
            document.body.classList.toggle('dark-mode', enabled);
            localStorage.setItem('dark-mode', enabled);
        });

        const flash = document.getElementById('flashMessage');
        if (flash) {
            setTimeout(() => {
                flash.style.animation = "fadeout 1s forwards";
                setTimeout(() => location.reload(), 1000);
            }, 2500);
        }
    </script>
</body>
</html>
"""

def parse_log_file():
    """Parse log file with improved error handling and correct pattern matching"""
    total_queries = 0
    fallback_hits = 0
    domain_stats = defaultdict(int)
    error_message = None

    if not os.path.exists(LOG_FILE):
        return 0, 0, {}, "Log file not found"

    try:
        with open(LOG_FILE, "r", encoding='utf-8', errors='ignore') as log:
            for line_num, line in enumerate(log, 1):
                try:
                    # Fixed: Correct pattern matching for queries
                    if "→ Query:" in line or "Query:" in line:
                        total_queries += 1
                    
                    # Fixed: Correct pattern matching for fallbacks
                    elif "Fallback used for" in line:
                        fallback_hits += 1
                        # Extract domain from the log line
                        match = re.search(r'Fallback used for (.+?)(?:\s|$)', line)
                        if match:
                            domain = match.group(1).strip()
                            domain_stats[domain] += 1
                
                except Exception as e:
                    logger.warning(f"Error parsing line {line_num}: {e}")
                    continue
                    
    except PermissionError:
        error_message = "Permission denied reading log file"
    except Exception as e:
        error_message = f"Error reading log file: {str(e)}"
        logger.error(f"Log parsing error: {e}")

    return total_queries, fallback_hits, domain_stats, error_message

@app.route("/")
def dashboard():
    """Main dashboard with improved error handling"""
    try:
        total_queries, fallback_hits, domain_stats, error_message = parse_log_file()
        
        # Calculate success rate
        success_rate = 0
        if total_queries > 0:
            success_rate = round(((total_queries - fallback_hits) / total_queries) * 100, 1)
        
        top_domains = sorted(domain_stats.items(), key=lambda x: x[1], reverse=True)[:10]

        return render_template_string(
            HTML_TEMPLATE,
            total=total_queries,
            fallback=fallback_hits,
            success_rate=success_rate,
            top_domains=top_domains,
            error=error_message
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return render_template_string(
            HTML_TEMPLATE,
            total=0,
            fallback=0,
            success_rate=0,
            top_domains=[],
            error=f"Dashboard error: {str(e)}"
        )

@app.route("/clean-log", methods=["POST"])
def clean_log():
    """Clean log with improved input validation and error handling"""
    try:
        # Fixed: Input validation
        days_str = request.form.get("days", "7")
        try:
            days = int(days_str)
            if days < 1 or days > 365:
                raise ValueError("Days must be between 1 and 365")
        except ValueError as e:
            flash(("error", f"⚠️ Invalid days value: {e}"))
            return redirect(url_for("dashboard"))
        
        cutoff_time = time.time() - (days * 86400)
        cleaned_lines = []

        if not os.path.exists(LOG_FILE):
            flash(("error", "⚠️ Log file not found."))
            return redirect(url_for("dashboard"))

        # Fixed: Better file handling with backup
        backup_file = f"{LOG_FILE}.backup"
        try:
            # Create backup
            with open(LOG_FILE, "r") as original:
                with open(backup_file, "w") as backup:
                    backup.write(original.read())
            
            # Clean log
            with open(LOG_FILE, "r") as file:
                for line in file:
                    try:
                        timestamp_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                        if timestamp_match:
                            log_time = time.mktime(time.strptime(timestamp_match.group(1), "%Y-%m-%d %H:%M:%S"))
                            if log_time > cutoff_time:
                                cleaned_lines.append(line)
                        else:
                            # Keep lines without timestamps (might be continuation lines)
                            cleaned_lines.append(line)
                    except Exception as e:
                        logger.warning(f"Error processing log line: {e}")
                        cleaned_lines.append(line)  # Keep problematic lines rather than lose them
            
            # Write cleaned log
            with open(LOG_FILE, "w") as file:
                file.writelines(cleaned_lines)
            
            # Remove backup if successful
            os.remove(backup_file)
            
            flash(("success", f"✅ Log cleaned! Retained entries from the last {days} day(s)."))
            
        except Exception as e:
            # Restore from backup if something went wrong
            if os.path.exists(backup_file):
                try:
                    with open(backup_file, "r") as backup:
                        with open(LOG_FILE, "w") as original:
                            original.write(backup.read())
                    os.remove(backup_file)
                except Exception:
                    pass
            flash(("error", f"⚠️ Error cleaning log: {str(e)}"))
            
    except Exception as e:
        flash(("error", f"⚠️ Unexpected error: {str(e)}"))
        logger.error(f"Clean log error: {e}")
    
    return redirect(url_for("dashboard"))

@app.route("/download-log")
def download_log():
    """Download log with error handling"""
    try:
        if not os.path.exists(LOG_FILE):
            flash(("error", "⚠️ Log file not found."))
            return redirect(url_for("dashboard"))
        return send_file(LOG_FILE, as_attachment=True, download_name="dns-fallback.log")
    except Exception as e:
        flash(("error", f"⚠️ Error downloading log: {str(e)}"))
        return redirect(url_for("dashboard"))

@app.route("/download-fallbacks")
def download_fallbacks():
    """Download fallback entries only"""
    try:
        lines = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line for line in f if "Fallback used for" in line]
        
        content = "".join(lines) if lines else "No fallback entries found\n"
        return Response(content, mimetype="text/plain", headers={
            "Content-Disposition": "attachment; filename=fallbacks.log"
        })
    except Exception as e:
        flash(("error", f"⚠️ Error downloading fallbacks: {str(e)}"))
        return redirect(url_for("dashboard"))

@app.route("/download-queries")
def download_queries():
    """Download query entries only"""
    try:
        lines = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line for line in f if ("→ Query:" in line or "Query:" in line)]
        
        content = "".join(lines) if lines else "No query entries found\n"
        return Response(content, mimetype="text/plain", headers={
            "Content-Disposition": "attachment; filename=queries.log"
        })
    except Exception as e:
        flash(("error", f"⚠️ Error downloading queries: {str(e)}"))
        return redirect(url_for("dashboard"))

@app.route("/download-domains")
def download_domains():
    """Download unique fallback domains as CSV"""
    try:
        domains = set()
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if "Fallback used for" in line:
                        match = re.search(r'Fallback used for (.+?)(?:\s|$)', line)
                        if match:
                            domain = match.group(1).strip()
                            domains.add(domain)
        
        csv_content = "domain\n" + "\n".join(sorted(domains)) if domains else "domain\nNo fallback domains found"
        return Response(csv_content, mimetype="text/csv", headers={
            "Content-Disposition": "attachment; filename=fallback_domains.csv"
        })
    except Exception as e:
        flash(("error", f"⚠️ Error downloading domains: {str(e)}"))
        return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8053, debug=False)
