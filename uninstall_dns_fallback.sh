#!/bin/bash

# Enhanced DNS Fallback Uninstall Script
# Version: 2.1
# Comprehensive removal with safety checks and rollback options

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
    echo "• DNS Fallback Proxy service and files"
    echo "• Enhanced Dashboard service and files"
    echo "• Configuration files and directories"
    echo "• System service files"
    echo "• Log rotation configuration"
    echo "• Virtual environment (if exists)"
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

    # Ask about system packages
    while true; do
        read -p "Do you want to remove system Python packages (python3-flask, python3-dnslib, bc)? (y/N): " remove_packages
        case $remove_packages in
            [Yy]* ) REMOVE_PACKAGES=true; break;;
            [Nn]* | "" ) REMOVE_PACKAGES=false; break;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

# Check Pi-hole configuration before uninstall
check_pihole_config_pre() {
    print_info "Checking Pi-hole configuration..."
    
    local pihole_issue=""
    
    if command -v pihole &> /dev/null; then
        # Check if Pi-hole is using our DNS proxy
        local pihole_dns=""
        
        # Try multiple methods to get Pi-hole DNS settings
        if [ -f "/etc/pihole/setupVars.conf" ]; then
            pihole_dns=$(grep "PIHOLE_DNS" /etc/pihole/setupVars.conf 2>/dev/null | cut -d'=' -f2 || echo "")
        fi
        
        # Also check dnsmasq config
        if [ -f "/etc/dnsmasq.d/01-pihole.conf" ]; then
            local dnsmasq_servers=$(grep "^server=" /etc/dnsmasq.d/01-pihole.conf 2>/dev/null || echo "")
            if echo "$dnsmasq_servers" | grep -q "127.0.0.1#5355"; then
                pihole_issue="dnsmasq"
            fi
        fi
        
        if echo "$pihole_dns" | grep -q "127.0.0.1#5355" || [ "$pihole_issue" = "dnsmasq" ]; then
            print_warning "Pi-hole is currently configured to use the DNS Fallback Proxy!"
            echo ""
            print_error "CRITICAL: Removing DNS Fallback will break Pi-hole DNS resolution!"
            echo ""
            print_info "You MUST reconfigure Pi-hole DNS settings after uninstallation:"
            echo "1. Go to Pi-hole Admin → Settings → DNS"
            echo "2. Remove 127.0.0.1#5355 from upstream DNS servers"
            echo "3. Add your preferred DNS servers (e.g., 1.1.1.1, 8.8.8.8)"
            echo "4. Save changes"
            echo ""
            
            while true; do
                read -p "Do you understand and want to continue? (y/N): " understand
                case $understand in
                    [Yy]* ) break;;
                    [Nn]* | "" ) echo "Uninstallation cancelled for safety."; exit 0;;
                    * ) echo "Please answer yes or no.";;
                esac
            done
            
            return 1  # Indicate Pi-hole needs reconfiguration
        else
            print_success "Pi-hole is not configured to use the DNS Fallback Proxy"
        fi
    else
        print_info "Pi-hole not found on this system"
    fi
    
    return 0  # Pi-hole OK
}

# Stop and disable services
stop_services() {
    print_info "Stopping and disabling services..."
    
    # Stop services gracefully
    local services=("$DASHBOARD_SERVICE" "$PROXY_SERVICE")
    
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            systemctl stop "$service" || {
                print_warning "$service failed to stop gracefully, forcing stop..."
                systemctl kill "$service" 2>/dev/null || true
                sleep 2
            }
            print_success "Stopped $service"
        else
            print_info "$service was not running"
        fi
        
        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            systemctl disable "$service" || {
                print_warning "Failed to disable $service"
            }
            print_success "Disabled $service"
        fi
    done
}

# Remove service files
remove_service_files() {
    print_info "Removing service files..."
    
    local service_files=("$SERVICE_DIR/$PROXY_SERVICE" "$SERVICE_DIR/$DASHBOARD_SERVICE")
    
    for service_file in "${service_files[@]}"; do
        if [ -f "$service_file" ]; then
            rm -f "$service_file" || {
                print_warning "Failed to remove $service_file"
            }
            print_success "Removed $(basename "$service_file")"
        fi
    done
    
    # Reload systemd
    systemctl daemon-reload || {
        print_warning "Failed to reload systemd daemon"
    }
    print_success "Reloaded systemd configuration"
}

# Remove binary files and directories
remove_binaries() {
    print_info "Removing binary files and directories..."
    
    # Remove legacy binary locations
    local legacy_binaries=("$BIN_DIR/dns_fallback_proxy.py" "$BIN_DIR/dns_fallback_dashboard.py")
    
    for binary in "${legacy_binaries[@]}"; do
        if [ -f "$binary" ]; then
            rm -f "$binary" || {
                print_warning "Failed to remove $binary"
            }
            print_success "Removed $(basename "$binary")"
        fi
    done
    
    # Remove main installation directory
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR" || {
            print_error "Failed to remove installation directory: $INSTALL_DIR"
            return 1
        }
        print_success "Removed installation directory: $INSTALL_DIR"
    fi
    
    # Remove configuration directory
    if [ -d "$CONFIG_DIR" ]; then
        rm -rf "$CONFIG_DIR" || {
            print_warning "Failed to remove configuration directory: $CONFIG_DIR"
        }
        print_success "Removed configuration directory: $CONFIG_DIR"
    fi
}

# Remove log rotation
remove_log_rotation() {
    print_info "Removing log rotation configuration..."
    
    if [ -f "/etc/logrotate.d/dns-fallback" ]; then
        rm -f "/etc/logrotate.d/dns-fallback" || {
            print_warning "Failed to remove log rotation config"
        }
        print_success "Removed log rotation configuration"
    fi
}

# Remove log files
remove_logs() {
    if [ "$REMOVE_LOGS" = true ]; then
        print_info "Removing log files..."
        
        local log_files=(
            "$LOG_DIR/dns-fallback.log*"
            "$LOG_DIR/dns-fallback_dashboard.log*"
        )
        
        for log_pattern in "${log_files[@]}"; do
            if ls $log_pattern 1> /dev/null 2>&1; then
                rm -f $log_pattern || {
                    print_warning "Failed to remove some log files: $log_pattern"
                }
                print_success "Removed log files: $log_pattern"
            fi
        done
    else
        print_info "Log files preserved"
    fi
}

# Remove PID files
remove_pid_files() {
    print_info "Removing PID files..."
    
    local pid_files=("/var/run/dns-fallback.pid" "/tmp/dns-fallback.pid")
    
    for pid_file in "${pid_files[@]}"; do
        if [ -f "$pid_file" ]; then
            rm -f "$pid_file" || {
                print_warning "Failed to remove $pid_file"
            }
            print_success "Removed PID file: $pid_file"
        fi
    done
}

# Remove system packages
remove_system_packages() {
    if [ "$REMOVE_PACKAGES" = true ]; then
        print_info "Removing system Python packages..."
        
        local packages=(
            "python3-flask"
            "python3-dnslib" 
            "python3-jinja2"
            "python3-werkzeug"
            "python3-click"
            "python3-blinker"
            "python3-itsdangerous"
            "python3-markupsafe"
            "bc"
        )
        
        # Only remove packages that were likely installed by us
        local packages_to_remove=()
        
        for pkg in "${packages[@]}"; do
            if dpkg -l | grep -q "^ii.*$pkg "; then
                packages_to_remove+=("$pkg")
            fi
        done
        
        if [ ${#packages_to_remove[@]} -gt 0 ]; then
            print_info "Removing packages: ${packages_to_remove[*]}"
            apt remove -y "${packages_to_remove[@]}" || {
                print_warning "Failed to remove some system packages"
            }
            
            # Clean up unused dependencies
            apt autoremove -y || {
                print_warning "Failed to autoremove unused dependencies"
            }
            
            print_success "Removed system packages"
        else
            print_info "No system packages to remove"
        fi
    else
        print_info "System packages preserved"
    fi
}

# Cleanup any remaining processes
cleanup_processes() {
    print_info "Cleaning up any remaining processes..."
    
    # Kill any remaining DNS fallback processes
    local pids=$(pgrep -f "dns_fallback" 2>/dev/null || true)
    
    if [ ! -z "$pids" ]; then
        print_info "Found remaining DNS Fallback processes, terminating..."
        echo "$pids" | xargs kill -TERM 2>/dev/null || true
        sleep 2
        
        # Force kill if still running
        local remaining_pids=$(pgrep -f "dns_fallback" 2>/dev/null || true)
        if [ ! -z "$remaining_pids" ]; then
            echo "$remaining_pids" | xargs kill -KILL 2>/dev/null || true
            print_success "Forcefully terminated remaining processes"
        else
            print_success "Gracefully terminated remaining processes"
        fi
    fi
}

# Create backup before uninstall
create_backup() {
    local backup_dir="/opt/dns-fallback-backup-uninstall-$(date +%Y%m%d-%H%M%S)"
    
    print_info "Creating backup before uninstallation..."
    mkdir -p "$backup_dir"
    
    # Backup configuration if exists
    if [ -d "$INSTALL_DIR" ]; then
        cp -r "$INSTALL_DIR" "$backup_dir/" 2>/dev/null || {
            print_warning "Failed to backup installation directory"
        }
    fi
    
    if [ -d "$CONFIG_DIR" ]; then
        cp -r "$CONFIG_DIR" "$backup_dir/" 2>/dev/null || {
            print_warning "Failed to backup configuration directory"
        }
    fi
    
    # Backup logs if they exist and we're not removing them
    if [ "$REMOVE_LOGS" = false ]; then
        local log_files=("$LOG_DIR/dns-fallback.log"* "$LOG_DIR/dns-fallback_dashboard.log"*)
        for log_file in "${log_files[@]}"; do
            if [ -f "$log_file" ]; then
                cp "$log_file" "$backup_dir/" 2>/dev/null || true
            fi
        done
    fi
    
    # Backup service files
    local service_files=("$SERVICE_DIR/$PROXY_SERVICE" "$SERVICE_DIR/$DASHBOARD_SERVICE")
    for service_file in "${service_files[@]}"; do
        if [ -f "$service_file" ]; then
            cp "$service_file" "$backup_dir/" 2>/dev/null || true
        fi
    done
    
    print_success "Backup created at: $backup_dir"
    echo "$backup_dir" > /tmp/dns-fallback-uninstall-backup-path
}

# Verify uninstallation
verify_uninstall() {
    print_info "Verifying uninstallation..."
    
    local issues=()
    
    # Check for remaining services
    if systemctl list-unit-files 2>/dev/null | grep -q "dns-fallback"; then
        issues+=("Systemd services still present")
    fi
    
    # Check for remaining files
    if [ -d "$INSTALL_DIR" ] || [ -d "$CONFIG_DIR" ]; then
        issues+=("Installation directories still present")
    fi
    
    if [ -f "$BIN_DIR/dns_fallback_proxy.py" ] || [ -f "$BIN_DIR/dns_fallback_dashboard.py" ]; then
        issues+=("Binary files still present")
    fi
    
    # Check for running processes
    if pgrep -f "dns_fallback" >/dev/null 2>&1; then
        issues+=("DNS Fallback processes still running")
    fi
    
    # Check for remaining log rotation
    if [ -f "/etc/logrotate.d/dns-fallback" ]; then
        issues+=("Log rotation configuration still present")
    fi
    
    if [ ${#issues[@]} -eq 0 ]; then
        print_success "Uninstallation completed successfully"
        return 0
    else
        print_warning "Some issues found during verification:"
        for issue in "${issues[@]}"; do
            echo "  - $issue"
        done
        return 1
    fi
}

# Check Pi-hole configuration after uninstall
check_pihole_config_post() {
    print_info "Final Pi-hole configuration check..."
    
    if command -v pihole &> /dev/null; then
        # Check if Pi-hole is still configured to use our proxy
        local still_configured=false
        
        if [ -f "/etc/pihole/setupVars.conf" ]; then
            if grep -q "127.0.0.1#5355" /etc/pihole/setupVars.conf 2>/dev/null; then
                still_configured=true
            fi
        fi
        
        if [ -f "/etc/dnsmasq.d/01-pihole.conf" ]; then
            if grep -q "127.0.0.1#5355" /etc/dnsmasq.d/01-pihole.conf 2>/dev/null; then
                still_configured=true
            fi
        fi
        
        if [ "$still_configured" = true ]; then
            print_error "CRITICAL: Pi-hole is STILL configured to use the DNS Fallback Proxy!"
            print_error "DNS resolution will NOT work until you reconfigure Pi-hole!"
            return 1
        else
            print_success "Pi-hole configuration appears to be updated"
        fi
    fi
    
    return 0
}

# Display final message
show_final_message() {
    local pihole_warning="$1"
    local backup_path=""
    
    if [ -f "/tmp/dns-fallback-uninstall-backup-path" ]; then
        backup_path=$(cat /tmp/dns-fallback-uninstall-backup-path)
        rm -f /tmp/dns-fallback-uninstall-backup-path
    fi
    
    echo ""
    print_header
    echo ""
    print_success "Enhanced DNS Fallback has been uninstalled! 🎉"
    echo ""
    
    if [ "$pihole_warning" = "pihole_warning" ]; then
        print_error "⚠️  CRITICAL: RECONFIGURE PI-HOLE DNS SETTINGS NOW!"
        echo ""
        print_info "Your Pi-hole will NOT resolve DNS queries until you:"
        echo "1. Go to Pi-hole Admin → Settings → DNS"
        echo "2. Remove 127.0.0.1#5355 from upstream DNS servers"
        echo "3. Add your preferred DNS servers (e.g., 1.1.1.1, 8.8.8.8)"
        echo "4. Save changes"
        echo ""
    fi
    
    print_info "What was removed:"
    echo "• DNS Fallback Proxy service and binary"
    echo "• Enhanced Dashboard service and binary"
    echo "• Configuration files and directories"
    echo "• Systemd service files"
    echo "• Log rotation configuration"
    echo "• Virtual environment"
    
    if [ "$REMOVE_LOGS" = true ]; then
        echo "• Log files"
    fi
    
    if [ "$REMOVE_PACKAGES" = true ]; then
        echo "• System Python packages (flask, dnslib, bc)"
    fi
    
    echo ""
    print_info "What was preserved:"
    
    if [ "$REMOVE_LOGS" = false ]; then
        echo "• Log files (if they existed)"
    fi
    
    if [ "$REMOVE_PACKAGES" = false ]; then
        echo "• System Python packages"
    fi
    
    echo "• System packages (Python, etc.)"
    echo "• Pi-hole and Unbound installations"
    
    if [ ! -z "$backup_path" ]; then
        echo "• Full backup at: $backup_path"
    fi
    
    echo ""
    print_success "Uninstallation complete! 🎉"
    echo ""
    
    if [ "$pihole_warning" = "pihole_warning" ]; then
        print_error "🚨 DON'T FORGET: Update Pi-hole DNS configuration immediately!"
    fi
}

# Main uninstallation function
main() {
    local pihole_warning=""
    
    print_header
    
    check_root
    confirm_uninstall
    
    # Check Pi-hole config before starting
    if ! check_pihole_config_pre; then
        pihole_warning="pihole_warning"
    fi
    
    create_backup
    stop_services
    cleanup_processes
    remove_service_files
    remove_binaries
    remove_log_rotation
    remove_logs
    remove_pid_files
    
    if [ "$REMOVE_PACKAGES" = true ]; then
        remove_system_packages
    fi
    
    # Verify uninstallation
    if ! verify_uninstall; then
        print_warning "Some components may not have been completely removed"
        print_info "Check the verification messages above"
    fi
    
    # Final Pi-hole check
    if ! check_pihole_config_post; then
        pihole_warning="pihole_warning"
    fi
    
    show_final_message "$pihole_warning"
}

# Cleanup function for script errors
cleanup_script() {
    if [ $? -ne 0 ]; then
        print_error "Uninstallation encountered errors!"
        print_info "Check the error messages above"
        print_info "Some components may need manual removal"
        
        if [ -f "/tmp/dns-fallback-uninstall-backup-path" ]; then
            local backup_path=$(cat /tmp/dns-fallback-uninstall-backup-path)
            print_info "Backup available at: $backup_path"
        fi
    fi
}

# Set trap for cleanup
trap cleanup_script EXIT

# Run main function
main "$@"
