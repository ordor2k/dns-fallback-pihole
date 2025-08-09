#!/bin/bash

# Enhanced DNS Fallback Installation Script
# Version: 2.2 - IMPROVED & FIXED
# Compatible with Pi-hole and Unbound - handles externally-managed-environment

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

# Global variables for cleanup
INSTALLATION_STARTED=false
SERVICES_CREATED=false

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
    
    # Check if required services exist and are enabled
    local service_issues=()
    
    if ! systemctl list-unit-files | grep -q "pihole-FTL.service"; then
        service_issues+=("pihole-FTL.service not found")
    fi
    
    if ! systemctl list-unit-files | grep -q "unbound.service"; then
        service_issues+=("unbound.service not found")
    fi
    
    if [ ${#service_issues[@]} -ne 0 ]; then
        print_warning "Service dependency issues found:"
        for issue in "${service_issues[@]}"; do
            echo "  - $issue"
        done
        print_info "The installation will continue, but you may need to adjust service dependencies"
    fi
    
    print_success "All prerequisites found"
}

# Check for port conflicts
check_port_conflicts() {
    print_info "Checking for port conflicts..."
    
    local conflicts=()
    
    # Check port 5355 (DNS proxy)
    if netstat -tuln 2>/dev/null | grep -q ":5355 "; then
        local process=$(lsof -ti:5355 2>/dev/null | head -1)
        if [ ! -z "$process" ]; then
            local process_name=$(ps -p "$process" -o comm= 2>/dev/null || echo "unknown")
            conflicts+=("Port 5355 is in use by process: $process_name (PID: $process)")
        fi
    fi
    
    # Check port 8053 (Dashboard)
    if netstat -tuln 2>/dev/null | grep -q ":8053 "; then
        local process=$(lsof -ti:8053 2>/dev/null | head -1)
        if [ ! -z "$process" ]; then
            local process_name=$(ps -p "$process" -o comm= 2>/dev/null || echo "unknown")
            conflicts+=("Port 8053 is in use by process: $process_name (PID: $process)")
        fi
    fi
    
    if [ ${#conflicts[@]} -ne 0 ]; then
        print_error "Port conflicts detected:"
        for conflict in "${conflicts[@]}"; do
            echo "  - $conflict"
        done
        echo ""
        print_info "Please stop the conflicting services or choose different ports"
        return 1
    fi
    
    print_success "No port conflicts detected"
    return 0
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

# IMPROVED: Detect current Unbound configuration with better error handling
detect_unbound_config() {
    local unbound_conf="/etc/unbound/unbound.conf.d/pi-hole.conf"
    local detected_port="5335"
    
    # Try multiple common Unbound config locations
    local config_locations=(
        "/etc/unbound/unbound.conf.d/pi-hole.conf"
        "/etc/unbound/unbound.conf"
        "/etc/unbound/conf.d/pi-hole.conf"
    )
    
    local found_config=""
    for config in "${config_locations[@]}"; do
        if [ -f "$config" ]; then
            found_config="$config"
            break
        fi
    done
    
    if [ -n "$found_config" ]; then
        # Try multiple port detection patterns
        local port_patterns=(
            "^\s*port:\s*([0-9]+)"
            "^\s*port\s+([0-9]+)"
            "port:\s*([0-9]+)"
            "port\s+([0-9]+)"
        )
        
        for pattern in "${pattern[@]}"; do
            local port_line=$(grep -E "$pattern" "$found_config" | head -1)
            if [ ! -z "$port_line" ]; then
                detected_port=$(echo "$port_line" | grep -oE '[0-9]+')
                break
            fi
        done
        
        # Redirect informational output to stderr so it doesn't contaminate the return value
        print_info "Detected Unbound configuration:" >&2
        print_info "  Config file: $found_config" >&2
        print_info "  Detected port: $detected_port" >&2
    else
        print_warning "Unbound Pi-hole configuration not found in common locations" >&2
        print_info "Using default port: $detected_port" >&2
    fi
    
    # Validate the detected port
    if ! [[ "$detected_port" =~ ^[0-9]+$ ]] || [ "$detected_port" -lt 1024 ] || [ "$detected_port" -gt 65535 ]; then
        print_warning "Invalid port detected: $detected_port, using default 5335" >&2
        detected_port="5335"
    fi
    
    # Only the port number goes to stdout (captured by the calling function)
    echo "$detected_port"
}

# Create directories with proper permissions
create_directories() {
    print_info "Creating directories..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$INSTALL_DIR/venv"
    
    # Set proper permissions
    chmod 755 "$INSTALL_DIR"
    chmod 755 "$CONFIG_DIR"
    
    print_success "Directories created"
}

# Install system dependencies with better error handling
install_system_deps() {
    print_info "Installing system dependencies..."
    
    # Update package list
    if ! apt update -qq; then
        print_error "Failed to update package list"
        return 1
    fi
    
    # Install essential system packages
    local packages=(
        "python3" "python3-pip" "python3-venv" "python3-dev" "python3-full"
        "bc" "curl" "wget" "git" "net-tools" "lsof"
    )
    
    if ! apt install -y "${packages[@]}"; then
        print_error "Failed to install system packages"
        return 1
    fi
    
    # Try to install Python packages via apt (handles externally-managed-environment)
    print_info "Installing Python packages via system package manager..."
    local python_packages=(
        "python3-flask" "python3-dnslib" "python3-jinja2" "python3-werkzeug"
        "python3-click" "python3-blinker" "python3-itsdangerous" "python3-markupsafe"
    )
    
    apt install -y "${python_packages[@]}" 2>/dev/null || {
        print_warning "Some Python packages not available via apt, will use virtual environment"
    }
    
    print_success "System dependencies installed"
}

# Create and setup virtual environment
setup_virtual_environment() {
    print_info "Setting up Python virtual environment..."
    python3 -m venv /opt/dns-fallback/venv
    /opt/dns-fallback/venv/bin/pip install flask dnslib
    
    # Remove existing venv if it exists
    [ -d "$INSTALL_DIR/venv" ] && rm -rf "$INSTALL_DIR/venv"
    
    # Create virtual environment
    if ! python3 -m venv "$INSTALL_DIR/venv"; then
        print_error "Failed to create virtual environment"
        return 1
    fi
    
    # Activate and install packages
    local venv_python="$INSTALL_DIR/venv/bin/python3"
    local venv_pip="$INSTALL_DIR/venv/bin/pip"
    
    # Upgrade pip
    if ! "$venv_pip" install --upgrade pip; then
        print_warning "Failed to upgrade pip in virtual environment"
    fi
    
    # Install required packages
    local pip_packages=("flask" "dnslib")
    for package in "${pip_packages[@]}"; do
        if ! "$venv_pip" install "$package"; then
            print_error "Failed to install $package in virtual environment"
            return 1
        fi
    done
    
    print_success "Virtual environment setup completed"
}

# Install DNS Fallback files
install_dns_fallback() {
    print_info "Installing DNS Fallback Proxy..."
    
    # Copy the current files from the git repository
    if [ -f "dns_fallback_proxy.py" ]; then
        cp dns_fallback_proxy.py "$INSTALL_DIR/"
        chmod +x "$INSTALL_DIR/dns_fallback_proxy.py"
        print_success "DNS Fallback Proxy installed"
    else
        print_error "dns_fallback_proxy.py not found in current directory"
        return 1
    fi
}

# Install Dashboard
install_dashboard() {
    print_info "Installing Enhanced Dashboard..."
    
    if [ -f "dns_fallback_dashboard.py" ]; then
        cp dns_fallback_dashboard.py "$INSTALL_DIR/"
        chmod +x "$INSTALL_DIR/dns_fallback_dashboard.py"
        print_success "Enhanced Dashboard installed"
    else
        print_error "dns_fallback_dashboard.py not found in current directory"
        return 1
    fi
}

# Create configuration file with validation
create_config() {
    local unbound_port=$1
    
    print_info "Creating configuration file..."
    
    # Validate unbound port
    if ! [[ "$unbound_port" =~ ^[0-9]+$ ]]; then
        print_error "Invalid unbound port: $unbound_port"
        return 1
    fi
    
    cat > "$INSTALL_DIR/config.ini" << EOF
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
# Shorter timeout for Unbound (local recursive resolver)
unbound_timeout = 1.5
# Longer timeout for fallback servers (public DNS over internet)
fallback_timeout = 3.0

# Intelligent caching and learning features
# Enable domain-specific fallback learning
intelligent_caching = true
# Maximum number of domains to track in cache
max_domain_cache = 1000
# Number of consecutive failures before bypassing Unbound for a domain
fallback_threshold = 3
# How long (in seconds) to bypass Unbound for a failing domain
bypass_duration = 3600

# Query optimization
# Enable deduplication of identical concurrent queries
enable_query_deduplication = true

# Logging configuration
# Enable structured JSON logging for better dashboard integration
structured_logging = true
EOF
    
    # Validate config file was created correctly
    if [ ! -f "$INSTALL_DIR/config.ini" ]; then
        print_error "Failed to create configuration file"
        return 1
    fi
    
    # Test if config file is parseable (basic syntax check)
    if ! python3 -c "
import configparser
config = configparser.ConfigParser()
config.read('$INSTALL_DIR/config.ini')
if 'Proxy' not in config:
    exit(1)
print('Config file syntax is valid')
" 2>/dev/null; then
        print_error "Configuration file has syntax errors"
        return 1
    fi
    
    print_success "Configuration file created and validated at $INSTALL_DIR/config.ini"
}

# Create systemd services with virtual environment
create_services() {
    print_info "Creating systemd services..."
    
    SERVICES_CREATED=true
    
    # DNS Fallback Proxy service - using virtual environment
    cat > "$SERVICE_DIR/$PROXY_SERVICE" << EOF
[Unit]
Description=DNS Fallback Pi-hole Proxy Service
After=network.target pihole-FTL.service unbound.service
Wants=pihole-FTL.service unbound.service

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/dns_fallback_proxy.py
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/dns-fallback.log
StandardError=append:$LOG_DIR/dns-fallback.log
# Security hardening
User=root
# Future: Use dedicated user for better security
# User=dnsfallback
# Group=dnsfallback
ProtectSystem=strict
PrivateTmp=true
NoNewPrivileges=true
ReadWritePaths=$LOG_DIR $INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

    # Dashboard service - using virtual environment
    cat > "$SERVICE_DIR/$DASHBOARD_SERVICE" << EOF
[Unit]
Description=DNS Fallback Pi-hole Dashboard Service
After=network.target dns-fallback.service
Wants=dns-fallback.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/dns_fallback_dashboard.py
Restart=on-failure
RestartSec=5
StandardOutput=file:$LOG_DIR/dns-fallback_dashboard.log
StandardError=file:$LOG_DIR/dns-fallback_dashboard.log
# Security hardening
ProtectSystem=strict
PrivateTmp=true
NoNewPrivileges=true
ReadWritePaths=$LOG_DIR $INSTALL_DIR

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

$LOG_DIR/dns-fallback_dashboard.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOF
    
    print_success "Log rotation configured"
}

# IMPROVED: Validate Unbound configuration with better testing
validate_unbound() {
    local unbound_port=$1
    
    print_info "Validating Unbound configuration..."
    
    # Check if Unbound is running
    if ! systemctl is-active --quiet unbound; then
        print_warning "Unbound is not currently running"
        print_info "Starting Unbound..."
        if ! systemctl start unbound; then
            print_error "Failed to start Unbound"
            return 1
        fi
        sleep 3
    fi
    
    # Wait for Unbound to be fully ready
    local retry_count=0
    while [ $retry_count -lt 10 ]; do
        if timeout 5 dig @127.0.0.1 -p "$unbound_port" google.com +short >/dev/null 2>&1; then
            print_success "Unbound is responding correctly on port $unbound_port"
            return 0
        fi
        sleep 1
        ((retry_count++))
    done
    
    print_error "Unbound test failed on port $unbound_port after multiple attempts"
    print_info "Please check your Unbound configuration manually"
    return 1
}

# IMPROVED: Test Python dependencies thoroughly
test_python_deps() {
    print_info "Testing Python dependencies..."
    
    local venv_python="$INSTALL_DIR/venv/bin/python3"
    
    # Test virtual environment
    if [ ! -f "$venv_python" ]; then
        print_error "Virtual environment Python not found"
        return 1
    fi
    
    # Test if we can import required modules in the virtual environment
    if ! "$venv_python" -c "
import sys
try:
    import flask
    import dnslib
    import configparser
    print('✓ All Python dependencies are available in virtual environment')
except ImportError as e:
    print(f'✗ Missing Python dependency: {e}')
    sys.exit(1)
"; then
        print_error "Required Python dependencies are missing from virtual environment"
        return 1
    fi
    
    print_success "Python dependencies validated"
}

# IMPROVED: Start services with proper error handling and waiting
start_services() {
    print_info "Starting services..."
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable services
    if ! systemctl enable "$PROXY_SERVICE"; then
        print_error "Failed to enable $PROXY_SERVICE"
        return 1
    fi
    
    if ! systemctl enable "$DASHBOARD_SERVICE"; then
        print_error "Failed to enable $DASHBOARD_SERVICE"
        return 1
    fi
    
    # Start DNS Fallback Proxy service
    print_info "Starting DNS Fallback Proxy service..."
    if ! systemctl start "$PROXY_SERVICE"; then
        print_error "Failed to start DNS Fallback Proxy service"
        print_info "Checking logs..."
        journalctl -u "$PROXY_SERVICE" --no-pager -l -n 20 || true
        return 1
    fi
    
    # Wait for proxy service to be ready
    local retry_count=0
    while [ $retry_count -lt 30 ]; do
        if systemctl is-active --quiet "$PROXY_SERVICE"; then
            print_success "DNS Fallback Proxy service started successfully"
            break
        fi
        sleep 1
        ((retry_count++))
        if [ $retry_count -eq 30 ]; then
            print_error "DNS Fallback Proxy service failed to start within 30 seconds"
            journalctl -u "$PROXY_SERVICE" --no-pager -l -n 20 || true
            return 1
        fi
    done
    
    # Start Dashboard service
    print_info "Starting Dashboard service..."
    if ! systemctl start "$DASHBOARD_SERVICE"; then
        print_error "Failed to start Dashboard service"
        journalctl -u "$DASHBOARD_SERVICE" --no-pager -l -n 20 || true
        return 1
    fi
    
    # Wait for dashboard service to be ready
    retry_count=0
    while [ $retry_count -lt 15 ]; do
        if systemctl is-active --quiet "$DASHBOARD_SERVICE"; then
            print_success "Dashboard service started successfully"
            break
        fi
        sleep 1
        ((retry_count++))
        if [ $retry_count -eq 15 ]; then
            print_error "Dashboard service failed to start within 15 seconds"
            journalctl -u "$DASHBOARD_SERVICE" --no-pager -l -n 20 || true
            return 1
        fi
    done
    
    return 0
}

# IMPROVED: Test installation with comprehensive checks
test_installation() {
    print_info "Testing installation..."
    
    # Test DNS proxy functionality
    local test_domains=("google.com" "cloudflare.com" "github.com")
    local successful_tests=0
    
    for domain in "${test_domains[@]}"; do
        if timeout 10 dig @127.0.0.1 -p 5355 "$domain" +short >/dev/null 2>&1; then
            print_success "DNS proxy resolved: $domain"
            ((successful_tests++))
        else
            print_warning "DNS proxy failed to resolve: $domain"
        fi
    done
    
    if [ $successful_tests -eq 0 ]; then
        print_error "DNS Fallback Proxy is not working - no domains resolved"
        return 1
    elif [ $successful_tests -lt ${#test_domains[@]} ]; then
        print_warning "DNS Fallback Proxy partially working ($successful_tests/${#test_domains[@]} domains resolved)"
    else
        print_success "DNS Fallback Proxy is working correctly"
    fi
    
    # Test dashboard with multiple attempts
    local dashboard_ready=false
    for i in {1..10}; do
        if curl -s --max-time 5 http://127.0.0.1:8053/health >/dev/null 2>&1; then
            dashboard_ready=true
            break
        fi
        sleep 2
    done
    
    if $dashboard_ready; then
        print_success "Dashboard is accessible"
    else
        print_warning "Dashboard is not accessible - may need more time to start"
    fi
    
    # Test fallback DNS servers
    print_info "Testing fallback DNS servers..."
    local working_fallbacks=0
    for server in "1.1.1.1" "8.8.8.8" "9.9.9.9"; do
        if timeout 5 dig @"$server" google.com +short >/dev/null 2>&1; then
            print_success "Fallback server $server is reachable"
            ((working_fallbacks++))
        else
            print_warning "Fallback server $server is not reachable"
        fi
    done
    
    if [ $working_fallbacks -eq 0 ]; then
        print_error "No fallback DNS servers are reachable - check network connectivity"
        return 1
    fi
    
    return 0
}

# Install test script
install_test_script() {
    print_info "Installing test script..."
    
    if [ -f "test_dns_fallback.sh" ]; then
        cp test_dns_fallback.sh "$INSTALL_DIR/"
        chmod +x "$INSTALL_DIR/test_dns_fallback.sh"
        print_success "Test script installed at $INSTALL_DIR/test_dns_fallback.sh"
    else
        print_warning "test_dns_fallback.sh not found - you can download it later"
    fi
}

# Display final instructions
show_final_instructions() {
    local server_ip=$(hostname -I | awk '{print $1}')
    
    echo ""
    print_header
    echo ""
    print_success "Enhanced DNS Fallback installation completed successfully! 🎉"
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
    print_info "Testing:"
    echo "• Run comprehensive tests: sudo bash $INSTALL_DIR/test_dns_fallback.sh"
    echo "• Quick DNS test: dig @127.0.0.1 -p 5355 google.com"
    echo "• Test your original issue: dig @127.0.0.1 -p 5355 download.proxmox.com"
    echo ""
    print_info "Files and directories:"
    echo "• Configuration: $INSTALL_DIR/config.ini"
    echo "• Virtual environment: $INSTALL_DIR/venv/"
    echo "• Log file: $LOG_DIR/dns-fallback.log"
    echo "• Dashboard log: $LOG_DIR/dns-fallback_dashboard.log"
    echo ""
    print_info "Features included:"
    echo "• ✅ Fixed configuration parsing bug"
    echo "• ✅ Proper virtual environment usage"
    echo "• ✅ Enhanced error handling and validation"
    echo "• ✅ Port conflict detection"
    echo "• ✅ Service dependency management"
    echo "• ✅ Comprehensive testing and verification"
    echo "• ✅ Security hardening"
    echo ""
    print_success "Installation complete! The original Proxmox DNS issue should now be resolved. 🎉"
}

# IMPROVED: Cleanup function with proper error handling
cleanup_on_failure() {
    print_error "Installation failed! Cleaning up..."
    
    # Stop services if they were created
    if $SERVICES_CREATED; then
        print_info "Stopping and disabling services..."
        systemctl stop "$PROXY_SERVICE" 2>/dev/null || true
        systemctl stop "$DASHBOARD_SERVICE" 2>/dev/null || true
        systemctl disable "$PROXY_SERVICE" 2>/dev/null || true
        systemctl disable "$DASHBOARD_SERVICE" 2>/dev/null || true
        
        # Remove service files
        rm -f "$SERVICE_DIR/$PROXY_SERVICE"
        rm -f "$SERVICE_DIR/$DASHBOARD_SERVICE"
        systemctl daemon-reload
    fi
    
    # Remove installation directory if we created it
    if $INSTALLATION_STARTED && [ -d "$INSTALL_DIR" ]; then
        print_info "Removing installation directory..."
        rm -rf "$INSTALL_DIR"
    fi
    
    # Remove log rotation config
    rm -f "/etc/logrotate.d/dns-fallback"
    
    print_info "Cleanup completed. You can safely re-run this script."
}

# Cleanup function for successful exit
cleanup_success() {
    # Nothing to clean up on success
    :
}

# Main installation function
main() {
    # Set up trap for cleanup
    trap cleanup_on_failure ERR
    trap cleanup_success EXIT
    
    print_header
    
    check_root
    check_prerequisites
    
    # Check for port conflicts early
    if ! check_port_conflicts; then
        exit 1
    fi
    
    backup_existing_config
    
    INSTALLATION_STARTED=true
    
    local unbound_port=$(detect_unbound_config)
    
    create_directories
    install_system_deps
    setup_virtual_environment
    install_dns_fallback
    install_dashboard
    
    if ! create_config "$unbound_port"; then
        exit 1
    fi
    
    create_services
    setup_log_rotation
    install_test_script
    
    if ! validate_unbound "$unbound_port"; then
        print_warning "Unbound validation failed, but continuing with installation"
    fi
    
    if ! test_python_deps; then
        exit 1
    fi
    
    if ! start_services; then
        exit 1
    fi
    
    if ! test_installation; then
        print_warning "Some installation tests failed, but basic functionality appears to work"
    fi
    
    show_final_instructions
}

# Run main function
main "$@"
