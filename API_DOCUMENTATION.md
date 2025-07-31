# NextDraw Plotter API Documentation

## Overview

The NextDraw Plotter API provides a REST interface for controlling NextDraw plotters with a project-based workflow. The API is designed to handle multi-layer SVG projects efficiently on resource-constrained devices like Raspberry Pi 5.

### Key Features

- Single active project management
- Multi-layer SVG support
- Chunked upload for large files
- Real-time status monitoring
- Layer-by-layer plotting control

### Base URL

```
http://<raspberry-pi-ip>:5000
```

## Workflow

1. **Create a new project** - Define project metadata and number of layers
2. **Upload layer files** - Upload SVG files for each layer (sequential or parallel)
3. **Monitor status** - Check upload progress and project readiness
4. **Execute plots** - Plot individual layers on demand
5. **Clear project** - Remove project data when done or before creating a new one

## API Endpoints

### Health Check

#### GET /health

Check if the API server is running.

**Response:**

```json
{
    "status": "healthy",
    "timestamp": "2024-01-15T10:30:00.000Z",
    "version": "2.0.0",
    "uptime_start": "2024-01-15T09:00:00.000Z"
}
```

### Status

#### GET /status

Get comprehensive system and project status.

**Response:**

```json
{
    "timestamp": "2024-01-15T10:30:00.000Z",
    "system": {
        "plotter_status": "IDLE", // IDLE, PLOTTING, PAUSED, ERROR
        "current_layer": null, // layer_id or null
        "plot_progress": 0, // 0-100
        "last_error": null,
        "plotter_connected": true
    },
    "project": {
        "id": "project_1234567890_abcd1234",
        "name": "My Project",
        "description": "Project description",
        "status": "ready", // created, uploading, ready, plotting, complete, error
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-15T10:15:00.000Z",
        "total_layers": 3,
        "uploaded_layers": 3,
        "layers": {
            "layer_0": {
                "id": "layer_0",
                "index": 0,
                "name": "Base Layer",
                "status": "complete", // not_started, uploading, complete, error
                "file_size": 1048576,
                "upload_progress": 100,
                "uploaded_at": "2024-01-15T10:10:00.000Z",
                "error_message": null,
                "original_filename": "base.svg"
            },
            "layer_1": {
                "id": "layer_1",
                "index": 1,
                "name": "Middle Layer",
                "status": "complete",
                "file_size": 2097152,
                "upload_progress": 100,
                "uploaded_at": "2024-01-15T10:12:00.000Z",
                "error_message": null,
                "original_filename": "middle.svg"
            },
            "layer_2": {
                "id": "layer_2",
                "index": 2,
                "name": "Top Layer",
                "status": "uploading",
                "file_size": 0,
                "upload_progress": 45,
                "uploaded_at": null,
                "error_message": null,
                "original_filename": null
            }
        },
        "metadata": {
            "custom_field": "value"
        }
    }
}
```

### Project Management

#### POST /project

Create a new project. This will clear any existing project data.

**Request Body:**

```json
{
    "name": "My Project",
    "description": "A multi-layer plotter project",
    "total_layers": 3,
    "layer_names": {
        "layer_0": "Base Layer",
        "layer_1": "Middle Layer",
        "layer_2": "Top Layer"
    },
    "config": {
        "default_speed": 100,
        "pen_down_position": 90
    },
    "metadata": {
        "author": "John Doe",
        "created_with": "Inkscape"
    }
}
```

**Response:**

```json
{
  "message": "Project created successfully",
  "project": {
    "id": "project_1234567890_abcd1234",
    "name": "My Project",
    "status": "created",
    "total_layers": 3,
    "uploaded_layers": 0,
    "layers": { ... }
  }
}
```

#### DELETE /project

Clear the current project from memory.

**Response:**

```json
{
    "message": "Project cleared"
}
```

### Layer Upload

#### POST /project/layer/{layer_id}

Upload an SVG file for a specific layer. Supports both direct upload and chunked upload for large files.

##### Direct Upload (files < 50MB recommended)

**Request:**

- Method: POST
- Content-Type: multipart/form-data
- Body:
    - `file`: SVG file

**Example cURL:**

```bash
curl -X POST \
  -F "file=@layer1.svg" \
  http://localhost:5000/project/layer/layer_0
```

**Response:**

```json
{
    "message": "Layer uploaded successfully",
    "layer": {
        "id": "layer_0",
        "name": "Base Layer",
        "status": "complete",
        "file_size": 1048576,
        "upload_progress": 100,
        "uploaded_at": "2024-01-15T10:10:00.000Z"
    }
}
```

##### Chunked Upload (for large files)

**Request:**

- Method: POST
- Content-Type: multipart/form-data
- Body:
    - `chunk_data`: File chunk
    - `chunk_number`: Current chunk index (0-based)
    - `total_chunks`: Total number of chunks
    - `file_id`: Unique identifier for the file
    - `filename`: Original filename

**Example cURL:**

```bash
# Upload chunk 0 of 10
curl -X POST \
  -F "chunk_data=@chunk_0.part" \
  -F "chunk_number=0" \
  -F "total_chunks=10" \
  -F "file_id=upload_123456" \
  -F "filename=large_layer.svg" \
  http://localhost:5000/project/layer/layer_1
```

**Response (chunk received):**

```json
{
    "layer_id": "layer_1",
    "status": "uploading",
    "progress": 10,
    "chunks_received": 1,
    "total_chunks": 10
}
```

**Response (all chunks received):**

```json
{
    "layer_id": "layer_1",
    "status": "complete",
    "progress": 100,
    "chunks_received": 10,
    "total_chunks": 10
}
```

### Plotting Control

#### POST /plot/{layer_id}

Start plotting a specific layer. The project must be in "ready" status. Configuration parameters can be passed in the request body to override defaults for this specific plot.

**Request Body (optional):**

```json
{
    "speed": 150,
    "pen_up_position": 45,
    "pen_down_position": 85
}
```

**Response:**

```json
{
    "message": "Plot started",
    "layer_id": "layer_0",
    "layer_name": "Base Layer"
}
```

#### POST /plot/pause

Pause the current plotting operation.

**Response:**

```json
{
    "message": "Plot paused",
    "success": true
}
```

#### POST /plot/resume

Resume a paused plotting operation.

**Response:**

```json
{
    "message": "Plot resumed",
    "success": true
}
```

#### POST /plot/stop

Stop the current plotting operation.

**Response:**

```json
{
    "message": "Plot stopped",
    "success": true
}
```

### Configuration

#### GET /config

Get current plotter configuration.

**Response:**

```json
{
    "plotter_settings": {
        "port": "/dev/ttyUSB0",
        "baud_rate": 115200,
        "timeout": 30
    },
    "pen_config": {
        "pen_up_position": 40,
        "pen_down_position": 90,
        "pen_up_speed": 150,
        "pen_down_speed": 150,
        "pen_up_delay": 0,
        "pen_down_delay": 0
    },
    "movement_config": {
        "speed": 100,
        "acceleration": 100,
        "resolution": 1
    },
    "paper_config": {
        "width": 420,
        "height": 297,
        "margin_top": 10,
        "margin_bottom": 10,
        "margin_left": 10,
        "margin_right": 10
    }
}
```

#### PUT /config

Update plotter configuration.

**Request Body:**

```json
{
    "pen_config": {
        "pen_up_position": 45,
        "pen_down_position": 85
    },
    "movement_config": {
        "speed": 150
    }
}
```

**Response:**

```json
{
  "message": "Configuration updated",
  "config": { ... }
}
```

## Error Responses

All endpoints may return error responses in the following format:

```json
{
    "error": "Error message description"
}
```

Common HTTP status codes:

- `200` - Success
- `201` - Created
- `202` - Accepted (async operation started)
- `400` - Bad Request
- `404` - Not Found
- `409` - Conflict (e.g., plotter busy)
- `413` - Request Entity Too Large
- `500` - Internal Server Error

## Example Implementation

### Python Example

```python
import requests
import os

# API base URL
BASE_URL = "http://192.168.1.100:5000"

# 1. Create a project
project_data = {
    "name": "Test Project",
    "description": "A test project with 2 layers",
    "total_layers": 2,
    "layer_names": {
        "layer_0": "Black Layer",
        "layer_1": "Red Layer"
    }
}

response = requests.post(f"{BASE_URL}/project", json=project_data)
project = response.json()
print(f"Created project: {project['project']['id']}")

# 2. Upload layers
for i in range(2):
    layer_id = f"layer_{i}"
    with open(f"layer_{i}.svg", "rb") as f:
        files = {"file": f}
        response = requests.post(f"{BASE_URL}/project/layer/{layer_id}", files=files)
        print(f"Uploaded {layer_id}: {response.json()}")

# 3. Check status
response = requests.get(f"{BASE_URL}/status")
status = response.json()
print(f"Project status: {status['project']['status']}")

# 4. Plot layers
for i in range(2):
    layer_id = f"layer_{i}"
    # Pass layer-specific configuration
    plot_config = {
        "speed": 50 + (i * 25),  # Different speed for each layer
        "pen_up_position": 40,
        "pen_down_position": 90
    }
    response = requests.post(f"{BASE_URL}/plot/{layer_id}", json=plot_config)
    print(f"Started plotting {layer_id}")

    # Wait for completion
    while True:
        response = requests.get(f"{BASE_URL}/status")
        status = response.json()
        if status['system']['plotter_status'] == "IDLE":
            break
        time.sleep(1)

# 5. Clear project
response = requests.delete(f"{BASE_URL}/project")
print("Project cleared")
```

### JavaScript Example

```javascript
const BASE_URL = "http://192.168.1.100:5000";

async function runPlotterProject() {
    // 1. Create project
    const projectData = {
        name: "Test Project",
        description: "A test project with 2 layers",
        total_layers: 2,
        layer_names: {
            layer_0: "Black Layer",
            layer_1: "Red Layer",
        },
    };

    let response = await fetch(`${BASE_URL}/project`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(projectData),
    });
    const project = await response.json();
    console.log("Created project:", project.project.id);

    // 2. Upload layers
    for (let i = 0; i < 2; i++) {
        const layerId = `layer_${i}`;
        const fileInput = document.getElementById(`file_layer_${i}`);
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);

        response = await fetch(`${BASE_URL}/project/layer/${layerId}`, {
            method: "POST",
            body: formData,
        });
        console.log(`Uploaded ${layerId}:`, await response.json());
    }

    // 3. Check status
    response = await fetch(`${BASE_URL}/status`);
    const status = await response.json();
    console.log("Project status:", status.project.status);

    // 4. Plot layers
    for (let i = 0; i < 2; i++) {
        const layerId = `layer_${i}`;
        // Pass layer-specific configuration
        const plotConfig = {
            speed: 50 + i * 25, // Different speed for each layer
            pen_up_position: 40,
            pen_down_position: 90,
        };
        response = await fetch(`${BASE_URL}/plot/${layerId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(plotConfig),
        });
        console.log(`Started plotting ${layerId}`);

        // Wait for completion
        while (true) {
            response = await fetch(`${BASE_URL}/status`);
            const status = await response.json();
            if (status.system.plotter_status === "IDLE") {
                break;
            }
            await new Promise((resolve) => setTimeout(resolve, 1000));
        }
    }

    // 5. Clear project
    response = await fetch(`${BASE_URL}/project`, {
        method: "DELETE",
    });
    console.log("Project cleared");
}
```

## Performance Considerations

1. **File Size Limits**: Maximum file size is 500MB per layer
2. **Chunked Uploads**: Use chunked uploads for files larger than 50MB
3. Memory Usage: Only one project is kept in memory at a time
4. Concurrent Uploads: Layers can be uploaded in parallel for faster preparation
5. File Cleanup: Project files are automatically deleted when a new project is created

## Best Practices

1. Always check the `/status` endpoint before starting operations
2. Use chunked uploads for large SVG files to avoid timeouts
3. Monitor upload progress through the status endpoint
4. Handle errors gracefully - the plotter may be busy or disconnected
5. Clear projects when done to free up storage space
6. Pass configuration parameters in the `/plot/{layer_id}` request body for layer-specific settings
