#!/bin/bash

# Enhanced DNS Fallback Installation Script
# Compatible with Pi-hole and Unbound

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/dns-fallback"
CONFIG_DIR="/etc/dns-fallback"
LOG_DIR="/var/log"
SERVICE_DIR="/etc/systemd/system"
BIN_DIR="/usr/local/bin"

# Service names
PROXY_SERVICE="dns-fallback.service"
DASHBOARD_SERVICE="dns-fallback-dashboard.service"

# Print functions
print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  Enhanced DNS Fallback Installation${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Validate prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    local missing_deps=()
    
    # Check for Pi-hole
    if ! command -v pihole &> /dev/null; then
        missing_deps+=("Pi-hole")
    fi
    
    # Check for Unbound
    if ! command -v unbound &> /dev/null; then
        missing_deps+=("Unbound")
    fi
    
    # Check for Python3
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("Python 3")
    fi
    
    # Check for systemctl
    if ! command -v systemctl &> /dev/null; then
        missing_deps+=("systemd")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing required dependencies:"
        for dep in "${missing_deps[@]}"; do
            echo "  - $dep"
        done
        echo ""
        print_info "Please install the missing dependencies and run this script again."
        print_info "For Pi-hole: https://pi-hole.net/"
        print_info "For Unbound: sudo apt install unbound"
        exit 1
    fi
    
    print_success "All prerequisites found"
}

# Backup existing configuration
backup_existing_config() {
    local backup_dir="/opt/dns-fallback-backup-$(date +%Y%m%d-%H%M%S)"
    
    if [ -d "$INSTALL_DIR" ] || [ -d "$CONFIG_DIR" ]; then
        print_info "Backing up existing configuration to $backup_dir"
        mkdir -p "$backup_dir"
        
        [ -d "$INSTALL_DIR" ] && cp -r "$INSTALL_DIR" "$backup_dir/"
        [ -d "$CONFIG_DIR" ] && cp -r "$CONFIG_DIR" "$backup_dir/"
        
        print_success "Backup created at $backup_dir"
    fi
}

# Detect current Unbound configuration
detect_unbound_config() {
    local unbound_conf="/etc/unbound/unbound.conf.d/pi-hole.conf"
    local detected_port="5335"
    
    if [ -f "$unbound_conf" ]; then
        # Try to detect port from config
        local port_line=$(grep -E "^\s*port:" "$unbound_conf" | head -1)
        if [ ! -z "$port_line" ]; then
            detected_port=$(echo "$port_line" | grep -oE '[0-9]+')
        fi
        
        print_info "Detected Unbound configuration:"
        print_info "  Config file: $unbound_conf"
        print_info "  Detected port: $detected_port"
    else
        print_warning "Unbound Pi-hole configuration not found"
        print_info "Expected location: $unbound_conf"
    fi
    
    echo "$detected_port"
}

# Create directories
create_directories() {
    print_info "Creating directories..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$INSTALL_DIR/venv"
    
    print_success "Directories created"
}

# Install Python dependencies
install_python_deps() {
    print_info "Installing Python dependencies..."
    
    # Update package list
    apt update -qq
    
    # Install system packages
    apt install -y python3 python3-pip python3-venv python3-dev
    
    print_success "Python dependencies installed"
}

# Install DNS Fallback files
install_dns_fallback() {
    print_info "Installing DNS Fallback Proxy..."
    
    # Create the main proxy script
    cat > "$BIN_DIR/dns_fallback_proxy.py" << 'EOF'
# The enhanced DNS proxy code goes here
# This would be the content from the enhanced_dns_proxy artifact
EOF
    
    chmod +x "$BIN_DIR/dns_fallback_proxy.py"
    
    print_success "DNS Fallback Proxy installed"
}

# Install Dashboard
install_dashboard() {
    print_info "Installing Enhanced Dashboard..."
    
    # Create the dashboard script
    cat > "$BIN_DIR/dns_fallback_dashboard.py" << 'EOF'
# The enhanced dashboard code goes here
# This would be the content from the enhanced_dashboard artifact
EOF
    
    chmod +x "$BIN_DIR/dns_fallback_dashboard.py"
    
    print_success "Enhanced Dashboard installed"
}

# Create configuration file
create_config() {
    local unbound_port=$1
    
    print_info "Creating configuration file..."
    
    cat > "$CONFIG_DIR/config.ini" << EOF
[Proxy]
# Main upstream resolver (Unbound)
primary_dns = 127.0.0.1:${unbound_port}

# Comma-separated fallback servers (public DNS providers)
fallback_dns_servers = 1.1.1.1, 8.8.8.8, 9.9.9.9

# Address and port to listen on for DNS queries from Pi-hole
listen_address = 127.0.0.1
dns_port = 5355

# Health check configuration
health_check_interval = 10
health_check_domains = google.com, cloudflare.com, wikipedia.org, github.com

# File locations
log_file = $LOG_DIR/dns-fallback.log
pid_file = /var/run/dns-fallback.pid

# Performance settings
buffer_size = 4096
max_workers = 50

# Enhanced timeout settings
unbound_timeout = 1.5
fallback_timeout = 3.0

# Intelligent caching and learning features
intelligent_caching = true
max_domain_cache = 1000
fallback_threshold = 3
bypass_duration = 3600

# Query optimization
enable_query_deduplication = true

# Logging configuration
structured_logging = true
EOF
    
    print_success "Configuration file created at $CONFIG_DIR/config.ini"
}

# Create systemd services
create_services() {
    print_info "Creating systemd services..."
    
    # DNS Fallback Proxy service
    cat > "$SERVICE_DIR/$PROXY_SERVICE" << EOF
[Unit]
Description=Enhanced DNS Fallback Proxy
After=network.target unbound.service
Wants=network.target
Requires=unbound.service

[Service]
Type=simple
User=root
Group=root
ExecStart=$BIN_DIR/dns_fallback_proxy.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$LOG_DIR /var/run $CONFIG_DIR
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_RAW

[Install]
WantedBy=multi-user.target
EOF

    # Dashboard service
    cat > "$SERVICE_DIR/$DASHBOARD_SERVICE" << EOF
[Unit]
Description=Enhanced DNS Fallback Dashboard
After=network.target dns-fallback.service
Wants=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart=$BIN_DIR/dns_fallback_dashboard.py
Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadOnlyPaths=$LOG_DIR

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "Systemd services created"
}

# Configure log rotation
setup_log_rotation() {
    print_info "Setting up log rotation..."
    
    cat > "/etc/logrotate.d/dns-fallback" << EOF
$LOG_DIR/dns-fallback.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        systemctl reload dns-fallback.service >/dev/null 2>&1 || true
    endscript
}
EOF
    
    print_success "Log rotation configured"
}

# Validate Unbound configuration
validate_unbound() {
    local unbound_port=$1
    
    print_info "Validating Unbound configuration..."
    
    # Check if Unbound is running
    if ! systemctl is-active --quiet unbound; then
        print_warning "Unbound is not currently running"
        print_info "Starting Unbound..."
        systemctl start unbound
        sleep 2
    fi
    
    # Test DNS resolution through Unbound
    if timeout 5 dig @127.0.0.1 -p "$unbound_port" google.com +short >/dev/null 2>&1; then
        print_success "Unbound is responding correctly on port $unbound_port"
    else
        print_warning "Unbound test failed on port $unbound_port"
        print_info "Please check your Unbound configuration"
    fi
}

# Start services
start_services() {
    print_info "Starting services..."
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable and start services
    systemctl enable "$PROXY_SERVICE"
    systemctl enable "$DASHBOARD_SERVICE"
    
    systemctl start "$PROXY_SERVICE"
    sleep 2
    systemctl start "$DASHBOARD_SERVICE"
    
    # Check service status
    if systemctl is-active --quiet "$PROXY_SERVICE"; then
        print_success "DNS Fallback Proxy service started"
    else
        print_error "Failed to start DNS Fallback Proxy service"
        systemctl status "$PROXY_SERVICE" --no-pager
    fi
    
    if systemctl is-active --quiet "$DASHBOARD_SERVICE"; then
        print_success "Dashboard service started"
    else
        print_error "Failed to start Dashboard service"
        systemctl status "$DASHBOARD_SERVICE" --no-pager
    fi
}

# Test installation
test_installation() {
    print_info "Testing installation..."
    
    # Test DNS proxy
    if timeout 5 dig @127.0.0.1 -p 5355 google.com +short >/dev/null 2>&1; then
        print_success "DNS Fallback Proxy is working"
    else
        print_warning "DNS Fallback Proxy test failed"
    fi
    
    # Test dashboard
    if curl -s http://127.0.0.1:8053/health >/dev/null 2>&1; then
        print_success "Dashboard is accessible"
    else
        print_warning "Dashboard test failed"
    fi
}

# Display final instructions
show_final_instructions() {
    local server_ip=$(hostname -I | awk '{print $1}')
    
    echo ""
    print_header
    echo ""
    print_success "Enhanced DNS Fallback installation completed!"
    echo ""
    print_info "Next steps:"
    echo "1. Configure Pi-hole to use the DNS proxy:"
    echo "   • Go to Pi-hole Admin → Settings → DNS"
    echo "   • Remove all current upstream DNS servers"
    echo "   • Add: 127.0.0.1#5355"
    echo "   • Save changes"
    echo ""
    echo "2. Access the Enhanced Dashboard:"
    echo "   • Local: http://localhost:8053"
    echo "   • Network: http://$server_ip:8053"
    echo ""
    print_info "Service management:"
    echo "• Check status: sudo systemctl status dns-fallback"
    echo "• View logs: sudo journalctl -u dns-fallback -f"
    echo "• Restart: sudo systemctl restart dns-fallback"
    echo ""
    print_info "Configuration file: $CONFIG_DIR/config.ini"
    print_info "Log file: $LOG_DIR/dns-fallback.log"
    echo ""
    print_success "Installation complete! 🎉"
}

# Cleanup function
cleanup() {
    if [ $? -ne 0 ]; then
        print_error "Installation failed!"
        print_info "Check the error messages above and try again"
        print_info "You can safely re-run this script"
    fi
}

# Main installation function
main() {
    trap cleanup EXIT
    
    print_header
    
    check_root
    check_prerequisites
    backup_existing_config
    
    local unbound_port=$(detect_unbound_config)
    
    create_directories
    install_python_deps
    install_dns_fallback
    install_dashboard
    create_config "$unbound_port"
    create_services
    setup_log_rotation
    
    validate_unbound "$unbound_port"
    start_services
    test_installation
    
    show_final_instructions
}

# Run main function
main "$@"
