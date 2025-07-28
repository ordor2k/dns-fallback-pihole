#!/bin/bash

# DNS Fallback Pi-hole Update Script
# Version: 2.0
# Description: Updates DNS Fallback Pi-hole system with enhanced error handling and validation

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/opt/dns-fallback"
SYSTEMD_DIR="/etc/systemd/system"
LOGROTATE_DIR="/etc/logrotate.d"
LOG_DIR="/var/log/dns-fallback"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

# Cleanup function for exit
cleanup() {
    if [ $? -ne 0 ]; then
        log_error "Update failed! Check the error messages above."
        log "You may need to restore from backup or run the install script again."
        
        # Show service status for debugging
        log "Current service status:"
        systemctl status dns-fallback.service --no-pager -l 2>/dev/null || true
        systemctl status dns-fallback-dashboard.service --no-pager -l 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check service status
check_service_status() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        log_success "$service_name is running"
        return 0
    else
        log_error "$service_name is not running"
        systemctl status "$service_name" --no-pager -l || true
        return 1
    fi
}

# Function to validate configuration file
validate_config() {
    local config_file="$1"
    if [ -f "$config_file" ]; then
        log "Validating configuration file..."
        python3 -c "
import configparser
import sys
try:
    config = configparser.ConfigParser()
    config.read('$config_file')
    # Check for required sections (adjust as needed)
    required_sections = ['dns', 'logging', 'dashboard']
    for section in required_sections:
        if not config.has_section(section):
            print(f'Missing required section: {section}')
            sys.exit(1)
    print('Configuration file validation passed.')
except configparser.Error as e:
    print(f'Configuration file parsing error: {e}')
    sys.exit(1)
except Exception as e:
    print(f'Configuration file validation error: {e}')
    sys.exit(1)
" || {
            log_error "Configuration file validation failed"
            return 1
        }
        log_success "Configuration file is valid"
    fi
}

# Function to create necessary directories
create_directories() {
    log "Creating necessary directories..."
    
    local dirs=("$PROJECT_DIR" "$LOG_DIR")
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir" || {
                log_error "Failed to create directory: $dir"
                return 1
            }
            log_success "Created directory: $dir"
        fi
    done
}

# Function to backup current installation
backup_installation() {
    if [ -d "$PROJECT_DIR" ]; then
        local backup_dir="/opt/dns-fallback-backup-$(date +%Y%m%d_%H%M%S)"
        log "Creating backup of current installation..."
        
        cp -r "$PROJECT_DIR" "$backup_dir" || {
            log_warning "Failed to create full backup, continuing anyway..."
            return 0
        }
        
        log_success "Backup created at: $backup_dir"
        echo "$backup_dir" > /tmp/dns-fallback-backup-path
    else
        log_warning "No existing installation found to backup"
    fi
}

# Function to check network connectivity
check_connectivity() {
    log "Checking network connectivity..."
    
    if ! ping -c 1 -W 5 github.com >/dev/null 2>&1; then
        if ! ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1; then
            log_error "No internet connectivity detected"
            return 1
        fi
        log_warning "GitHub may be unreachable, but internet is available"
    fi
    
    log_success "Network connectivity verified"
}

# Function to validate git repository
validate_repository() {
    log "Validating git repository..."
    
    cd "$SCRIPT_DIR"
    
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_error "This script must be run from the root of the dns-fallback-pihole git repository"
        return 1
    fi
    
    # Check if we're on the correct repository
    local repo_url
    repo_url=$(git config --get remote.origin.url 2>/dev/null || echo "")
    if [[ ! "$repo_url" =~ dns-fallback-pihole ]]; then
        log_warning "This doesn't appear to be the dns-fallback-pihole repository"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
    fi
    
    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        log_warning "You have uncommitted changes in the repository"
        log "These changes may be overwritten during update"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
    fi
    
    log_success "Repository validation passed"
}

# Function to update dependencies
update_dependencies() {
    log "Checking and updating Python dependencies..."
    
    # Update pip first
    python3 -m pip install --upgrade pip >/dev/null 2>&1 || {
        log_warning "Failed to upgrade pip"
    }
    
    # Check if requirements.txt exists
    if [ -f "requirements.txt" ]; then
        pip3 install -r requirements.txt --upgrade || {
            log_warning "Failed to install from requirements.txt"
        }
    else
        # Install known dependencies
        local deps=("flask" "dnslib")
        for dep in "${deps[@]}"; do
            pip3 install --upgrade "$dep" >/dev/null 2>&1 || {
                log_warning "Failed to update dependency: $dep"
            }
        done
    fi
    
    log_success "Dependencies updated"
}

# Function to stop services
stop_services() {
    log "Stopping DNS Fallback services..."
    
    local services=("dns-fallback-dashboard.service" "dns-fallback.service")
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            systemctl stop "$service" || {
                log_warning "$service failed to stop gracefully, forcing stop..."
                systemctl kill "$service" 2>/dev/null || true
                sleep 2
            }
            log_success "Stopped $service"
        else
            log_warning "$service was not running"
        fi
    done
}

# Function to copy files with validation
copy_files() {
    log "Copying updated project files to system directories..."
    
    # Define file mappings: source -> destination
    declare -A file_map=(
        ["dns_fallback_proxy.py"]="$PROJECT_DIR/"
        ["dns_fallback_dashboard.py"]="$PROJECT_DIR/"
        ["dns-fallback.service"]="$SYSTEMD_DIR/"
        ["dns-fallback-dashboard.service"]="$SYSTEMD_DIR/"
    )
    
    # Copy main files
    for src in "${!file_map[@]}"; do
        local dest="${file_map[$src]}"
        if [ -f "$src" ]; then
            cp "$src" "$dest" || {
                log_error "Failed to copy $src to $dest"
                return 1
            }
            log_success "Copied $src"
        else
            log_error "Source file not found: $src"
            return 1
        fi
    done
    
    # Handle optional files
    if [ -f "logrotate/dns-fallback" ]; then
        cp "logrotate/dns-fallback" "$LOGROTATE_DIR/" || {
            log_warning "Failed to copy logrotate config"
        }
        log_success "Copied logrotate configuration"
    else
        log_warning "logrotate/dns-fallback config not found, skipping"
    fi
}

# Function to handle configuration file
handle_config() {
    local config_file="$PROJECT_DIR/config.ini"
    local replace_config=0
    
    # Check for --replace-config argument
    for arg in "$@"; do
        if [ "$arg" == "--replace-config" ]; then
            replace_config=1
            break
        fi
    done
    
    if [ $replace_config -eq 1 ]; then
        if [ -f "$config_file" ]; then
            local backup_file="$config_file.backup.$(date +%Y%m%d_%H%M%S)"
            log "Backing up existing config.ini to $backup_file"
            cp "$config_file" "$backup_file" || {
                log_error "Failed to backup config.ini"
                return 1
            }
        fi
        
        if [ -f "config.ini" ]; then
            cp "config.ini" "$PROJECT_DIR/" || {
                log_error "Failed to copy config.ini"
                return 1
            }
            log_success "config.ini replaced"
        else
            log_warning "config.ini not found in repository"
        fi
    else
        log "NOTE: Your 'config.ini' file is NOT overwritten during update to preserve your settings"
        log "      To replace it, re-run with: sudo bash update_dns_fallback.sh --replace-config"
        log "      Please check 'CHANGELOG.md' for any new configuration options"
        
        # Copy config.ini if it doesn't exist
        if [ ! -f "$config_file" ] && [ -f "config.ini" ]; then
            cp "config.ini" "$PROJECT_DIR/" || {
                log_warning "Failed to copy default config.ini"
            }
            log_success "Default config.ini copied (file didn't exist)"
        fi
    fi
    
    # Validate the configuration file
    validate_config "$config_file"
}

# Function to set permissions
set_permissions() {
    log "Setting appropriate file permissions..."
    
    # Set executable permissions for Python scripts
    chmod 755 "$PROJECT_DIR"/dns_fallback_proxy.py 2>/dev/null || {
        log_warning "Failed to set permissions for proxy script"
    }
    chmod 755 "$PROJECT_DIR"/dns_fallback_dashboard.py 2>/dev/null || {
        log_warning "Failed to set permissions for dashboard script"
    }
    
    # Set service file permissions
    chmod 644 "$SYSTEMD_DIR"/dns-fallback.service 2>/dev/null || {
        log_warning "Failed to set permissions for proxy service file"
    }
    chmod 644 "$SYSTEMD_DIR"/dns-fallback-dashboard.service 2>/dev/null || {
        log_warning "Failed to set permissions for dashboard service file"
    }
    
    # Set logrotate permissions
    if [ -f "$LOGROTATE_DIR/dns-fallback" ]; then
        chmod 644 "$LOGROTATE_DIR"/dns-fallback 2>/dev/null || {
            log_warning "Failed to set permissions for logrotate config"
        }
    fi
    
    # Set log directory permissions
    if [ -d "$LOG_DIR" ]; then
        chown -R root:root "$LOG_DIR" 2>/dev/null || {
            log_warning "Failed to set ownership for log directory"
        }
        chmod 755 "$LOG_DIR" 2>/dev/null || {
            log_warning "Failed to set permissions for log directory"
        }
    fi
    
    log_success "Permissions set"
}

# Function to restart services
restart_services() {
    log "Reloading systemd daemon..."
    systemctl daemon-reload || {
        log_error "Failed to reload systemd daemon"
        return 1
    }
    
    log "Restarting DNS Fallback services..."
    local services=("dns-fallback.service" "dns-fallback-dashboard.service")
    
    for service in "${services[@]}"; do
        systemctl restart "$service" || {
            log_error "Failed to restart $service"
            return 1
        }
        log_success "Restarted $service"
    done
    
    # Give services time to start
    sleep 3
    
    # Verify services are running
    log "Verifying services are running..."
    local all_services_ok=true
    for service in "${services[@]}"; do
        if ! check_service_status "$service"; then
            all_services_ok=false
        fi
    done
    
    if [ "$all_services_ok" = false ]; then
        log_error "One or more services failed to start properly"
        return 1
    fi
    
    log_success "All services are running successfully"
}

# Function to restart pihole
restart_pihole() {
    log "Restarting Pi-hole FTL (dnsmasq) service..."
    
    if command_exists pihole; then
        pihole reloaddns || {
            log_warning "Failed to reload Pi-hole DNS. Trying alternative method..."
            systemctl restart pihole-FTL 2>/dev/null || {
                log_warning "Failed to restart Pi-hole FTL. You may need to restart it manually."
                return 0
            }
        }
        log_success "Pi-hole DNS reloaded"
    else
        log_warning "Pi-hole command not found, skipping Pi-hole restart"
    fi
}

# Function to display update summary
show_summary() {
    log_success "DNS Fallback Pi-hole update complete! 🎉"
    echo
    log "Update Summary:"
    log "- Services updated and restarted"
    log "- Configuration preserved (unless --replace-config was used)"
    log "- Dependencies updated"
    
    if [ -f "/tmp/dns-fallback-backup-path" ]; then
        local backup_path
        backup_path=$(cat /tmp/dns-fallback-backup-path)
        log "- Backup created at: $backup_path"
        rm -f /tmp/dns-fallback-backup-path
    fi
    
    echo
    log "Important reminders:"
    log "- Check CHANGELOG.md for any new configuration options"
    log "- Monitor logs for any issues: journalctl -u dns-fallback.service -f"
    log "- Dashboard should be available at: http://$(hostname -I | awk '{print $1}'):8053"
    
    # Show current service status
    echo
    log "Current service status:"
    systemctl status dns-fallback.service --no-pager -l || true
    systemctl status dns-fallback-dashboard.service --no-pager -l || true
}

# Main execution function
main() {
    log "Starting DNS Fallback Pi-hole update process..."
    
    # Parse arguments
    local show_help=false
    for arg in "$@"; do
        case $arg in
            --help|-h)
                show_help=true
                ;;
        esac
    done
    
    if [ "$show_help" = true ]; then
        echo "DNS Fallback Pi-hole Update Script"
        echo "Usage: sudo bash update_dns_fallback.sh [OPTIONS]"
        echo
        echo "Options:"
        echo "  --replace-config    Replace existing config.ini with the one from repository"
        echo "  --help, -h          Show this help message"
        echo
        echo "This script will:"
        echo "  - Update all project files from the git repository"
        echo "  - Preserve your existing configuration (unless --replace-config is used)"
        echo "  - Update Python dependencies"
        echo "  - Restart all services"
        echo "  - Create a backup of your current installation"
        exit 0
    fi
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root: sudo ./update_dns_fallback.sh"
        exit 1
    fi
    
    # Check required commands
    local required_commands=("git" "python3" "pip3" "systemctl")
    for cmd in "${required_commands[@]}"; do
        if ! command_exists "$cmd"; then
            log_error "Required command not found: $cmd"
            exit 1
        fi
    done
    
    # Execute update steps
    check_connectivity
    validate_repository
    create_directories
    backup_installation
    stop_services
    
    log "Pulling latest changes from GitHub..."
    git pull || {
        log_error "Failed to pull latest changes. Please check your network or git configuration."
        exit 1
    }
    log_success "Latest changes pulled successfully"
    
    update_dependencies
    copy_files
    handle_config "$@"
    set_permissions
    restart_services
    restart_pihole
    show_summary
}

# Execute main function with all arguments
main "$@"
