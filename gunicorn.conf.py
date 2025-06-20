import os
import multiprocessing

# Server socket
bind = "127.0.0.1:5000"
backlog = 2048

# Worker processes
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 600  # Increased for large file uploads
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 500  # Lower due to large file processing
max_requests_jitter = 50

# Logging
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "nextdraw-api"

# Server mechanics
daemon = False
pidfile = "logs/gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None

# Application
wsgi_module = "wsgi:application"
pythonpath = "."

# Worker timeout for long-running plots and large uploads
graceful_timeout = 120
worker_tmp_dir = "/dev/shm"

# Security - increased limits for large SVG files
limit_request_line = 8192
limit_request_fields = 200
limit_request_field_size = 16384

# Large file handling
max_request_size = 1073741824  # 1GB
worker_memory_limit = 1073741824  # 1GB per worker

# Preload application for better memory usage
preload_app = True

# Enable threading for Flask
threads = 2