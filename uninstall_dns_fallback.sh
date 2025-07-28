#!/bin/bash

# Enhanced DNS Fallback Uninstall Script

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
    echo -e "${BLUE}  Enhanced DNS Fallback Uninstallation${NC}"
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

# Confirm uninstallation
confirm_uninstall() {
    echo -e "${YELLOW}This will completely remove the Enhanced DNS Fallback system.${NC}"
    echo ""
    print_warning "The following will be removed:"
    echo "• DNS Fallback Proxy service"
    echo "• Enhanced Dashboard service"
    echo "• Configuration files"
    echo "• Log files (optional)"
    echo "• System service files"
    echo ""
    
    while true; do
        read -p "Do you want to continue? (y/N): " yn
        case $yn in
            [Yy]* ) break;;
            [Nn]* | "" ) echo "Uninstallation cancelled."; exit 0;;
            * ) echo "Please answer yes or no.";;
        esac
    done
    
    # Ask about log files
    while true; do
        read -p "Do you want to remove log files? (y/N): " remove_logs
        case $remove_logs in
            [Yy]* ) REMOVE_LOGS=true; break;;
            [Nn]* | "" ) REMOVE_LOGS=false; break;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

# Stop and disable services
stop_services() {
    print_info "Stopping and disabling services..."
    
    # Stop services
    if systemctl is-active --quiet "$PROXY_SERVICE" 2>/dev/null; then
        systemctl stop "$PROXY_SERVICE"
        print_success "Stopped DNS Fallback Proxy service"
    fi
    
    if systemctl is-active --quiet "$DASHBOARD_SERVICE" 2>/dev/null; then
        systemctl stop "$DASHBOARD_SERVICE"
        print_success "Stopped Dashboard service"
    fi
    
    # Disable services
    if systemctl is-enabled --quiet "$PROXY_SERVICE" 2>/dev/null; then
        systemctl disable "$PROXY_SERVICE"
        print_success "Disabled DNS Fallback Proxy service"
    fi
    
    if systemctl is-enabled --quiet "$DASHBOARD_SERVICE" 2>/dev/null; then
        systemctl disable "$DASHBOARD_SERVICE"
        print_success "Disabled Dashboard service"
    fi
}

# Remove service files
remove_service_files() {
    print_info "Removing service files..."
    
    if [ -f "$SERVICE_DIR/$PROXY_SERVICE" ]; then
        rm -f "$SERVICE_DIR/$PROXY_SERVICE"
        print_success "Removed $PROXY_SERVICE"
    fi
    
    if [ -f "$SERVICE_DIR/$DASHBOARD_SERVICE" ]; then
        rm -f "$SERVICE_DIR/$DASHBOARD_SERVICE"
        print_success "Removed $DASHBOARD_SERVICE"
    fi
    
    # Reload systemd
    systemctl daemon-reload
    print_success "Reloaded systemd configuration"
}

# Remove binary files
remove_binaries() {
    print_info "Removing binary files..."
    
    if [ -f "$BIN_DIR/dns_fallback_proxy.py" ]; then
        rm -f "$BIN_DIR/dns_fallback_proxy.py"
        print_success "Removed DNS Fallback Proxy binary"
    fi
    
    if [ -f "$BIN_DIR/dns_fallback_dashboard.py" ]; then
        rm -f "$BIN_DIR/dns_fallback_dashboard.py"
        print_success "Removed Dashboard binary"
    fi
}

# Remove configuration files
remove_config() {
    print_info "Removing configuration files..."
    
    if [ -d "$CONFIG_DIR" ]; then
        rm -rf "$CONFIG_DIR"
        print_success "Removed configuration directory: $CONFIG_DIR"
    fi
    
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        print_success "Removed installation directory: $INSTALL_DIR"
    fi
}

# Remove log rotation
remove_log_rotation() {
    print_info "Removing log rotation configuration..."
    
    if [ -f "/etc/logrotate.d/dns-fallback" ]; then
        rm -f "/etc/logrotate.d/dns-fallback"
        print_success "Removed log rotation configuration"
    fi
}

# Remove log files
remove_logs() {
    if [ "$REMOVE_LOGS" = true ]; then
        print_info "Removing log files..."
        
        if [ -f "$LOG_DIR/dns-fallback.log" ]; then
            rm -f "$LOG_DIR/dns-fallback.log"*
            print_success "Removed log files"
        fi
    else
        print_info "Log files preserved at $LOG_DIR/dns-fallback.log*"
    fi
}

# Remove PID files
remove_pid_files() {
    print_info "Removing PID files..."
    
    if [ -f "/var/run/dns-fallback.pid" ]; then
        rm -f "/var/run/dns-fallback.pid"
        print_success "Removed PID file"
    fi
}

# Check for Pi-hole configuration
check_pihole_config() {
    print_info "Checking Pi-hole configuration..."
    
    # Check if Pi-hole is configured to use our proxy
    if command -v pihole &> /dev/null; then
        local pihole_dns=$(pihole -a -i | grep -i "DNS" || true)
        
        if echo "$pihole_dns" | grep -q "127.0.0.1#5355\|127.0.0.1:5355"; then
            print_warning "Pi-hole is still configured to use the DNS Fallback Proxy!"
            echo ""
            print_info "You need to reconfigure Pi-hole DNS settings:"
            echo "1. Go to Pi-hole Admin → Settings → DNS"
            echo "2. Remove 127.0.0.1#5355 from upstream DNS servers"
            echo "3. Add your preferred DNS servers (e.g., 1.1.1.1, 8.8.8.8)"
            echo "4. Save changes"
            echo ""
            print_warning "Pi-hole DNS queries will fail until you update the configuration!"
        else
            print_success "Pi-hole is not configured to use the DNS Fallback Proxy"
        fi
    else
        print_info "Pi-hole not found on this system"
    fi
}

# Cleanup any remaining processes
cleanup_processes() {
    print_info "Cleaning up any remaining processes..."
    
    # Kill any remaining processes
    local pids=$(pgrep -f "dns_fallback" 2>/dev/null || true)
    
    if [ ! -z "$pids" ]; then
        echo "$pids" | xargs kill -TERM 2>/dev/null || true
        sleep 2
        
        # Force kill if still running
        local remaining_pids=$(pgrep -f "dns_fallback" 2>/dev/null || true)
        if [ ! -z "$remaining_pids" ]; then
            echo "$remaining_pids" | xargs kill -KILL 2>/dev/null || true
            print_success "Forcefully terminated remaining processes"
        fi
        
        print_success "Cleaned up DNS Fallback processes"
    fi
}

# Verify uninstallation
verify_uninstall() {
    print_info "Verifying uninstallation..."
    
    local issues=()
    
    # Check for remaining services
    if systemctl list-unit-files | grep -q "dns-fallback"; then
        issues+=("Systemd services still present")
    fi
    
    # Check for remaining files
    if [ -d "$INSTALL_DIR" ] || [ -d "$CONFIG_DIR" ]; then
        issues+=("Configuration directories still present")
    fi
    
    if [ -f "$BIN_DIR/dns_fallback_proxy.py" ] || [ -f "$BIN_DIR/dns_fallback_dashboard.py" ]; then
        issues+=("Binary files still present")
    fi
    
    # Check for running processes
    if pgrep -f "dns_fallback" >/dev/null 2>&1; then
        issues+=("DNS Fallback processes still running")
    fi
    
    if [ ${#issues[@]} -eq 0 ]; then
        print_success "Uninstallation completed successfully"
    else
        print_warning "Some issues found during verification:"
        for issue in "${issues[@]}"; do
            echo "  - $issue"
        done
    fi
}

# Create backup before uninstall
create_backup() {
    local backup_dir="/opt/dns-fallback-backup-uninstall-$(date +%Y%m%d-%H%M%S)"
    
    print_info "Creating backup before uninstallation..."
    mkdir -p "$backup_dir"
    
    # Backup configuration if exists
    if [ -d "$CONFIG_DIR" ]; then
        cp -r "$CONFIG_DIR" "$backup_dir/"
    fi
    
    # Backup logs if they exist and we're not removing them
    if [ -f "$LOG_DIR/dns-fallback.log" ] && [ "$REMOVE_LOGS" = false ]; then
        cp "$LOG_DIR/dns-fallback.log"* "$backup_dir/" 2>/dev/null || true
    fi
    
    # Backup service files
    if [ -f "$SERVICE_DIR/$PROXY_SERVICE" ]; then
        cp "$SERVICE_DIR/$PROXY_SERVICE" "$backup_dir/"
    fi
    
    if [ -f "$SERVICE_DIR/$DASHBOARD_SERVICE" ]; then
        cp "$SERVICE_DIR/$DASHBOARD_SERVICE" "$backup_dir/"
    fi
    
    print_success "Backup created at: $backup_dir"
}

# Display final message
show_final_message() {
    echo ""
    print_header
    echo ""
    print_success "Enhanced DNS Fallback has been uninstalled!"
    echo ""
    
    if [ "$1" = "pihole_warning" ]; then
        print_warning "IMPORTANT: Don't forget to reconfigure Pi-hole DNS settings!"
        echo ""
    fi
    
    print_info "What was removed:"
    echo "• DNS Fallback Proxy service and binary"
    echo "• Enhanced Dashboard service and binary"
    echo "• Configuration files and directories"
    echo "• Systemd service files"
    echo "• Log rotation configuration"
    
    if [ "$REMOVE_LOGS" = true ]; then
        echo "• Log files"
    fi
    
    echo ""
    print_info "What was preserved:"
    
    if [ "$REMOVE_LOGS" = false ]; then
        echo "• Log files at $LOG_DIR/dns-fallback.log*"
    fi
    
    echo "• System packages (Python, etc.)"
    echo "• Pi-hole and Unbound installations"
    echo ""
    
    print_success "Uninstallation complete! 🎉"
    echo ""
    
    if [ "$1" = "pihole_warning" ]; then
        print_warning "Remember to update Pi-hole DNS configuration before the next DNS query!"
    fi
}

# Main uninstallation function
main() {
    local pihole_warning=""
    
    print_header
    
    check_root
    confirm_uninstall
    create_backup
    
    # Check Pi-hole config before stopping services
    if command -v pihole &> /dev/null; then
        local pihole_dns=$(pihole -a -i | grep -i "DNS" || true)
        if echo "$pihole_dns" | grep -q "127.0.0.1#5355\|127.0.0.1:5355"; then
            pihole_warning="pihole_warning"
        fi
    fi
    
    stop_services
    cleanup_processes
    remove_service_files
    remove_binaries
    remove_config
    remove_log_rotation
    remove_logs
    remove_pid_files
    
    verify_uninstall
    check_pihole_config
    
    show_final_message "$pihole_warning"
}

# Run main function
main "$@"
