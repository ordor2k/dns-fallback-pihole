#!/usr/bin/env python3

import os
import sys
from pathlib import Path
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from flask import Flask, render_template_string, jsonify, request, send_file
import threading
import time
import csv
import io

# Configuration
LOG_FILE = "/var/log/dns-fallback.log"
DASHBOARD_PORT = 8053
DASHBOARD_HOST = "0.0.0.0"

app = Flask(__name__)

class EnhancedLogAnalyzer:
    def __init__(self, log_file_path):
        self.log_file_path = log_file_path
        self.cache = {}
        self.cache_time = None
        self.cache_duration = 30  # seconds
        self.lock = threading.Lock()

    def _parse_structured_log(self, line):
        """Parse structured JSON log entries"""
        try:
            data = json.loads(line.strip())
            if 'domain' in data:  # DNS query log
                return {
                    'timestamp': datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00')),
                    'domain': data['domain'],
                    'client': data.get('client', 'unknown'),
                    'resolver': data.get('resolver', 'unknown'),
                    'response_time': float(data.get('response_time', 0)),
                    'query_type': data.get('query_type', 'A'),
                    'success': data.get('success', True)
                }
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return None

    def _parse_legacy_log(self, line):
        """Parse legacy text-based log entries"""
        # Enhanced regex patterns for different log types
        patterns = [
            # DNS_QUERY structured logs in text format
            (r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*DNS_QUERY.*domain: (\S+).*client: (\S+).*resolver: (\S+).*response_time: ([\d.]+).*query_type: (\S+).*success: (\w+)', 'dns_query'),
            # Fallback/failure events
            (r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*Switching to fallback server: (\S+)', 'fallback_switch'),
            (r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*Primary DNS.*is healthy again', 'primary_restored'),
            (r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*Domain (\S+) bypassed.*repeated Unbound failures', 'domain_bypassed'),
            # Health check failures
            (r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*DNS server (\S+) failed health check', 'health_failure'),
        ]

        for pattern, log_type in patterns:
            match = re.search(pattern, line)
            if match:
                if log_type == 'dns_query':
                    return {
                        'timestamp': datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S,%f'),
                        'domain': match.group(2),
                        'client': match.group(3),
                        'resolver': match.group(4),
                        'response_time': float(match.group(5)),
                        'query_type': match.group(6),
                        'success': match.group(7).lower() == 'true'
                    }
                elif log_type in ['fallback_switch', 'primary_restored', 'domain_bypassed', 'health_failure']:
                    return {
                        'timestamp': datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S,%f'),
                        'event_type': log_type,
                        'details': match.group(2) if len(match.groups()) > 1 else None
                    }
        return None

    def get_analytics(self, hours=24):
        """Get comprehensive analytics from logs"""
        with self.lock:
            # Check cache validity
            now = datetime.now()
            if (self.cache_time and 
                (now - self.cache_time).seconds < self.cache_duration and
                'analytics' in self.cache):
                return self.cache['analytics']

            # Parse log file
            cutoff_time = now - timedelta(hours=hours)
            dns_queries = []
            events = []

            try:
                with open(self.log_file_path, 'r') as f:
                    for line in f:
                        # Try structured parsing first
                        parsed = self._parse_structured_log(line)
                        if not parsed:
                            parsed = self._parse_legacy_log(line)
                        
                        if parsed and parsed.get('timestamp', now) > cutoff_time:
                            if 'domain' in parsed:
                                dns_queries.append(parsed)
                            else:
                                events.append(parsed)

            except FileNotFoundError:
                return self._empty_analytics()

            # Generate analytics
            analytics = self._generate_analytics(dns_queries, events, hours)
            
            # Cache results
            self.cache['analytics'] = analytics
            self.cache_time = now
            
            return analytics

    def _empty_analytics(self):
        """Return empty analytics structure"""
        return {
            'summary': {
                'total_queries': 0,
                'unbound_queries': 0,
                'fallback_queries': 0,
                'bypassed_queries': 0,
                'failed_queries': 0,
                'unbound_success_rate': 0,
                'fallback_usage_rate': 0,
                'bypass_rate': 0,
                'average_response_time': 0,
                'unbound_avg_response': 0,
                'fallback_avg_response': 0
            },
            'hourly_stats': [],
            'top_domains': [],
            'top_failing_domains': [],
            'top_clients': [],
            'resolver_distribution': {},
            'query_types': {},
            'recent_events': [],
            'cdn_analysis': {
                'total_cdn_queries': 0,
                'cdn_unbound_success': 0,
                'cdn_bypass_rate': 0
            },
            'performance_metrics': {
                'p50_response_time': 0,
                'p95_response_time': 0,
                'p99_response_time': 0
            }
        }

    def _generate_analytics(self, dns_queries, events, hours):
        """Generate comprehensive analytics from parsed data"""
        if not dns_queries:
            return self._empty_analytics()

        # Basic counts
        total_queries = len(dns_queries)
        unbound_queries = [q for q in dns_queries if q['resolver'] == 'unbound']
        fallback_queries = [q for q in dns_queries if q['resolver'] == 'fallback']
        bypassed_queries = [q for q in dns_queries if q['resolver'] == 'bypassed']
        failed_queries = [q for q in dns_queries if not q['success']]

        # CDN analysis
        cdn_patterns = ['cloudfront.net', 'fastly.com', 'amazonaws.com', 'akamai.net', 'cloudflare.com']
        cdn_queries = [q for q in dns_queries if any(pattern in q['domain'].lower() for pattern in cdn_patterns)]
        cdn_unbound_success = [q for q in cdn_queries if q['resolver'] == 'unbound' and q['success']]

        # Performance metrics
        response_times = [q['response_time'] for q in dns_queries if q['response_time'] > 0]
        response_times.sort()
        
        def percentile(data, p):
            if not data:
                return 0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = k - f
            if f + 1 < len(data):
                return data[f] * (1 - c) + data[f + 1] * c
            return data[f]

        # Hourly statistics
        hourly_stats = []
        now = datetime.now()
        for i in range(hours):
            hour_start = now - timedelta(hours=i+1)
            hour_end = now - timedelta(hours=i)
            hour_queries = [q for q in dns_queries if hour_start <= q['timestamp'] < hour_end]
            
            hourly_stats.append({
                'hour': hour_start.strftime('%H:00'),
                'total': len(hour_queries),
                'unbound': len([q for q in hour_queries if q['resolver'] == 'unbound']),
                'fallback': len([q for q in hour_queries if q['resolver'] == 'fallback']),
                'bypassed': len([q for q in hour_queries if q['resolver'] == 'bypassed']),
                'failed': len([q for q in hour_queries if not q['success']])
            })

        # Domain analysis
        domain_stats = defaultdict(lambda: {'total': 0, 'unbound_success': 0, 'fallback': 0, 'bypassed': 0, 'failed': 0})
        client_stats = defaultdict(int)
        query_type_stats = defaultdict(int)
        resolver_stats = defaultdict(int)

        for query in dns_queries:
            domain = query['domain']
            domain_stats[domain]['total'] += 1
            
            if query['resolver'] == 'unbound' and query['success']:
                domain_stats[domain]['unbound_success'] += 1
            elif query['resolver'] == 'fallback':
                domain_stats[domain]['fallback'] += 1
            elif query['resolver'] == 'bypassed':
                domain_stats[domain]['bypassed'] += 1
            
            if not query['success']:
                domain_stats[domain]['failed'] += 1
            
            client_stats[query['client']] += 1
            query_type_stats[query['query_type']] += 1
            resolver_stats[query['resolver']] += 1

        # Top domains and failing domains
        top_domains = sorted(domain_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:20]
        top_failing_domains = sorted(
            [(d, s) for d, s in domain_stats.items() if s['failed'] > 0 or s['fallback'] > s['unbound_success']], 
            key=lambda x: x[1]['failed'] + x[1]['fallback'], 
            reverse=True
        )[:15]

        # Top clients
        top_clients = sorted(client_stats.items(), key=lambda x: x[1], reverse=True)[:10]

        # Recent events
        recent_events = sorted(events, key=lambda x: x['timestamp'], reverse=True)[:20]

        return {
            'summary': {
                'total_queries': total_queries,
                'unbound_queries': len(unbound_queries),
                'fallback_queries': len(fallback_queries),
                'bypassed_queries': len(bypassed_queries),
                'failed_queries': len(failed_queries),
                'unbound_success_rate': (len([q for q in unbound_queries if q['success']]) / max(1, len(unbound_queries))) * 100,
                'fallback_usage_rate': (len(fallback_queries) / max(1, total_queries)) * 100,
                'bypass_rate': (len(bypassed_queries) / max(1, total_queries)) * 100,
                'average_response_time': sum(q['response_time'] for q in dns_queries) / max(1, total_queries),
                'unbound_avg_response': sum(q['response_time'] for q in unbound_queries) / max(1, len(unbound_queries)),
                'fallback_avg_response': sum(q['response_time'] for q in fallback_queries) / max(1, len(fallback_queries))
            },
            'hourly_stats': list(reversed(hourly_stats)),
            'top_domains': [(domain, stats['total']) for domain, stats in top_domains],
            'top_failing_domains': [(domain, {'failed': stats['failed'], 'fallback': stats['fallback'], 'total': stats['total']}) for domain, stats in top_failing_domains],
            'top_clients': top_clients,
            'resolver_distribution': dict(resolver_stats),
            'query_types': dict(query_type_stats),
            'recent_events': [{'timestamp': e['timestamp'].strftime('%Y-%m-%d %H:%M:%S'), 'type': e.get('event_type', 'unknown'), 'details': e.get('details', '')} for e in recent_events],
            'cdn_analysis': {
                'total_cdn_queries': len(cdn_queries),
                'cdn_unbound_success': len(cdn_unbound_success),
                'cdn_bypass_rate': (len([q for q in cdn_queries if q['resolver'] == 'bypassed']) / max(1, len(cdn_queries))) * 100
            },
            'performance_metrics': {
                'p50_response_time': percentile(response_times, 50),
                'p95_response_time': percentile(response_times, 95),
                'p99_response_time': percentile(response_times, 99)
            }
        }

    def export_csv(self, hours=24):
        """Export analytics data as CSV"""
        analytics = self.get_analytics(hours)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write summary
        writer.writerow(['=== SUMMARY ==='])
        for key, value in analytics['summary'].items():
            writer.writerow([key.replace('_', ' ').title(), f"{value:.2f}" if isinstance(value, float) else value])
        
        writer.writerow([])
        writer.writerow(['=== TOP DOMAINS ==='])
        writer.writerow(['Domain', 'Query Count'])
        for domain, count in analytics['top_domains']:
            writer.writerow([domain, count])
            
        writer.writerow([])
        writer.writerow(['=== TOP FAILING DOMAINS ==='])
        writer.writerow(['Domain', 'Failed Queries', 'Fallback Queries', 'Total Queries'])
        for domain, stats in analytics['top_failing_domains']:
            writer.writerow([domain, stats['failed'], stats['fallback'], stats['total']])
            
        writer.writerow([])
        writer.writerow(['=== HOURLY STATISTICS ==='])
        writer.writerow(['Hour', 'Total', 'Unbound', 'Fallback', 'Bypassed', 'Failed'])
        for hour_stat in analytics['hourly_stats']:
            writer.writerow([hour_stat['hour'], hour_stat['total'], hour_stat['unbound'], 
                           hour_stat['fallback'], hour_stat['bypassed'], hour_stat['failed']])
        
        output.seek(0)
        return output.getvalue()

# Initialize log analyzer
log_analyzer = EnhancedLogAnalyzer(LOG_FILE)

# Enhanced HTML template with seamless updates
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced DNS Fallback Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        
        .control-group {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255,255,255,0.1);
            padding: 10px 15px;
            border-radius: 25px;
            backdrop-filter: blur(10px);
        }
        
        .control-group label {
            color: white;
            font-weight: 500;
        }
        
        select, button {
            padding: 8px 15px;
            border: none;
            border-radius: 20px;
            background: white;
            color: #333;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        button:hover {
            background: #f0f0f0;
            transform: translateY(-2px);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            transition: transform 0.3s ease, opacity 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .stat-card.updating::after {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
            animation: shimmer 1s ease-in-out;
        }
        
        @keyframes shimmer {
            0% { left: -100%; }
            100% { left: 100%; }
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: bold;
            margin-bottom: 10px;
            transition: all 0.5s ease;
        }
        
        .stat-label {
            font-size: 0.9rem;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .success { color: #10b981; }
        .warning { color: #f59e0b; }
        .danger { color: #ef4444; }
        .info { color: #3b82f6; }
        
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }
        
        .chart-container {
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            transition: opacity 0.3s ease;
        }
        
        .chart-container.updating {
            opacity: 0.7;
        }
        
        .chart-title {
            font-size: 1.3rem;
            font-weight: bold;
            margin-bottom: 20px;
            text-align: center;
            color: #333;
        }
        
        .tables-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 25px;
        }
        
        .table-container {
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            transition: opacity 0.3s ease;
        }
        
        .table-container.updating {
            opacity: 0.7;
        }
        
        .table-title {
            font-size: 1.3rem;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }
        
        th, td {
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }
        
        th {
            background: #f9fafb;
            font-weight: 600;
            color: #374151;
        }
        
        tbody tr {
            transition: background-color 0.2s ease;
        }
        
        tbody tr:hover {
            background: #f3f4f6;
        }
        
        tbody tr.new-row {
            animation: fadeIn 0.5s ease;
        }
        
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: white;
            font-size: 1.2rem;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .status-healthy { background: #10b981; }
        .status-warning { background: #f59e0b; }
        .status-error { background: #ef4444; }
        
        .update-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(255,255,255,0.95);
            padding: 10px 20px;
            border-radius: 25px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            display: none;
            align-items: center;
            gap: 10px;
            z-index: 1000;
        }
        
        .update-indicator.show {
            display: flex;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        .spinner {
            width: 20px;
            height: 20px;
            border: 3px solid #f3f4f6;
            border-top: 3px solid #3b82f6;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .header h1 { font-size: 2rem; }
            .stats-grid { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
            .charts-grid { grid-template-columns: 1fr; }
            .tables-grid { grid-template-columns: 1fr; }
            .update-indicator { top: 10px; right: 10px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ Enhanced DNS Fallback Dashboard</h1>
            <p>Unbound + Pi-hole DNS Resolution Analytics</p>
        </div>
        
        <div class="controls">
            <div class="control-group">
                <label for="timeRange">Time Range:</label>
                <select id="timeRange">
                    <option value="1">Last Hour</option>
                    <option value="6">Last 6 Hours</option>
                    <option value="24" selected>Last 24 Hours</option>
                    <option value="168">Last Week</option>
                </select>
            </div>
            <div class="control-group">
                <button onclick="refreshData(true)">🔄 Refresh</button>
                <button onclick="exportCSV()">📊 Export CSV</button>
            </div>
        </div>
        
        <div id="loading" class="loading">Loading analytics...</div>
        <div id="dashboard" style="display: none;">
            <!-- Summary Statistics -->
            <div class="stats-grid" id="statsGrid"></div>
            
            <!-- Charts -->
            <div class="charts-grid">
                <div class="chart-container" id="hourlyChartContainer">
                    <div class="chart-title">Query Distribution Over Time</div>
                    <canvas id="hourlyChart"></canvas>
                </div>
                <div class="chart-container" id="resolverChartContainer">
                    <div class="chart-title">Resolver Usage</div>
                    <canvas id="resolverChart"></canvas>
                </div>
                <div class="chart-container" id="performanceChartContainer">
                    <div class="chart-title">Response Time Distribution</div>
                    <canvas id="performanceChart"></canvas>
                </div>
                <div class="chart-container" id="queryTypeChartContainer">
                    <div class="chart-title">Query Types</div>
                    <canvas id="queryTypeChart"></canvas>
                </div>
            </div>
            
            <!-- Data Tables -->
            <div class="tables-grid">
                <div class="table-container" id="topDomainsContainer">
                    <div class="table-title">🔥 Top Domains</div>
                    <table id="topDomainsTable"></table>
                </div>
                <div class="table-container" id="failingDomainsContainer">
                    <div class="table-title">⚠️ Problematic Domains</div>
                    <table id="failingDomainsTable"></table>
                </div>
                <div class="table-container" id="topClientsContainer">
                    <div class="table-title">👥 Top Clients</div>
                    <table id="topClientsTable"></table>
                </div>
                <div class="table-container" id="recentEventsContainer">
                    <div class="table-title">📋 Recent Events</div>
                    <table id="recentEventsTable"></table>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Update indicator -->
    <div class="update-indicator" id="updateIndicator">
        <div class="spinner"></div>
        <span>Updating dashboard...</span>
    </div>

    <script>
        let currentData = null;
        let previousData = null;
        let charts = {};
        let isUpdating = false;
        let autoRefreshInterval = null;
        
        // Initialize dashboard
        document.addEventListener('DOMContentLoaded', function() {
            refreshData(true);
            
            // Auto-refresh every 30 seconds
            autoRefreshInterval = setInterval(() => refreshData(false), 30000);
            
            // Time range change handler
            document.getElementById('timeRange').addEventListener('change', () => refreshData(true));
        });
        
        async function refreshData(showLoading = false) {
            if (isUpdating) return;
            isUpdating = true;
            
            const timeRange = document.getElementById('timeRange').value;
            
            if (showLoading) {
                document.getElementById('loading').style.display = 'block';
                document.getElementById('dashboard').style.display = 'none';
            } else {
                // Show update indicator
                document.getElementById('updateIndicator').classList.add('show');
            }
            
            try {
                const response = await fetch(`/api/analytics?hours=${timeRange}`);
                const newData = await response.json();
                
                previousData = currentData;
                currentData = newData;
                
                if (showLoading || !previousData) {
                    // Initial load or time range change
                    updateDashboard(true);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('dashboard').style.display = 'block';
                } else {
                    // Seamless update
                    updateDashboard(false);
                }
            } catch (error) {
                console.error('Error fetching data:', error);
                if (showLoading) {
                    document.getElementById('loading').innerHTML = '❌ Error loading data';
                }
            } finally {
                isUpdating = false;
                // Hide update indicator
                setTimeout(() => {
                    document.getElementById('updateIndicator').classList.remove('show');
                }, 500);
            }
        }
        
        function updateDashboard(fullUpdate = true) {
            updateSummaryStats(fullUpdate);
            updateCharts(fullUpdate);
            updateTables(fullUpdate);
        }
        
        function animateValue(element, start, end, duration) {
            const range = end - start;
            const startTime = performance.now();
            
            function update(currentTime) {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const current = start + (range * progress);
                
                if (element.dataset.isPercentage === 'true') {
                    element.textContent = current.toFixed(1) + '%';
                } else if (element.dataset.isTime === 'true') {
                    element.textContent = current.toFixed(0) + 'ms';
                } else {
                    element.textContent = Math.round(current).toLocaleString();
                }
                
                if (progress < 1) {
                    requestAnimationFrame(update);
                }
            }
            
            requestAnimationFrame(update);
        }
        
        function updateSummaryStats(fullUpdate = true) {
            const stats = currentData.summary;
            const statsGrid = document.getElementById('statsGrid');
            
            const statsConfig = [
                { value: stats.total_queries, label: 'Total Queries', class: 'success' },
                { value: stats.unbound_success_rate, label: 'Unbound Success Rate', class: 'info', isPercentage: true },
                { value: stats.fallback_usage_rate, label: 'Fallback Usage', class: 'warning', isPercentage: true },
                { value: stats.bypass_rate, label: 'Bypass Rate', class: 'danger', isPercentage: true },
                { value: stats.average_response_time * 1000, label: 'Avg Response Time', class: 'info', isTime: true },
                { value: stats.unbound_avg_response * 1000, label: 'Unbound Avg', class: 'success', isTime: true },
                { value: stats.fallback_avg_response * 1000, label: 'Fallback Avg', class: 'warning', isTime: true }
            ];
            
            if (fullUpdate) {
                statsGrid.innerHTML = statsConfig.map((stat, index) => `
                    <div class="stat-card" id="stat-${index}">
                        <div class="stat-value ${stat.class}" 
                             data-value="${stat.value}"
                             data-is-percentage="${stat.isPercentage || false}"
                             data-is-time="${stat.isTime || false}">
                            ${stat.isPercentage ? stat.value.toFixed(1) + '%' : 
                              stat.isTime ? stat.value.toFixed(0) + 'ms' :
                              stat.value.toLocaleString()}
                        </div>
                        <div class="stat-label">${stat.label}</div>
                    </div>
                `).join('');
            } else {
                // Animate value changes
                statsConfig.forEach((stat, index) => {
                    const card = document.getElementById(`stat-${index}`);
                    const valueElement = card.querySelector('.stat-value');
                    const oldValue = parseFloat(valueElement.dataset.value) || 0;
                    
                    if (Math.abs(oldValue - stat.value) > 0.01) {
                        card.classList.add('updating');
                        animateValue(valueElement, oldValue, stat.value, 500);
                        valueElement.dataset.value = stat.value;
                        
                        setTimeout(() => {
                            card.classList.remove('updating');
                        }, 600);
                    }
                });
            }
        }
        
        function updateCharts(fullUpdate = true) {
            if (fullUpdate) {
                // Destroy existing charts
                Object.values(charts).forEach(chart => chart.destroy());
                charts = {};
            }
            
            // Update or create hourly chart
            updateHourlyChart(fullUpdate);
            updateResolverChart(fullUpdate);
            updatePerformanceChart(fullUpdate);
            updateQueryTypeChart(fullUpdate);
        }
        
        function updateHourlyChart(fullUpdate) {
            const container = document.getElementById('hourlyChartContainer');
            const ctx = document.getElementById('hourlyChart').getContext('2d');
            
            const chartData = {
                labels: currentData.hourly_stats.map(h => h.hour),
                datasets: [
                    {
                        label: 'Total Queries',
                        data: currentData.hourly_stats.map(h => h.total),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Unbound Success',
                        data: currentData.hourly_stats.map(h => h.unbound),
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Fallback Used',
                        data: currentData.hourly_stats.map(h => h.fallback),
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Bypassed',
                        data: currentData.hourly_stats.map(h => h.bypassed),
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        tension: 0.4
                    }
                ]
            };
            
            if (fullUpdate || !charts.hourly) {
                charts.hourly = new Chart(ctx, {
                    type: 'line',
                    data: chartData,
                    options: {
                        responsive: true,
                        animation: {
                            duration: fullUpdate ? 1000 : 0
                        },
                        plugins: {
                            legend: {
                                position: 'bottom'
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });
            } else {
                container.classList.add('updating');
                charts.hourly.data = chartData;
                charts.hourly.update('none');
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        function updateResolverChart(fullUpdate) {
            const container = document.getElementById('resolverChartContainer');
            const ctx = document.getElementById('resolverChart').getContext('2d');
            const resolverData = currentData.resolver_distribution;
            
            const chartData = {
                labels: Object.keys(resolverData),
                datasets: [{
                    data: Object.values(resolverData),
                    backgroundColor: [
                        '#10b981',
                        '#f59e0b',
                        '#ef4444',
                        '#3b82f6',
                        '#8b5cf6'
                    ]
                }]
            };
            
            if (fullUpdate || !charts.resolver) {
                charts.resolver = new Chart(ctx, {
                    type: 'doughnut',
                    data: chartData,
                    options: {
                        responsive: true,
                        animation: {
                            duration: fullUpdate ? 1000 : 0
                        },
                        plugins: {
                            legend: {
                                position: 'bottom'
                            }
                        }
                    }
                });
            } else {
                container.classList.add('updating');
                charts.resolver.data = chartData;
                charts.resolver.update('none');
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        function updatePerformanceChart(fullUpdate) {
            const container = document.getElementById('performanceChartContainer');
            const ctx = document.getElementById('performanceChart').getContext('2d');
            const perfMetrics = currentData.performance_metrics;
            
            const chartData = {
                labels: ['P50', 'P95', 'P99'],
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [
                        perfMetrics.p50_response_time * 1000,
                        perfMetrics.p95_response_time * 1000,
                        perfMetrics.p99_response_time * 1000
                    ],
                    backgroundColor: [
                        '#10b981',
                        '#f59e0b',
                        '#ef4444'
                    ]
                }]
            };
            
            if (fullUpdate || !charts.performance) {
                charts.performance = new Chart(ctx, {
                    type: 'bar',
                    data: chartData,
                    options: {
                        responsive: true,
                        animation: {
                            duration: fullUpdate ? 1000 : 0
                        },
                        plugins: {
                            legend: {
                                display: false
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Response Time (ms)'
                                }
                            }
                        }
                    }
                });
            } else {
                container.classList.add('updating');
                charts.performance.data = chartData;
                charts.performance.update('none');
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        function updateQueryTypeChart(fullUpdate) {
            const container = document.getElementById('queryTypeChartContainer');
            const ctx = document.getElementById('queryTypeChart').getContext('2d');
            const queryTypeData = currentData.query_types;
            
            const chartData = {
                labels: Object.keys(queryTypeData),
                datasets: [{
                    data: Object.values(queryTypeData),
                    backgroundColor: [
                        '#3b82f6',
                        '#10b981',
                        '#f59e0b',
                        '#ef4444',
                        '#8b5cf6',
                        '#06b6d4'
                    ]
                }]
            };
            
            if (fullUpdate || !charts.queryType) {
                charts.queryType = new Chart(ctx, {
                    type: 'pie',
                    data: chartData,
                    options: {
                        responsive: true,
                        animation: {
                            duration: fullUpdate ? 1000 : 0
                        },
                        plugins: {
                            legend: {
                                position: 'bottom'
                            }
                        }
                    }
                });
            } else {
                container.classList.add('updating');
                charts.queryType.data = chartData;
                charts.queryType.update('none');
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        function updateTables(fullUpdate = true) {
            updateTopDomainsTable(fullUpdate);
            updateFailingDomainsTable(fullUpdate);
            updateTopClientsTable(fullUpdate);
            updateRecentEventsTable(fullUpdate);
        }
        
        function updateTopDomainsTable(fullUpdate) {
            const container = document.getElementById('topDomainsContainer');
            const table = document.getElementById('topDomainsTable');
            
            if (!fullUpdate) container.classList.add('updating');
            
            table.innerHTML = `
                <thead>
                    <tr>
                        <th>Domain</th>
                        <th>Queries</th>
                        <th>Percentage</th>
                    </tr>
                </thead>
                <tbody>
                    ${currentData.top_domains.slice(0, 15).map(([domain, count]) => `
                        <tr>
                            <td>${domain}</td>
                            <td>${count.toLocaleString()}</td>
                            <td>${((count / currentData.summary.total_queries) * 100).toFixed(1)}%</td>
                        </tr>
                    `).join('')}
                </tbody>
            `;
            
            if (!fullUpdate) {
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        function updateFailingDomainsTable(fullUpdate) {
            const container = document.getElementById('failingDomainsContainer');
            const table = document.getElementById('failingDomainsTable');
            
            if (!fullUpdate) container.classList.add('updating');
            
            table.innerHTML = `
                <thead>
                    <tr>
                        <th>Domain</th>
                        <th>Failed</th>
                        <th>Fallback</th>
                        <th>Success Rate</th>
                    </tr>
                </thead>
                <tbody>
                    ${currentData.top_failing_domains.slice(0, 15).map(([domain, stats]) => {
                        const successRate = ((stats.total - stats.failed - stats.fallback) / stats.total * 100).toFixed(1);
                        return `
                            <tr>
                                <td>${domain}</td>
                                <td class="danger">${stats.failed}</td>
                                <td class="warning">${stats.fallback}</td>
                                <td class="${successRate > 50 ? 'success' : 'danger'}">${successRate}%</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            `;
            
            if (!fullUpdate) {
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        function updateTopClientsTable(fullUpdate) {
            const container = document.getElementById('topClientsContainer');
            const table = document.getElementById('topClientsTable');
            
            if (!fullUpdate) container.classList.add('updating');
            
            table.innerHTML = `
                <thead>
                    <tr>
                        <th>Client IP</th>
                        <th>Queries</th>
                        <th>Percentage</th>
                    </tr>
                </thead>
                <tbody>
                    ${currentData.top_clients.slice(0, 10).map(([client, count]) => `
                        <tr>
                            <td>${client}</td>
                            <td>${count.toLocaleString()}</td>
                            <td>${((count / currentData.summary.total_queries) * 100).toFixed(1)}%</td>
                        </tr>
                    `).join('')}
                </tbody>
            `;
            
            if (!fullUpdate) {
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        function updateRecentEventsTable(fullUpdate) {
            const container = document.getElementById('recentEventsContainer');
            const table = document.getElementById('recentEventsTable');
            
            if (!fullUpdate) container.classList.add('updating');
            
            // Check for new events
            const previousEvents = previousData ? previousData.recent_events : [];
            const newEventTimestamps = currentData.recent_events
                .filter(e => !previousEvents.some(pe => pe.timestamp === e.timestamp))
                .map(e => e.timestamp);
            
            table.innerHTML = `
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Event</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    ${currentData.recent_events.slice(0, 20).map(event => {
                        const eventClass = event.type.includes('fail') ? 'danger' : 
                                         event.type.includes('bypass') ? 'warning' : 'info';
                        const isNew = newEventTimestamps.includes(event.timestamp);
                        return `
                            <tr class="${isNew && !fullUpdate ? 'new-row' : ''}">
                                <td>${event.timestamp}</td>
                                <td><span class="status-indicator status-${eventClass === 'danger' ? 'error' : eventClass === 'warning' ? 'warning' : 'healthy'}"></span>${event.type}</td>
                                <td>${event.details || '-'}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            `;
            
            if (!fullUpdate) {
                setTimeout(() => container.classList.remove('updating'), 300);
            }
        }
        
        async function exportCSV() {
            const timeRange = document.getElementById('timeRange').value;
            try {
                const response = await fetch(`/api/export?hours=${timeRange}`);
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `dns-fallback-analytics-${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            } catch (error) {
                console.error('Error exporting CSV:', error);
                alert('Error exporting CSV data');
            }
        }
        
        // Clean up interval on page unload
        window.addEventListener('beforeunload', () => {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/analytics')
def api_analytics():
    hours = int(request.args.get('hours', 24))
    analytics = log_analyzer.get_analytics(hours)
    return jsonify(analytics)

@app.route('/api/export')
def api_export():
    hours = int(request.args.get('hours', 24))
    csv_data = log_analyzer.export_csv(hours)
    
    output = io.StringIO(csv_data)
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'dns-fallback-analytics-{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Quick log file check
        if os.path.exists(LOG_FILE):
            file_size = os.path.getsize(LOG_FILE)
            return jsonify({
                'status': 'healthy',
                'log_file_size': file_size,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': 'Log file not found',
                'timestamp': datetime.now().isoformat()
            }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    print(f"🚀 Enhanced DNS Fallback Dashboard starting on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    print(f"📊 Monitoring log file: {LOG_FILE}")
    print(f"🔍 Health check: http://{DASHBOARD_HOST}:{DASHBOARD_PORT}/health")
    
    app.run(
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        debug=False,
        threaded=True
    )
