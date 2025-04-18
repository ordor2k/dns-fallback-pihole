# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),  
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
## [v1.0.1] – 2025-04-18
### Added
- Dark mode toggle on the dashboard
- Persistent dark mode using `localStorage`
- Added 📡 favicon to the browser tab


## [v1.0.0] – 2025-04-18
### Added
- Initial release of `dns_fallback_proxy.py`: Python DNS proxy with fallback to public resolvers.
- Added `dns_fallback_dashboard.py`: live dashboard showing fallback stats.
- Included `systemd` services for proxy and dashboard.
- Provided full installation instructions and project setup.
- Added basic logging to `/var/log/dns-fallback.log`.
- HTML dashboard auto-refreshes every 10 seconds.

---
