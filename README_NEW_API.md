# NextDraw Plotter API - Project-Based System

## Overview

This is a simplified, project-based API for controlling NextDraw plotters on Raspberry Pi. The system handles one project at a time with support for multiple SVG layers.

## Key Features

- **Single Active Project**: One project in memory at a time for optimal performance
- **Multi-Layer Support**: Projects can contain multiple SVG layers
- **Sequential Workflow**: Upload all layers first, then plot on demand
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
      -d '{"name": "My Project", "total_layers": 2}'
    ```

2. **Upload Layers**

    ```bash
    curl -X POST http://localhost:5000/project/layer/layer_0 \
      -F "file=@layer0.svg"

    curl -X POST http://localhost:5000/project/layer/layer_1 \
      -F "file=@layer1.svg"
    ```

3. **Check Status**

    ```bash
    curl http://localhost:5000/status
    ```

4. **Plot Layers**

    ```bash
    # Plot with layer-specific configuration
    curl -X POST http://localhost:5000/plot/layer_0 \
      -H "Content-Type: application/json" \
      -d '{"speed": 50, "pen_up_position": 40}'

    # Wait for completion...

    curl -X POST http://localhost:5000/plot/layer_1 \
      -H "Content-Type: application/json" \
      -d '{"speed": 75, "pen_down_position": 85}'
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

- `POST /project/layer/{layer_id}` - Upload layer (supports chunked)

### Plotting

- `POST /plot/{layer_id}` - Start plotting a layer (config in request body)
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
- Verify layer ID format (layer_0, layer_1, etc.)

### Plotting Issues

- Ensure all layers are uploaded (status = "ready")
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
