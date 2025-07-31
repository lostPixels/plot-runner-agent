# NextDraw Plotter API Documentation

## Overview

The NextDraw Plotter API provides a REST interface for controlling NextDraw plotters with a project-based workflow. The API is designed to handle multi-layer SVG projects efficiently on resource-constrained devices like Raspberry Pi 5.

### Key Features

- Single active project management
- Single SVG file with internal layers
- Chunked upload for large files
- Real-time status monitoring
- Layer-by-layer plotting control from within the SVG

### Base URL

```
http://<raspberry-pi-ip>:5000
```

## Workflow

1. **Create a new project** - Define project metadata
2. **Upload SVG file** - Upload single SVG file containing all layers
3. **Monitor status** - Check upload progress and available layers
4. **Execute plots** - Plot individual layers by name or all layers
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
        "svg_uploaded": true,
        "file_size": 5242880,
        "upload_progress": 100,
        "original_filename": "design.svg",
        "available_layers": [
            {
                "id": "layer_base",
                "name": "Base Layer"
            },
            {
                "id": "layer_middle",
                "name": "Middle Layer"
            },
            {
                "id": "layer_top",
                "name": "Top Layer"
            }
        ],
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
        "svg_uploaded": false,
        "available_layers": []
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

### SVG Upload

#### POST /project/svg

Upload the SVG file containing all layers. Supports both direct upload and chunked upload for large files.

##### Direct Upload (files < 50MB recommended)

**Request:**

- Method: POST
- Content-Type: multipart/form-data
- Body:
    - `file`: SVG file

**Example cURL:**

```bash
curl -X POST \
  -F "file=@design.svg" \
  http://localhost:5000/project/svg
```

**Response:**

```json
{
    "message": "SVG uploaded successfully",
    "project": {
        "id": "project_1234567890_abcd1234",
        "name": "My Project",
        "status": "ready",
        "svg_uploaded": true,
        "file_size": 1048576,
        "available_layers": [
            { "id": "layer_base", "name": "Base Layer" },
            { "id": "layer_middle", "name": "Middle Layer" }
        ]
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
  -F "filename=large_design.svg" \
  http://localhost:5000/project/svg
```

**Response (chunk received):**

```json
{
    "status": "uploading",
    "progress": 10,
    "chunks_received": 1,
    "total_chunks": 10
}
```

**Response (all chunks received):**

```json
{
    "status": "ready",
    "progress": 100,
    "chunks_received": 10,
    "total_chunks": 10
}
```

### Plotting Control

#### POST /plot/{layer_name}

Start plotting a specific layer by name. Use "all" to plot all layers. The project must be in "ready" status. Configuration parameters can be passed in the request body to override defaults for this specific plot.

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
    "description": "A test project with multiple layers in one SVG"
}

response = requests.post(f"{BASE_URL}/project", json=project_data)
project = response.json()
print(f"Created project: {project['project']['id']}")

# 2. Upload SVG file
with open("design.svg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/project/svg", files=files)
    project_info = response.json()
    print(f"Uploaded SVG: {project_info}")
    available_layers = project_info['project']['available_layers']

# 3. Check status
response = requests.get(f"{BASE_URL}/status")
status = response.json()
print(f"Project status: {status['project']['status']}")

# 4. Plot layers
for layer in available_layers:
    layer_name = layer['name']
    # Pass layer-specific configuration
    plot_config = {
        "speed": 75,
        "pen_up_position": 40,
        "pen_down_position": 90
    }
    response = requests.post(f"{BASE_URL}/plot/{layer_name}", json=plot_config)
    print(f"Started plotting {layer_name}")

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
        description: "A test project with multiple layers in one SVG",
    };

    let response = await fetch(`${BASE_URL}/project`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(projectData),
    });
    const project = await response.json();
    console.log("Created project:", project.project.id);

    // 2. Upload SVG file
    const fileInput = document.getElementById("svg_file");
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    response = await fetch(`${BASE_URL}/project/svg`, {
        method: "POST",
        body: formData,
    });
    const projectInfo = await response.json();
    console.log("Uploaded SVG:", projectInfo);
    const availableLayers = projectInfo.project.available_layers;

    // 3. Check status
    response = await fetch(`${BASE_URL}/status`);
    const status = await response.json();
    console.log("Project status:", status.project.status);

    // 4. Plot layers
    for (const layer of availableLayers) {
        const layerName = layer.name;
        // Pass layer-specific configuration
        const plotConfig = {
            speed: 75,
            pen_up_position: 40,
            pen_down_position: 90,
        };
        response = await fetch(`${BASE_URL}/plot/${layerName}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(plotConfig),
        });
        console.log(`Started plotting ${layerName}`);

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
3. **Memory Usage**: Only one project is kept in memory at a time
4. **Layer Detection**: Layers are automatically detected from the SVG file structure
5. **File Cleanup**: Project files are automatically deleted when a new project is created

## Best Practices

1. Always check the `/status` endpoint before starting operations
2. Use chunked uploads for large SVG files to avoid timeouts
3. Monitor upload progress through the status endpoint
4. Handle errors gracefully - the plotter may be busy or disconnected
5. Clear projects when done to free up storage space
6. Pass configuration parameters in the `/plot/{layer_name}` request body for layer-specific settings
7. Use layer names as shown in `available_layers` from the status response
