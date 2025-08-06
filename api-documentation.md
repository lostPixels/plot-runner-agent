# NextDraw Plotter API Documentation (Simplified)

This document provides comprehensive details about the REST API endpoints available in the simplified NextDraw Plotter API Server. This version removes the concept of projects and works with a single current SVG file.

## Base URL

By default, the API server runs on:

```http
http://<server-ip>:5000
```

## Authentication

The API currently doesn't implement authentication. If you're implementing a UI that connects to this API, consider network-level security measures.

## Status Codes

- `200 OK`: Request succeeded
- `202 Accepted`: Request accepted for processing
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `409 Conflict`: Operation conflicts with current state
- `413 Payload Too Large`: Request entity too large (max 500MB)
- `500 Internal Server Error`: Server error

## Core Concepts

### Single SVG Workflow

The simplified API works with a single current SVG file at a time. When you upload a new SVG, it replaces any existing one. The SVG can contain multiple layers that can be plotted individually.

### Layer Support

SVG files can contain multiple layers (Inkscape layers or SVG groups). Each layer can be plotted individually by specifying its name in the plot endpoint.

## Endpoints

### Health Check

#### `GET /health`

Check if the API server is running.

**Response:**

```json
{
    "status": "healthy",
    "timestamp": "2023-08-01T12:00:00.000000",
    "version": "3.0.0",
    "uptime_start": "2023-08-01T10:00:00.000000"
}
```

### System Status

#### `GET /status`

Get the current status of the plotter system and current SVG.

**Response:**

```json
{
    "timestamp": "2023-08-01T12:00:00.000000",
    "system": {
        "plotter_status": "IDLE",
        "current_layer": null,
        "plot_progress": 0,
        "last_error": null
    },
    "svg": {
        "id": "svg_1234567890_abcd1234",
        "file_size": 1048576,
        "upload_progress": 100,
        "original_filename": "my_design.svg",
        "uploaded_at": "2023-08-01T11:30:00.000000",
        "available_layers": [
            {
                "id": "layer1",
                "name": "Cut Layer"
            },
            {
                "id": "layer2",
                "name": "Engrave Layer"
            }
        ],
        "is_ready": true
    }
}
```

**Plotter Status Values:**

- `IDLE`: Ready to accept commands
- `PLOTTING`: Currently plotting
- `PAUSED`: Plot is paused
- `ERROR`: Error state

### SVG Management

#### `POST /api/svg`

Upload a new SVG file. This replaces any existing SVG.

**Direct Upload (for files < 500MB):**

**Request:**

- Method: `POST`
- Content-Type: `multipart/form-data`
- Body:
    - `file`: The SVG file to upload

**Example (curl):**

```bash
curl -X POST -F "file=@my_design.svg" http://localhost:5000/api/svg
```

**Response:**

```json
{
    "message": "SVG uploaded successfully",
    "svg": {
        "id": "svg_1234567890_abcd1234",
        "file_size": 1048576,
        "upload_progress": 100,
        "original_filename": "my_design.svg",
        "uploaded_at": "2023-08-01T11:30:00.000000",
        "available_layers": [
            {
                "id": "layer1",
                "name": "Cut Layer"
            }
        ],
        "is_ready": true
    }
}
```

**Chunked Upload (for large files):**

For files larger than a few MB, use chunked upload to provide progress feedback.

**Request:**

- Method: `POST`
- Content-Type: `multipart/form-data`
- Form fields:
    - `chunk_number`: Current chunk index (0-based)
    - `total_chunks`: Total number of chunks
    - `file_id`: Unique identifier for this upload session
    - `filename`: Original filename
    - `chunk_data`: The chunk data file

**Example (JavaScript):**

```javascript
const chunkSize = 1024 * 1024; // 1MB chunks
const totalChunks = Math.ceil(file.size / chunkSize);

for (let i = 0; i < totalChunks; i++) {
    const chunk = file.slice(i * chunkSize, (i + 1) * chunkSize);
    const formData = new FormData();
    formData.append("chunk_number", i);
    formData.append("total_chunks", totalChunks);
    formData.append("file_id", "upload_" + Date.now());
    formData.append("filename", file.name);
    formData.append("chunk_data", chunk);

    await fetch("/api/svg", {
        method: "POST",
        body: formData,
    });
}
```

**Response (for each chunk):**

```json
{
    "progress": 50,
    "chunks_received": 5,
    "total_chunks": 10
}
```

#### `GET /api/svg`

Get the status of the currently loaded SVG.

**Response:**

```json
{
    "id": "svg_1234567890_abcd1234",
    "file_size": 1048576,
    "upload_progress": 100,
    "original_filename": "my_design.svg",
    "uploaded_at": "2023-08-01T11:30:00.000000",
    "available_layers": [
        {
            "id": "layer1",
            "name": "Cut Layer"
        },
        {
            "id": "layer2",
            "name": "Engrave Layer"
        }
    ],
    "is_ready": true
}
```

Or if no SVG is loaded:

```json
{
    "message": "No SVG loaded",
    "is_ready": false
}
```

#### `GET /api/svg/filename`

Get the filename of the currently loaded SVG.

**Response:**

```json
{
    "filename": "my_design.svg",
    "has_svg": true
}
```

Or if no SVG is loaded:

```json
{
    "filename": null,
    "has_svg": false
}
```

#### `DELETE /svg/clear`

Clear the current SVG from memory.

**Response:**

```json
{
    "message": "SVG cleared"
}
```

**Error Response (409 - if plotting):**

```json
{
    "error": "Cannot clear SVG while plotting"
}
```

### Plotting Operations

#### `POST /plot/<layer_name>`

Start plotting a specific layer from the current SVG.

**Parameters:**

- `layer_name`: Name or ID of the layer to plot. Use "all" to plot all layers.

**Request Body (optional):**

```json
{
    "config_content": {
        "speed": 2000,
        "up_position": 2000,
        "down_position": 1000
    }
}
```

**Response (202 Accepted):**

```json
{
    "message": "Plot started",
    "layer_name": "Cut Layer",
    "svg_name": "my_design.svg"
}
```

**Error Response (404 - layer not found):**

```json
{
    "error": "Layer 'unknown_layer' not found",
    "available_layers": [
        {
            "id": "layer1",
            "name": "Cut Layer"
        },
        {
            "id": "layer2",
            "name": "Engrave Layer"
        }
    ]
}
```

**Error Response (409 - plotter busy):**

```json
{
    "error": "Plotter is busy",
    "current_status": "PLOTTING"
}
```

#### `POST /plot/stop`

Stop the current plotting operation.

**Response:**

```json
{
    "message": "Plot stopped",
    "success": true
}
```

#### `POST /plot/pause`

Pause the current plotting operation.

**Response:**

```json
{
    "message": "Plot paused",
    "success": true
}
```

#### `POST /plot/resume`

Resume a paused plotting operation.

**Response:**

```json
{
    "message": "Plot resumed",
    "success": true
}
```

### Utility Commands

#### `POST /utility/<command>`

Execute utility commands on the plotter.

**Available Commands:**

- `pen_up`: Raise the pen
- `pen_down`: Lower the pen
- `motors_off`: Turn off motors
- `home`: Home the plotter

**Request Body (optional):**

```json
{
    "parameter": "value"
}
```

**Response:**

```json
{
    "result": "Command executed successfully"
}
```

### Logs

#### `GET /logs`

Retrieve recent log entries.

**Query Parameters:**

- `lines` (optional): Number of log lines to return (default: 100)

**Response:**

```json
{
    "logs": ["2023-08-01 12:00:00,000 INFO: SVG uploaded successfully: my_design.svg", "2023-08-01 12:01:00,000 INFO: Received request to plot layer 'Cut Layer' from my_design.svg", "2023-08-01 12:01:01,000 INFO: Successfully plotted layer Cut Layer"]
}
```

## Usage Examples

### Complete Workflow Example

1. **Upload an SVG:**

```bash
curl -X POST -F "file=@design.svg" http://localhost:5000/api/svg
```

2. **Check status:**

```bash
curl http://localhost:5000/status
```

3. **Plot a specific layer:**

```bash
curl -X POST http://localhost:5000/plot/Cut%20Layer \
  -H "Content-Type: application/json" \
  -d '{"config_content": {"speed": 2000}}'
```

4. **Monitor progress:**

```bash
# Poll the status endpoint
curl http://localhost:5000/status
```

5. **Stop plotting if needed:**

```bash
curl -X POST http://localhost:5000/plot/stop
```

### JavaScript/Frontend Example

```javascript
class PlotterAPI {
    constructor(baseURL = "http://localhost:5000") {
        this.baseURL = baseURL;
    }

    async uploadSVG(file) {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(`${this.baseURL}/api/svg`, {
            method: "POST",
            body: formData,
        });

        return response.json();
    }

    async getStatus() {
        const response = await fetch(`${this.baseURL}/status`);
        return response.json();
    }

    async plotLayer(layerName, config = {}) {
        const response = await fetch(`${this.baseURL}/plot/${encodeURIComponent(layerName)}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ config_content: config }),
        });

        return response.json();
    }

    async stopPlot() {
        const response = await fetch(`${this.baseURL}/plot/stop`, {
            method: "POST",
        });

        return response.json();
    }
}

// Usage
const api = new PlotterAPI();

// Upload SVG
const fileInput = document.getElementById("svg-file");
const result = await api.uploadSVG(fileInput.files[0]);

// Start plotting
await api.plotLayer("Cut Layer", { speed: 2000 });

// Monitor status
setInterval(async () => {
    const status = await api.getStatus();
    console.log(`Progress: ${status.system.plot_progress}%`);
}, 1000);
```

## Error Handling

The API uses standard HTTP status codes and always returns JSON responses for errors:

```json
{
    "error": "Description of the error"
}
```

Common error scenarios:

- No SVG uploaded when trying to plot
- Invalid layer name
- Plotter busy
- File too large (>500MB)
- Cannot clear SVG while plotting

## Best Practices

1. **Always check status** before starting a plot to ensure the plotter is idle
2. **Use chunked upload** for files larger than a few MB to provide progress feedback
3. **Handle errors gracefully** - the plotter may be busy or in an error state
4. **Poll the status endpoint** during plotting to monitor progress
5. **Validate layer names** before attempting to plot

## Migration from Project-Based API

If migrating from the previous project-based API:

1. Replace `/api/project` POST with `/api/svg` POST
2. Remove `/api/project/svg` - now just `/api/svg`
3. Add calls to `/api/svg/filename` to get current filename
4. Replace `/project` DELETE with `/svg/clear` DELETE
5. Remove project ID/name from plot requests - only layer name is needed
