from flask import Flask, render_template_string
import os
from collections import defaultdict

app = Flask(__name__)

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
        .dark-mode body { background: #121212; color: #eee; }
        .dark-mode th { background: #333; color: #eee; }
        .toggle { position: fixed; top: 1em; right: 1em; }
    </style>
</head>
<body>
    <div class="toggle">
        <label><input type="checkbox" id="darkToggle"> 🌙 Dark Mode</label>
    </div>
    <h1>DNS Fallback Monitor for Pi-hole</h1>
    <p>Total Queries: <strong>{{ total }}</strong></p>
    <p>Fallbacks Used: <strong>{{ fallback }}</strong></p>
    <h2>Top Fallback Domains</h2>
    <table>
        <tr><th>Domain</th><th>Count</th></tr>
        {% for domain, count in top_domains %}
        <tr><td>{{ domain }}</td><td>{{ count }}</td></tr>
        {% endfor %}
    </table>
    <script>
        const toggle = document.getElementById('darkToggle');
        const root = document.documentElement;

        // Initialize from localStorage
        if (localStorage.getItem('dark-mode') === 'true') {
            toggle.checked = true;
            root.classList.add('dark-mode');
        }

        toggle.addEventListener('change', () => {
            const enabled = toggle.checked;
            root.classList.toggle('dark-mode', enabled);
            localStorage.setItem('dark-mode', enabled);
        });
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
                if "→ Query:" in line:
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
        top_domains=top_domains
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8053)
