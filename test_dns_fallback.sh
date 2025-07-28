#!/bin/bash

# Enhanced DNS Fallback Testing Script
# Tests the full chain: Pi-hole → DNS Proxy → Unbound → Fallback

# Remove the problematic set -e that was causing early exits
# set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROXY_IP="127.0.0.1"
PROXY_PORT="5355"
UNBOUND_IP="127.0.0.1"
UNBOUND_PORT="5335"
DASHBOARD_URL="http://127.0.0.1:8053"

# Test domains
BASIC_DOMAINS=("google.com" "cloudflare.com" "github.com")
CDN_DOMAINS=("cdn.jsdelivr.net" "ajax.googleapis.com" "fonts.googleapis.com")
PROBLEMATIC_DOMAINS=("some-edge-case.example" "non-existent-domain-test.com")

# Print functions
print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  Enhanced DNS Fallback Testing${NC}"
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

print_test_header() {
    echo -e "${BLUE}--- $1 ---${NC}"
}

# Test DNS resolution
test_dns_resolution() {
    local server=$1
    local port=$2
    local domain=$3
    local timeout=${4:-5}
    
    if timeout "$timeout" dig @"$server" -p "$port" "$domain" +short +time=2 >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Test DNS resolution with timing
test_dns_with_timing() {
    local server=$1
    local port=$2
    local domain=$3
    local timeout=${4:-5}
    
    local start_time=$(date +%s.%N)
    local result=$(timeout "$timeout" dig @"$server" -p "$port" "$domain" +short +time=2 2>/dev/null || echo "FAILED")
    local end_time=$(date +%s.%N)
    local response_time=$(echo "$end_time - $start_time" | bc -l 2>/dev/null || echo "0")
    
    if [ "$result" != "FAILED" ] && [ ! -z "$result" ]; then
        echo "SUCCESS:${response_time}"
    else
        echo "FAILED:${response_time}"
    fi
}

# Test service status
test_service_status() {
    print_test_header "Service Status Tests"
    
    # Test DNS Fallback Proxy service
    if systemctl is-active --quiet dns-fallback.service; then
        print_success "DNS Fallback Proxy service is running"
    else
        print_error "DNS Fallback Proxy service is not running"
        systemctl status dns-fallback.service --no-pager || true
    fi
    
    # Test Dashboard service
    if systemctl is-active --quiet dns-fallback-dashboard.service; then
        print_success "Dashboard service is running"
    else
        print_error "Dashboard service is not running"
        systemctl status dns-fallback-dashboard.service --no-pager || true
    fi
    
    # Test Unbound service
    if systemctl is-active --quiet unbound.service; then
        print_success "Unbound service is running"
    else
        print_error "Unbound service is not running"
        systemctl status unbound.service --no-pager || true
    fi
    
    # Test Pi-hole service
    if systemctl is-active --quiet pihole-FTL.service; then
        print_success "Pi-hole FTL service is running"
    else
        print_warning "Pi-hole FTL service is not running"
    fi
    
    echo ""
}

# Test network connectivity
test_network_connectivity() {
    print_test_header "Network Connectivity Tests"
    
    # Test if proxy port is listening
    if ss -tuln | grep -q ":$PROXY_PORT "; then
        print_success "DNS Proxy is listening on port $PROXY_PORT"
    else
        print_error "DNS Proxy is not listening on port $PROXY_PORT"
    fi
    
    # Test if Unbound port is listening
    if ss -tuln | grep -q ":$UNBOUND_PORT "; then
        print_success "Unbound is listening on port $UNBOUND_PORT"
    else
        print_error "Unbound is not listening on port $UNBOUND_PORT"
    fi
    
    # Test dashboard accessibility
    if curl -s "$DASHBOARD_URL/health" >/dev/null 2>&1; then
        print_success "Dashboard is accessible"
    else
        print_error "Dashboard is not accessible at $DASHBOARD_URL"
    fi
    
    echo ""
}

# Test direct Unbound resolution
test_unbound_direct() {
    print_test_header "Direct Unbound Resolution Tests"
    
    local success_count=0
    local total_tests=${#BASIC_DOMAINS[@]}
    
    for domain in "${BASIC_DOMAINS[@]}"; do
        if test_dns_resolution "$UNBOUND_IP" "$UNBOUND_PORT" "$domain"; then
            print_success "Unbound resolved: $domain"
            success_count=$((success_count + 1))
        else
            print_error "Unbound failed to resolve: $domain"
        fi
    done
    
    local success_rate=$((success_count * 100 / total_tests))
    echo ""
    print_info "Unbound direct resolution success rate: $success_rate% ($success_count/$total_tests)"
    echo ""
}

# Test DNS proxy resolution
test_proxy_resolution() {
    print_test_header "DNS Proxy Resolution Tests"
    
    local success_count=0
    local total_tests=${#BASIC_DOMAINS[@]}
    
    for domain in "${BASIC_DOMAINS[@]}"; do
        local result=$(test_dns_with_timing "$PROXY_IP" "$PROXY_PORT" "$domain")
        local status=$(echo "$result" | cut -d: -f1)
        local timing=$(echo "$result" | cut -d: -f2)
        
        if [ "$status" = "SUCCESS" ]; then
            print_success "Proxy resolved: $domain (${timing}s)"
            success_count=$((success_count + 1))
        else
            print_error "Proxy failed to resolve: $domain"
        fi
    done
    
    local success_rate=$((success_count * 100 / total_tests))
    echo ""
    print_info "DNS Proxy resolution success rate: $success_rate% ($success_count/$total_tests)"
    echo ""
}

# Test CDN domain handling
test_cdn_domains() {
    print_test_header "CDN Domain Resolution Tests"
    
    print_info "Testing domains that typically require fallback..."
    
    local fallback_count=0
    local total_tests=${#CDN_DOMAINS[@]}
    
    for domain in "${CDN_DOMAINS[@]}"; do
        # Test Unbound first
        local unbound_success=false
        if test_dns_resolution "$UNBOUND_IP" "$UNBOUND_PORT" "$domain" 2; then
            unbound_success=true
        fi
        
        # Test through proxy
        local result=$(test_dns_with_timing "$PROXY_IP" "$PROXY_PORT" "$domain")
        local status=$(echo "$result" | cut -d: -f1)
        local timing=$(echo "$result" | cut -d: -f2)
        
        if [ "$status" = "SUCCESS" ]; then
            if [ "$unbound_success" = false ]; then
                print_success "Proxy resolved via fallback: $domain (${timing}s)"
                fallback_count=$((fallback_count + 1))
            else
                print_success "Proxy resolved via Unbound: $domain (${timing}s)"
            fi
        else
            print_error "Proxy failed to resolve: $domain"
        fi
    done
    
    echo ""
    print_info "CDN domains requiring fallback: $fallback_count/$total_tests"
    echo ""
}

# Test fallback mechanism
test_fallback_mechanism() {
    print_test_header "Fallback Mechanism Tests"
    
    print_info "Testing fallback by temporarily stopping Unbound..."
    
    # Stop Unbound temporarily
    systemctl stop unbound.service
    sleep 2
    
    local fallback_success=0
    local total_tests=${#BASIC_DOMAINS[@]}
    
    for domain in "${BASIC_DOMAINS[@]}"; do
        local result=$(test_dns_with_timing "$PROXY_IP" "$PROXY_PORT" "$domain" 10)
        local status=$(echo "$result" | cut -d: -f1)
        local timing=$(echo "$result" | cut -d: -f2)
        
        if [ "$status" = "SUCCESS" ]; then
            print_success "Fallback resolved: $domain (${timing}s)"
            fallback_success=$((fallback_success + 1))
        else
            print_error "Fallback failed to resolve: $domain"
        fi
    done
    
    # Restart Unbound
    print_info "Restarting Unbound..."
    systemctl start unbound.service
    sleep 3
    
    echo ""
    print_info "Fallback mechanism success rate: $((fallback_success * 100 / total_tests))% ($fallback_success/$total_tests)"
    echo ""
}

# Test performance comparison
test_performance_comparison() {
    print_test_header "Performance Comparison Tests"
    
    local domain="google.com"
    local test_count=5
    
    print_info "Running $test_count resolution tests for $domain..."
    
    # Test Unbound directly
    local unbound_times=()
    for i in $(seq 1 $test_count); do
        local result=$(test_dns_with_timing "$UNBOUND_IP" "$UNBOUND_PORT" "$domain")
        local timing=$(echo "$result" | cut -d: -f2)
        unbound_times+=("$timing")
    done
    
    # Test through proxy
    local proxy_times=()
    for i in $(seq 1 $test_count); do
        local result=$(test_dns_with_timing "$PROXY_IP" "$PROXY_PORT" "$domain")
        local timing=$(echo "$result" | cut -d: -f2)
        proxy_times+=("$timing")
    done
    
    # Calculate averages
    local unbound_avg=0
    for time in "${unbound_times[@]}"; do
        unbound_avg=$(echo "$unbound_avg + $time" | bc -l)
    done
    unbound_avg=$(echo "scale=3; $unbound_avg / $test_count" | bc -l)
    
    local proxy_avg=0
    for time in "${proxy_times[@]}"; do
        proxy_avg=$(echo "$proxy_avg + $time" | bc -l)
    done
    proxy_avg=$(echo "scale=3; $proxy_avg / $test_count" | bc -l)
    
    print_info "Average response times:"
    echo "  Direct Unbound: ${unbound_avg}s"
    echo "  Through Proxy:  ${proxy_avg}s"
    
    local overhead=$(echo "scale=1; ($proxy_avg - $unbound_avg) * 1000" | bc -l)
    echo "  Proxy overhead: ${overhead}ms"
    echo ""
}

# Test log generation
test_log_generation() {
    print_test_header "Log Generation Tests"
    
    local log_file="/var/log/dns-fallback.log"
    
    if [ -f "$log_file" ]; then
        local initial_size=$(stat -c%s "$log_file")
        
        # Generate some queries
        for domain in "${BASIC_DOMAINS[@]}"; do
            dig @"$PROXY_IP" -p "$PROXY_PORT" "$domain" +short >/dev/null 2>&1 || true
        done
        
        sleep 2
        
        local final_size=$(stat -c%s "$log_file")
        
        if [ "$final_size" -gt "$initial_size" ]; then
            print_success "Log file is being updated"
            local new_entries=$((final_size - initial_size))
            print_info "Added $new_entries bytes to log file"
        else
            print_warning "Log file does not appear to be updating"
        fi
        
        # Check log format
        local recent_logs=$(tail -5 "$log_file" 2>/dev/null || echo "")
        if echo "$recent_logs" | grep -q "DNS_QUERY\|timestamp"; then
            print_success "Log entries appear to be in correct format"
        else
            print_warning "Log format may not be structured correctly"
        fi
    else
        print_error "Log file not found at $log_file"
    fi
    
    echo ""
}

# Test dashboard functionality
test_dashboard() {
    print_test_header "Dashboard Functionality Tests"
    
    # Test health endpoint
    if curl -s "$DASHBOARD_URL/health" | grep -q "healthy\|status"; then
        print_success "Dashboard health endpoint is working"
    else
        print_error "Dashboard health endpoint is not responding correctly"
    fi
    
    # Test analytics endpoint
    if curl -s "$DASHBOARD_URL/api/analytics" | grep -q "summary\|total_queries"; then
        print_success "Dashboard analytics endpoint is working"
    else
        print_error "Dashboard analytics endpoint is not responding correctly"
    fi
    
    # Test main dashboard page
    if curl -s "$DASHBOARD_URL/" | grep -q "Enhanced DNS Fallback Dashboard"; then
        print_success "Dashboard main page is loading"
    else
        print_error "Dashboard main page is not loading correctly"
    fi
    
    echo ""
}

# Test Pi-hole integration
test_pihole_integration() {
    print_test_header "Pi-hole Integration Tests"
    
    if command -v pihole &> /dev/null; then
        # Check if Pi-hole is configured to use our proxy
        local pihole_upstream=$(pihole -a -i 2>/dev/null | grep -i "DNS" || echo "No DNS info found")
        
        if echo "$pihole_upstream" | grep -q "127.0.0.1.*535[35]"; then
            print_success "Pi-hole is configured to use DNS Fallback Proxy"
        else
            print_warning "Pi-hole may not be configured to use DNS Fallback Proxy"
            print_info "Current Pi-hole upstream DNS:"
            echo "$pihole_upstream"
        fi
        
        # Test resolution through Pi-hole
        if command -v pihole &> /dev/null && systemctl is-active --quiet pihole-FTL.service; then
            if test_dns_resolution "127.0.0.1" "53" "google.com"; then
                print_success "Pi-hole is resolving queries (full chain test)"
            else
                print_error "Pi-hole resolution test failed"
            fi
        fi
    else
        print_warning "Pi-hole command not found - cannot test integration"
    fi
    
    echo ""
}

# Generate test report
generate_report() {
    local report_file="/tmp/dns-fallback-test-report-$(date +%Y%m%d-%H%M%S).txt"
    
    print_info "Generating test report..."
    
    cat > "$report_file" << EOF
Enhanced DNS Fallback Test Report
Generated: $(date)
System: $(uname -a)

=== Service Status ===
DNS Fallback Proxy: $(systemctl is-active dns-fallback.service 2>/dev/null || echo "inactive")
Dashboard: $(systemctl is-active dns-fallback-dashboard.service 2>/dev/null || echo "inactive")
Unbound: $(systemctl is-active unbound.service 2>/dev/null || echo "inactive")
Pi-hole FTL: $(systemctl is-active pihole-FTL.service 2>/dev/null || echo "inactive")

=== Network Status ===
Proxy Port ($PROXY_PORT): $(ss -tuln | grep ":$PROXY_PORT " >/dev/null && echo "Listening" || echo "Not listening")
Unbound Port ($UNBOUND_PORT): $(ss -tuln | grep ":$UNBOUND_PORT " >/dev/null && echo "Listening" || echo "Not listening")
Dashboard URL: $(curl -s "$DASHBOARD_URL/health" >/dev/null && echo "Accessible" || echo "Not accessible")

=== DNS Resolution Tests ===
EOF

    # Add resolution test results
    for domain in "${BASIC_DOMAINS[@]}"; do
        local unbound_result=$(test_dns_resolution "$UNBOUND_IP" "$UNBOUND_PORT" "$domain" 2 && echo "SUCCESS" || echo "FAILED")
        local proxy_result=$(test_dns_resolution "$PROXY_IP" "$PROXY_PORT" "$domain" 5 && echo "SUCCESS" || echo "FAILED")
        echo "$domain: Unbound=$unbound_result, Proxy=$proxy_result" >> "$report_file"
    done
    
    cat >> "$report_file" << EOF

=== Log File Status ===
Log file exists: $([ -f "/var/log/dns-fallback.log" ] && echo "Yes" || echo "No")
Log file size: $([ -f "/var/log/dns-fallback.log" ] && du -h "/var/log/dns-fallback.log" | cut -f1 || echo "N/A")
Recent log entries: $([ -f "/var/log/dns-fallback.log" ] && tail -3 "/var/log/dns-fallback.log" | wc -l || echo "0")

=== Configuration ===
Config file: $([ -f "/opt/dns-fallback/config.ini" ] && echo "Present" || echo "Missing")
Install directory: $([ -d "/opt/dns-fallback" ] && echo "Present" || echo "Missing")

EOF
    
    print_success "Test report generated: $report_file"
}

# Main testing function
main() {
    print_header
    
    print_info "Starting comprehensive DNS Fallback testing..."
    print_info "This may take several minutes to complete."
    echo ""
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        print_warning "Some tests require root privileges for accurate results"
        print_info "Consider running with sudo for complete testing"
        echo ""
    fi
    
    # Run all tests
    test_service_status
    test_network_connectivity
    test_unbound_direct
    test_proxy_resolution
    test_cdn_domains
    test_log_generation
    test_dashboard
    test_pihole_integration
    test_performance_comparison
    
    # Optional fallback test (requires stopping Unbound)
    echo ""
    while true; do
        read -p "Run fallback mechanism test? (requires stopping Unbound temporarily) (y/N): " yn
        case $yn in
            [Yy]* ) test_fallback_mechanism; break;;
            [Nn]* | "" ) print_info "Skipping fallback mechanism test"; break;;
            * ) echo "Please answer yes or no.";;
        esac
    done
    
    # Generate report
    generate_report
    
    echo ""
    print_header
    print_success "Testing completed! 🎉"
    echo ""
    print_info "Summary:"
    echo "• All major components tested"
    echo "• Performance metrics collected"
    echo "• Integration verified"
    echo "• Test report generated"
    echo ""
    print_info "Next steps:"
    echo "• Review the test report for any issues"
    echo "• Check the dashboard at $DASHBOARD_URL"
    echo "• Monitor logs at /var/log/dns-fallback.log"
    echo ""
    
    # Check for critical issues
    local critical_issues=()
    
    if ! systemctl is-active --quiet dns-fallback.service; then
        critical_issues+=("DNS Fallback Proxy service not running")
    fi
    
    if ! ss -tuln | grep -q ":$PROXY_PORT "; then
        critical_issues+=("DNS Proxy not listening on port $PROXY_PORT")
    fi
    
    if ! test_dns_resolution "$PROXY_IP" "$PROXY_PORT" "google.com" 5; then
        critical_issues+=("DNS resolution through proxy failing")
    fi
    
    if [ ${#critical_issues[@]} -gt 0 ]; then
        print_warning "Critical issues found:"
        for issue in "${critical_issues[@]}"; do
            echo "  - $issue"
        done
        echo ""
        print_info "Please resolve these issues before using the DNS Fallback system"
    else
        print_success "No critical issues found - system appears to be working correctly!"
    fi
}

# Cleanup function
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        print_error "Testing encountered errors!"
        print_info "Check the output above for details"
    fi
    exit $exit_code
}

# Set trap for cleanup
trap cleanup EXIT

# Run main function
main "$@"
