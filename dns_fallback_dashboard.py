from flask import Flask, render_template_string, send_file, Response, request, redirect, url_for, flash
import os
from collections import defaultdict
import re
import time

app = Flask(__name__)
app.secret_key = "dns-dashboard-secret"
LOG_FILE = "/var/log/dns-fallback.log"

HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Pi-hole DNS Fallback Monitor</title>
    <meta http-equiv="refresh" content="10">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='0.9em' font-size='90'>📡</text></svg>">
    <style>
        body { font-family: Arial; margin: 2em; background: #f8f9fa; color: #333; transition: background 0.3s, color 0.3s; }
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
    <p>Total Queries: <strong>{{ total }}</strong></p>
    <p>Fallbacks Used: <strong>{{ fallback }}</strong></p>
    <h2>Top 10 Fallback Domains</h2>
    <table>
        <tr><th>Domain</th><th>Count</th></tr>
        {% for domain, count in top_domains %}
        <tr><td>{{ domain }}</td><td>{{ count }}</td></tr>
        {% endfor %}
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
            <label>Remove entries older than <input type="number" name="days" value="7" min="1"> days</label>
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

@app.route("/")
def dashboard():
    total_queries = 0
    fallback_hits = 0
    domain_stats = defaultdict(int)

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as log:
            for line in log:
                if re.search(r"query", line, re.IGNORECASE):
                    total_queries += 1
                elif "Fallback used for" in line:
                    fallback_hits += 1
                    parts = line.strip().split("Fallback used for")
                    if len(parts) > 1:
                        domain = parts[1].strip()
                        domain_stats[domain] += 1

    top_domains = sorted(domain_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    return render_template_string(
        HTML_TEMPLATE,
        total=total_queries,
        fallback=fallback_hits,
        top_domains=top_domains,
        top_count=len(top_domains)
    )

@app.route("/clean-log", methods=["POST"])
def clean_log():
    days = int(request.form.get("days", 7))
    cutoff_time = time.time() - (days * 86400)
    cleaned_lines = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as file:
            for line in file:
                try:
                    timestamp_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                    if timestamp_match:
                        log_time = time.mktime(time.strptime(timestamp_match.group(1), "%Y-%m-%d %H:%M:%S"))
                        if log_time > cutoff_time:
                            cleaned_lines.append(line)
                    else:
                        cleaned_lines.append(line)
                except Exception:
                    cleaned_lines.append(line)
        with open(LOG_FILE, "w") as file:
            file.writelines(cleaned_lines)
        flash(("success", f"✅ Log cleaned! Retained entries from the last {days} day(s)."))
    else:
        flash(("error", "⚠️ Log file not found."))
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8053)

