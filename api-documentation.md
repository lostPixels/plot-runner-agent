# NextDraw Plotter API Documentation

This document provides comprehensive details about the REST API endpoints available in the NextDraw Plotter API Server. Use this information to build a UI that interacts with the plotter system.

## Base URL

By default, the API server runs on:
```http
http://<server-ip>:5000
```

## Authentication

The API currently doesn't implement authentication. If you're implementing a UI that connects to this API, you should consider network-level security measures.

## Status Codes

- `200 OK`: Request succeeded
- `201 Created`: Resource successfully created
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `413 Payload Too Large`: Request entity too large
- `500 Internal Server Error`: Server error

## Endpoints

### Health Check

#### `GET /health`

Check if the API server is running.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2023-08-01T12:00:00.000000",
  "version": "1.0.0"
}
```

### System Status

#### `GET /status`

Get the current status of the plotter system.

**Response:**
```json
{
  "plotter": {
    "status": "IDLE",
    "connected": true,
    "port": "/dev/ttyUSB0",
    "model": "AxiDraw V3"
  },
  "queue": {
    "count": 2,
    "active": false,
    "pending_jobs": ["job1", "job2"]
  },
  "app": {
    "status": "IDLE",
    "current_job": null,
    "error_message": null,
    "last_updated": "2023-08-01T12:00:00.000000",
    "uptime_start": "2023-08-01T10:00:00.000000"
  },
  "config": {
    // Current configuration (see Configuration section)
  }
}
```

### Plot Submission

#### `POST /plot`

Submit a new plot job. Accepts both JSON and multipart/form-data formats.

**JSON Request Body:**
```json
{
  "svg_content": "<svg>...</svg>",  // SVG content as string (alternative to svg_file)
  "svg_file": "/path/to/file.svg",  // Path to SVG file (alternative to svg_content)
  "config": {                       // Optional config overrides for this job
    "speed_pendown": 20,
    "speed_penup": 75
  },
  "priority": 1,                    // Optional priority (lower number = higher priority)
  "name": "My Plot Job",            // Optional job name
  "description": "Test plot",       // Optional description
  "start_mm": 10.5                  // Optional starting position in mm
}
```

**Multipart Form Data:**
- `svg_file`: SVG file to upload
- `config`: JSON string of configuration overrides
- `priority`: Job priority (integer)
- `name`: Job name
- `description`: Job description
- `start_mm`: Starting position in mm

**Response (201 Created):**
```json
{
  "job_id": "job_1234567890",
  "status": "queued",
  "position": 1
}
```

#### `POST /plot/upload`

Dedicated endpoint for large file uploads. Uses the same parameters as the multipart form data in `/plot`.

**Response (201 Created):**
```json
{
  "job_id": "job_1234567890",
  "status": "queued",
  "position": 1,
  "file_size": 1024000,
  "uploaded_filename": "1628450000_myfile.svg"
}
```

#### `POST /plot/chunk`

Handle chunked uploads for very large files.

**Multipart Form Data:**
- `chunk_data`: The chunk file data
- `chunk`: Chunk number (integer, 0-based)
- `total_chunks`: Total number of chunks (integer)
- `file_id`: Unique identifier for the file being uploaded
- `filename`: Original filename
- `config`: JSON string of configuration overrides (on last chunk)
- `priority`: Job priority (integer, on last chunk)
- `name`: Job name (on last chunk)
- `description`: Job description (on last chunk)

**Response for in-progress upload (200 OK):**
```json
{
  "status": "chunk_received",
  "chunk": 1,
  "total_chunks": 5,
  "uploaded_chunks": 2
}
```

**Response for completed upload (201 Created):**
```json
{
  "job_id": "job_1234567890",
  "status": "queued",
  "position": 1,
  "file_size": 1024000,
  "message": "File assembled and job created"
}
```

### Job Management

#### `GET /jobs`

Get a list of all jobs.

**Response:**
```json
[
  {
    "id": "job_1234567890",
    "name": "My Plot Job",
    "description": "Test plot",
    "status": "queued",
    "submitted_at": "2023-08-01T12:00:00.000000",
    "priority": 1,
    "position": 1
  },
  {
    "id": "job_0987654321",
    "name": "Another Job",
    "description": "Another test",
    "status": "completed",
    "submitted_at": "2023-08-01T11:00:00.000000",
    "completed_at": "2023-08-01T11:30:00.000000",
    "priority": 2
  }
]
```

#### `GET /jobs/<job_id>`

Get details for a specific job.

**Response:**
```json
{
  "id": "job_1234567890",
  "name": "My Plot Job",
  "description": "Test plot",
  "status": "in_progress",
  "submitted_at": "2023-08-01T12:00:00.000000",
  "started_at": "2023-08-01T12:05:00.000000",
  "progress": 75,
  "priority": 1,
  "config_overrides": {
    "speed_pendown": 20
  },
  "file_size": 102400,
  "original_filename": "myplot.svg"
}
```

#### `DELETE /jobs/<job_id>`

Cancel a job.

**Response:**
```json
{
  "message": "Job cancelled"
}
```

### Plotter Control

#### `POST /pause`

Pause the current plotting job.

**Response:**
```json
{
  "message": "Plotting paused"
}
```

#### `POST /resume`

Resume a paused plotting job.

**Response:**
```json
{
  "message": "Plotting resumed"
}
```

#### `POST /stop`

Stop the current plotting job.

**Response:**
```json
{
  "message": "Plotting stopped"
}
```

### Configuration

#### `GET /config`

Get the current configuration.

**Response:**
```json
{
  "plotter_info": {
    "model": 8,
    "nickname": "RaspberryPi-Plotter-001",
    "firmware_version": "",
    "software_version": "",
    "port": null,
    "port_config": 0,
    "last_updated": "2024-01-01T00:00:00"
  },
  "plotter_settings": {
    "speed_pendown": 25,
    "speed_penup": 75,
    "accel": 75,
    "pen_pos_down": 40,
    "pen_pos_up": 60,
    "pen_rate_lower": 50,
    "pen_rate_raise": 50,
    "handling": 1,
    "homing": true,
    "model": 8,
    "penlift": 1,
    "auto_rotate": true,
    "reordering": 0,
    "random_start": false,
    "hiding": false,
    "report_time": true
  },
  "api_settings": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false,
    "cors_enabled": true,
    "max_job_queue": 100,
    "job_timeout": 3600,
    "log_level": "INFO"
  },
  "file_settings": {
    "upload_directory": "uploads",
    "output_directory": "output",
    "max_file_size": 10485760,
    "allowed_extensions": [".svg"],
    "auto_cleanup": true,
    "cleanup_age_days": 7
  },
  "safety_settings": {
    "max_plot_time": 7200,
    "emergency_stop_enabled": true,
    "pen_height_limits": {
      "min": 0,
      "max": 100
    },
    "speed_limits": {
      "min_pendown": 1,
      "max_pendown": 100,
      "min_penup": 1,
      "max_penup": 100
    }
  },
  "notification_settings": {
    "webhook_enabled": false,
    "webhook_url": "",
    "email_enabled": false,
    "email_settings": {
      "smtp_server": "",
      "smtp_port": 587,
      "username": "",
      "password": "",
      "recipient": ""
    }
  },
  "version": "1.0.0",
  "last_updated": "2024-01-01T00:00:00"
}
```

#### `PUT /config`

Update the configuration.

**Request Body:**
```json
{
  "plotter_settings": {
    "speed_pendown": 30,
    "speed_penup": 80
  },
  "api_settings": {
    "port": 5001
  }
}
```

**Response:**
```json
{
  "message": "Configuration updated"
}
```

#### `POST /config/reset`

Reset configuration to defaults.

**Response:**
```json
{
  "message": "Configuration reset to defaults"
}
```

### Utility Commands

#### `POST /utility/<command>`

Execute utility commands. Available commands depend on the plotter implementation.

**Request Body:**
```json
{
  "param1": "value1",
  "param2": "value2"
}
```

**Response:**
```json
{
  "result": "Command output or success message"
}
```

### System Management

#### `POST /update`

Trigger a remote update of the plotter software.

**Request Body:**
```json
{
  "branch": "main",
  "force": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Update completed successfully",
  "details": {
    "previous_version": "1.0.0",
    "new_version": "1.1.0",
    "updated_files": 5
  }
}
```

#### `GET /logs`

Get recent log entries.

**Query Parameters:**
- `lines` (optional): Number of log lines to retrieve (default: 100)

**Response:**
```json
{
  "logs": [
    "2023-08-01 12:00:00 INFO: Server started",
    "2023-08-01 12:05:00 INFO: Job job_1234567890 started",
    "2023-08-01 12:30:00 INFO: Job job_1234567890 completed"
  ]
}
```

## Configuration Options

### Plotter Settings

| Parameter | Type | Description |
|-----------|------|-------------|
| speed_pendown | Integer | Movement speed when pen is down (1-100) |
| speed_penup | Integer | Movement speed when pen is up (1-100) |
| accel | Integer | Acceleration rate (1-100) |
| pen_pos_down | Integer | Pen down position (0-100) |
| pen_pos_up | Integer | Pen up position (0-100) |
| pen_rate_lower | Integer | Pen lowering rate (1-100) |
| pen_rate_raise | Integer | Pen raising rate (1-100) |
| handling | Integer | Reserved parameter |
| homing | Boolean | Whether to home the axes before plotting |
| model | Integer | Plotter model identifier |
| penlift | Integer | Pen lift mode |
| auto_rotate | Boolean | Auto-rotate SVG to fit paper |
| reordering | Integer | Path reordering mode (0-4) |
| random_start | Boolean | Start from random point in plot |
| hiding | Boolean | Hide lines not being plotted |
| report_time | Boolean | Report estimated time |

### API Settings

| Parameter | Type | Description |
|-----------|------|-------------|
| host | String | Host address to bind to |
| port | Integer | Port to listen on |
| debug | Boolean | Enable debug mode |
| cors_enabled | Boolean | Enable CORS for web UIs |
| max_job_queue | Integer | Maximum size of job queue |
| job_timeout | Integer | Job timeout in seconds |
| log_level | String | Logging level (DEBUG, INFO, WARNING, ERROR) |

### File Settings

| Parameter | Type | Description |
|-----------|------|-------------|
| upload_directory | String | Directory for uploaded files |
| output_directory | String | Directory for output files |
| max_file_size | Integer | Maximum file size in bytes |
| allowed_extensions | Array | Allowed file extensions |
| auto_cleanup | Boolean | Automatically clean up old files |
| cleanup_age_days | Integer | Age in days before cleanup |

### Safety Settings

| Parameter | Type | Description |
|-----------|------|-------------|
| max_plot_time | Integer | Maximum plot time in seconds |
| emergency_stop_enabled | Boolean | Enable emergency stop |
| pen_height_limits | Object | Min/max pen height limits |
| speed_limits | Object | Min/max speed limits |

### Notification Settings

| Parameter | Type | Description |
|-----------|------|-------------|
| webhook_enabled | Boolean | Enable webhook notifications |
| webhook_url | String | URL for webhook notifications |
| email_enabled | Boolean | Enable email notifications |
| email_settings | Object | Email server settings |

## Error Handling

All endpoints may return error responses in the following format:

```json
{
  "error": "Error message describing what went wrong"
}
```

## Building a UI

When building a UI to interact with this API, consider the following:

1. **Real-time updates**: Poll the `/status` endpoint to get real-time updates on plotter and job status.
2. **File uploads**: For large files, use the chunked upload endpoint to provide progress feedback.
3. **Job management**: Allow users to view, cancel, and manage jobs through the jobs endpoints.
4. **Configuration**: Provide interfaces for configuring plotter settings.
5. **Error handling**: Properly handle and display API errors to users.
6. **Logging**: Use the logs endpoint to provide debugging information.

## Example UI Workflow

1. Check server health via `/health`
2. Display current status via `/status`
3. Allow configuration via `/config`
4. Provide job submission via `/plot` or `/plot/chunk`
5. Show job queue and status via `/jobs`
6. Offer controls via `/pause`, `/resume`, and `/stop`
7. Display logs via `/logs`
