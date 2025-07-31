# NextDraw Plotter API - Project-Based System

## Overview

This is a simplified, project-based API for controlling NextDraw plotters on Raspberry Pi. The system handles one project at a time with support for multiple SVG layers.

## Key Features

- **Single Active Project**: One project in memory at a time for optimal performance
- **Single SVG File**: One SVG file containing all layers internally
- **Layer Detection**: Automatically detects layers within the SVG file
- **Sequential Workflow**: Upload SVG first, then plot individual layers on demand
- **Chunked Uploads**: Support for large SVG files through chunked uploading
- **Real-time Status**: Monitor upload progress and plotting status
- **Resource Efficient**: Optimized for Raspberry Pi 5 constraints

## Quick Start

### 1. Migration from Old API

If you're upgrading from the job-based API:

```bash
python migrate_to_new_api.py
```

### 2. Start the Server

```bash
python app.py
# Or with gunicorn:
gunicorn -c gunicorn.conf.py wsgi:app
```

### 3. Test the API

```bash
python test_new_api.py
```

## Basic Workflow

1. **Create a Project**

    ```bash
    curl -X POST http://localhost:5000/project \
      -H "Content-Type: application/json" \
      -d '{"name": "My Project", "description": "Multi-layer design"}'
    ```

2. **Upload SVG File**

    ```bash
    curl -X POST http://localhost:5000/project/svg \
      -F "file=@design.svg"
    ```

3. **Check Status**

    ```bash
    curl http://localhost:5000/status
    ```

4. **Plot Layers**

    ```bash
    # Plot specific layer by name with configuration
    curl -X POST http://localhost:5000/plot/Base%20Layer \
      -H "Content-Type: application/json" \
      -d '{"speed": 50, "pen_up_position": 40}'

    # Wait for completion...

    # Plot another layer
    curl -X POST http://localhost:5000/plot/Detail%20Layer \
      -H "Content-Type: application/json" \
      -d '{"speed": 75, "pen_down_position": 85}'

    # Or plot all layers
    curl -X POST http://localhost:5000/plot/all
    ```

5. **Clear Project**
    ```bash
    curl -X DELETE http://localhost:5000/project
    ```

## API Endpoints

### System

- `GET /health` - Health check
- `GET /status` - Get system and project status

### Project Management

- `POST /project` - Create new project (clears existing)
- `DELETE /project` - Clear current project

### Layer Management

- `POST /project/svg` - Upload SVG file (supports chunked)

### Plotting

- `POST /plot/{layer_name}` - Start plotting a layer by name or "all" (config in request body)
- `POST /plot/pause` - Pause current plot
- `POST /plot/resume` - Resume paused plot
- `POST /plot/stop` - Stop current plot

### Configuration

- `GET /config` - Get plotter configuration
- `PUT /config` - Update plotter configuration

## File Structure

```
plot-runner-agent/
├── app.py                  # Main Flask application
├── project_manager.py      # Project and layer management
├── plotter_controller.py   # Plotter hardware control
├── config_manager.py       # Configuration management
├── projects/              # Project storage directory
├── logs/                  # Application logs
└── API_DOCUMENTATION.md   # Detailed API documentation
```

## Performance Considerations

- **Memory**: Only one project is kept in memory
- **Storage**: Old projects are automatically deleted
- **Uploads**: Use chunked uploads for files > 50MB
- **Concurrent Operations**: Layers upload in parallel, plotting is sequential

## Troubleshooting

### API Not Responding

```bash
# Check if service is running
ps aux | grep app.py

# Check logs
tail -f logs/app.log
```

### Upload Failures

- Ensure project is created first
- Check file size limits (500MB max)
- Ensure SVG file contains valid layer structure

### Plotting Issues

- Ensure SVG is uploaded (status = "ready")
- Check available layers in /status response
- Use exact layer names as shown in available_layers
- Check plotter connection in /status
- Verify plotter configuration in /config

## Documentation

- `API_DOCUMENTATION.md` - Complete API reference
- `MIGRATION_GUIDE.md` - Migration from old API
- `test_new_api.py` - API test examples

## Support

For issues or questions:

1. Check the logs in `logs/app.log`
2. Run the test script: `python test_new_api.py`
3. Refer to API_DOCUMENTATION.md for detailed information
