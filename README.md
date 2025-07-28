# 🛡️ Enhanced DNS Fallback for Pi-hole

A sophisticated DNS fallback solution that intelligently routes DNS queries through Unbound (for privacy) and falls back to public DNS servers when needed. Features an enhanced dashboard with comprehensive analytics and smart domain learning.

## 🌟 Key Features

### 🧠 Intelligent DNS Resolution
- **Smart Fallback Logic**: Automatically detects when Unbound cannot resolve specific domains
- **Domain Learning**: Learns which domains consistently fail with Unbound and routes them directly to fallback servers
- **CDN Recognition**: Automatically detects and handles CDN domains that typically require public DNS
- **Query Deduplication**: Prevents duplicate queries for the same domain to improve performance

### 📊 Enhanced Analytics Dashboard
- **Real-time Metrics**: Live statistics on DNS resolution patterns
- **Performance Monitoring**: Response time analysis with percentile metrics
- **Failure Analysis**: Detailed breakdown of domains requiring fallback
- **Visual Charts**: Interactive graphs showing resolver usage over time
- **Export Functionality**: CSV export of analytics data

### ⚡ Performance Optimizations
- **Adaptive Timeouts**: Different timeout values for Unbound vs public DNS
- **Bypass Mechanism**: Temporarily bypasses Unbound for consistently failing domains
- **Concurrent Processing**: Multi-threaded query handling
- **Structured Logging**: JSON-formatted logs for better analysis

### 🔧 Operational Excellence
- **Health Monitoring**: Continuous health checks with adaptive intervals
- **Graceful Degradation**: Seamless fallback when services are unavailable
- **Service Integration**: Full systemd integration with proper lifecycle management
- **Comprehensive Testing**: Built-in testing suite for validation

## 🏗️ Architecture

```
Pi-hole → DNS Fallback Proxy → Unbound (Primary)
                           ↓
                       Public DNS (Fallback)
```

### Component Overview

1. **Pi-hole**: Handles ad blocking and forwards DNS queries to the proxy
2. **DNS Fallback Proxy**: Intelligent routing with learning capabilities
3. **Unbound**: Recursive DNS resolver for privacy and security
4. **Enhanced Dashboard**: Web-based analytics and monitoring interface

## 🚀 Quick Installation

### Prerequisites

- Pi-hole installed and running
- Unbound installed and configured
- Python 3.7+ with pip
- systemd-based Linux distribution
- Root/sudo access

### One-Line Installation

```bash
git clone https://github.com/ordor2k/dns-fallback-pihole.git
cd dns-fallback-pihole
sudo bash install_dns_fallback.sh
```

### Post-Installation Setup

1. **Configure Pi-hole**:
   - Go to Pi-hole Admin → Settings → DNS
   - Remove all upstream DNS servers
   - Add: `127.0.0.1#5355`
   - Save changes

2. **Access Dashboard**:
   - Local: http://localhost:8053
   - Network: http://YOUR_PI_IP:8053

## 📋 Manual Installation

<details>
<summary>Click to expand manual installation steps</summary>

### 1. System Requirements

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Clone Repository

```bash
git clone https://github.com/ordor2k/dns-fallback-pihole.git
cd dns-fallback-pihole
```

### 3. Install Components

```bash
# Create directories
sudo mkdir -p /opt/dns-fallback /etc/dns-fallback

# Install Python scripts
sudo cp dns_fallback_proxy.py /usr/local/bin/
sudo cp dns_fallback_dashboard.py /usr/local/bin/
sudo chmod +x /usr/local/bin/dns_fallback_*.py

# Install systemd services
sudo cp dns-fallback.service /etc/systemd/system/
sudo cp dns-fallback-dashboard.service /etc/systemd/system/

# Setup configuration
sudo cp config.ini /etc/dns-fallback/
```

### 4. Configure Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable dns-fallback.service dns-fallback-dashboard.service
sudo systemctl start dns-fallback.service dns-fallback-dashboard.service
```

</details>

## ⚙️ Configuration

### Main Configuration File: `/etc/dns-fallback/config.ini`

```ini
[Proxy]
# Unbound configuration
primary_dns = 127.0.0.1:5335
unbound_timeout = 1.5

# Fallback DNS servers
fallback_dns_servers = 1.1.1.1, 8.8.8.8, 9.9.9.9
fallback_timeout = 3.0

# Proxy settings
listen_address = 127.0.0.1
dns_port = 5355

# Enhanced features
intelligent_caching = true
max_domain_cache = 1000
fallback_threshold = 3
bypass_duration = 3600
enable_query_deduplication = true
structured_logging = true

# Health monitoring
health_check_interval = 10
health_check_domains = google.com, cloudflare.com, wikipedia.org
```

### Advanced Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `intelligent_caching` | `true` | Enable domain-specific learning |
| `fallback_threshold` | `3` | Failures before domain bypass |
| `bypass_duration` | `3600` | Bypass period in seconds |
| `enable_query_deduplication` | `true` | Prevent duplicate concurrent queries |
| `structured_logging` | `true` | JSON-formatted logs |
| `max_domain_cache` | `1000` | Maximum domains to track |

## 🔍 Monitoring & Analytics

### Dashboard Features

#### 📈 Real-time Statistics
- Total queries processed
- Unbound success rate
- Fallback usage percentage
- Average response times
- Current active DNS server

#### 📊 Visual Analytics
- **Query Distribution**: Hourly breakdown of DNS queries
- **Resolver Usage**: Pie chart of Unbound vs fallback usage
- **Response Times**: Performance percentile analysis
- **Query Types**: Distribution of DNS record types

#### 📋 Data Tables
- **Top Domains**: Most queried domains
- **Problematic Domains**: Domains requiring fallback
- **Client Analysis**: Per-client query statistics
- **Recent Events**: Real-time system events

#### 💾 Export Options
- CSV export of all analytics data
- Configurable time ranges (1h, 6h, 24h, 1week)
- Comprehensive reports for troubleshooting

### Log Analysis

#### Structured Logging Format
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "level": "INFO",
  "message": "DNS_QUERY",
  "domain": "example.com",
  "client": "192.168.1.100",
  "resolver": "unbound",
  "response_time": 0.045,
  "query_type": "A",
  "success": true
}
```

#### Key Log Events
- `DNS_QUERY`: Individual DNS resolution events
- `FALLBACK_SWITCH`: When switching to fallback DNS
- `DOMAIN_BYPASSED`: When a domain is temporarily bypassed
- `HEALTH_CHECK`: DNS server health status changes

## 🧪 Testing & Validation

### Comprehensive Testing Suite

Run the built-in testing script:

```bash
sudo bash test_dns_fallback.sh
```

#### Test Categories

1. **Service Status**: Verify all components are running
2. **Network Connectivity**: Check port bindings and accessibility
3. **DNS Resolution**: Test query processing through all paths
4. **CDN Handling**: Verify CDN domain fallback behavior
5. **Performance**: Response time analysis and overhead measurement
6. **Fallback Mechanism**: Simulate Unbound failure scenarios
7. **Dashboard**: Web interface functionality testing
8. **Integration**: Pi-hole configuration validation

### Manual Testing Commands

```bash
# Test direct Unbound resolution
dig @127.0.0.1 -p 5335 google.com

# Test through DNS Fallback Proxy
dig @127.0.0.1 -p 5355 google.com

# Test full Pi-hole chain
dig @127.0.0.1 -p 53 google.com

# Check service status
systemctl status dns-fallback.service
systemctl status dns-fallback-dashboard.service

# Monitor logs in real-time
tail -f /var/log/dns-fallback.log
```

## 🔧 Troubleshooting

### Common Issues

#### DNS Proxy Not Responding

```bash
# Check service status
sudo systemctl status dns-fallback.service

# Check if port is bound
sudo ss -tuln | grep :5355

# Check logs
sudo journalctl -u dns-fallback.service -f
```

#### High Fallback Usage

1. **Check Unbound Configuration**:
   ```bash
   sudo unbound-checkconf
   sudo systemctl status unbound.service
   ```

2. **Review Dashboard Analytics**:
   - Identify domains consistently failing with Unbound
   - Check response time patterns
   - Review error logs

3. **Adjust Configuration**:
   ```ini
   # Increase Unbound timeout
   unbound_timeout = 2.0
   
   # Reduce fallback threshold
   fallback_threshold = 5
   ```

#### Dashboard Not Accessible

```bash
# Check dashboard service
sudo systemctl status dns-fallback-dashboard.service

# Check port binding
sudo ss -tuln | grep :8053

# Test health endpoint
curl http://127.0.0.1:8053/health
```

### Performance Tuning

#### For High-Volume Networks

```ini
[Proxy]
# Increase worker threads
max_workers = 100

# Increase domain cache
max_domain_cache = 5000

# Optimize buffer size
buffer_size = 8192

# Reduce health check frequency
health_check_interval = 30
```

#### For Low-Latency Requirements

```ini
[Proxy]
# Aggressive timeouts
unbound_timeout = 1.0
fallback_timeout = 2.0

# Enable all optimizations
enable_query_deduplication = true
intelligent_caching = true

# Faster bypass recovery
bypass_duration = 1800
```

## 🔄 Maintenance

### Log Rotation

Automatic log rotation is configured via `/etc/logrotate.d/dns-fallback`:

```
/var/log/dns-fallback.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
```

### Service Management

```bash
# Restart services
sudo systemctl restart dns-fallback.service
sudo systemctl restart dns-fallback-dashboard.service

# View service logs
sudo journalctl -u dns-fallback.service -f
sudo journalctl -u dns-fallback-dashboard.service -f

# Check service health
sudo systemctl is-active dns-fallback.service
curl http://127.0.0.1:8053/health
```

### Configuration Updates

1. Edit configuration file:
   ```bash
   sudo nano /etc/dns-fallback/config.ini
   ```

2. Reload services:
   ```bash
   sudo systemctl reload dns-fallback.service
   ```

3. Verify changes:
   ```bash
   sudo systemctl status dns-fallback.service
   ```

## 🗑️ Uninstallation

### Complete Removal

```bash
sudo bash uninstall_dns_fallback.sh
```

### Manual Cleanup

<details>
<summary>Manual uninstallation steps</summary>

```bash
# Stop and disable services
sudo systemctl stop dns-fallback.service dns-fallback-dashboard.service
sudo systemctl disable dns-fallback.service dns-fallback-dashboard.service

# Remove service files
sudo rm -f /etc/systemd/system/dns-fallback*.service
sudo systemctl daemon-reload

# Remove binaries
sudo rm -f /usr/local/bin/dns_fallback_*.py

# Remove configuration and logs
sudo rm -rf /etc/dns-fallback
sudo rm -rf /opt/dns-fallback
sudo rm -f /var/log/dns-fallback.log*

# Remove log rotation
sudo rm -f /etc/logrotate.d/dns-fallback
```

**Important**: Remember to reconfigure Pi-hole DNS settings after uninstallation!

</details>

## 📊 Performance Metrics

### Typical Performance Characteristics

| Metric | Unbound Direct | Through Proxy | Fallback Only |
|--------|----------------|---------------|---------------|
| Response Time | 15-50ms | 20-60ms | 25-100ms |
| Success Rate | 85-95% | 98-99% | 99%+ |
| Memory Usage | - | 50-100MB | - |
| CPU Impact | - | < 5% | - |

### Optimization Impact

- **Query Deduplication**: 10-30% reduction in upstream queries
- **Domain Learning**: 50-80% reduction in fallback latency for learned domains
- **CDN Recognition**: 90%+ immediate routing for known CDN patterns

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

### Development Setup

```bash
git clone https://github.com/ordor2k/dns-fallback-pihole.git
cd dns-fallback-pihole

# Install development dependencies
pip3 install -r requirements-dev.txt

# Run tests
python3 -m pytest tests/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Pi-hole team for the excellent ad-blocking platform
- Unbound developers for the secure recursive resolver
- The DNS community for protocols and best practices
- Contributors and testers who helped improve this project

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/ordor2k/dns-fallback-pihole/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ordor2k/dns-fallback-pihole/discussions)
- **Wiki**: [Project Wiki](https://github.com/ordor2k/dns-fallback-pihole/wiki)

---

**Made with ❤️ for the Pi-hole and privacy-focused DNS community**
