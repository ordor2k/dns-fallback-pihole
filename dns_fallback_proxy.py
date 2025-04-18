#!/usr/bin/env python3

from dnslib import DNSRecord, QTYPE
import socket, time, logging
from collections import defaultdict

# Configuration
LISTEN_PORT = 5353  # Proxy listens on 5353 (avoid 5355 due to conflict with Unbound)
PRIMARY_DNS = ("127.0.0.1", 5355)  # Unbound listens on 5355
FALLBACK_DNS = ("1.1.1.1", 53)
TIMEOUT = 2.0  # More time for Unbound recursion

# Logging setup
logging.basicConfig(
    filename="/var/log/dns-fallback.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Stats
total_queries = 0
fallback_hits = 0
per_domain_fallback = defaultdict(int)

# Start listening
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", LISTEN_PORT))
logging.info(f"DNS fallback proxy started on port {LISTEN_PORT}")

while True:
    try:
        data, addr = sock.recvfrom(512)
        query = DNSRecord.parse(data)
        domain = str(query.q.qname)
        qtype = QTYPE[query.q.qtype]

        total_queries += 1
        logging.info(f"→ Query: {domain} ({qtype}) from {addr[0]}")

        # Attempt recursive query via Unbound
        primary_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        primary_sock.settimeout(TIMEOUT)
        primary_sock.sendto(data, PRIMARY_DNS)

        try:
            response, _ = primary_sock.recvfrom(512)
            logging.info(f"✔ Primary success for {domain}")
        except socket.timeout:
            fallback_hits += 1
            per_domain_fallback[domain] += 1
            logging.warning(f"⏱ Timeout → Fallback used for {domain} (⚠️ no DNSSEC validation)")

            fallback_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            fallback_sock.sendto(data, FALLBACK_DNS)
            response, _ = fallback_sock.recvfrom(512)
            logging.info(f"✔ Fallback success for {domain}")
            fallback_sock.close()

        primary_sock.close()
        sock.sendto(response, addr)

        # Log stats periodically
        if total_queries % 10 == 0:
            logging.info(f"STATS: {total_queries} total queries, {fallback_hits} fallbacks")
            top = sorted(per_domain_fallback.items(), key=lambda x: x[1], reverse=True)[:3]
            for d, count in top:
                logging.info(f"  └─ {d}: {count} fallback(s)")

    except Exception as e:
        logging.error(f"❌ Error: {e}")
