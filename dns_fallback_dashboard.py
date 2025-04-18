from flask import Flask, render_template_string
import os
from collections import defaultdict

app = Flask(__name__)

LOG_FILE = "/var/log/dns-fallback.log"

HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>DNS Fallback Stats</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body { font-family: Arial; margin: 2em; background: #f8f9fa; color: #333; }
        h1 { color: #007bff; }
        table { width: 100%; border-collapse: collapse; margin-top: 1em; }
        th, td { padding: 8px 12px; border: 1px solid #ccc; text-align: left; }
        th { background: #007bff; color: #fff; }
    </style>
</head>
<body>
    <h1>DNS Fallback Dashboard</h1>
    <p>Total Queries: <strong>{{ total }}</strong></p>
    <p>Fallbacks Used: <strong>{{ fallback }}</strong></p>
    <h2>Top Fallback Domains</h2>
    <table>
        <tr><th>Domain</th><th>Count</th></tr>
        {% for domain, count in top_domains %}
        <tr><td>{{ domain }}</td><td>{{ count }}</td></tr>
        {% endfor %}
    </table>
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
