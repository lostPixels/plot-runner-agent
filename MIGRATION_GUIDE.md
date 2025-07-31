# Migration Guide: From Job Queue to Project-Based API

## Overview

This guide helps you migrate from the old job queue-based API to the new simplified project-based workflow. The new API is designed for better performance on Raspberry Pi and provides a cleaner, more intuitive interface for multi-layer plotting projects.

## Key Changes

### 1. Conceptual Changes

**Old System:**
- Job queue with multiple concurrent jobs
- Single SVG per job
- Jobs could be queued, reordered, and managed independently
- Complex state management with job history

**New System:**
- Single active project at a time
- Multiple layers (SVGs) per project
- Sequential layer upload followed by on-demand plotting
- Simplified state with focus on current project only

### 2. Workflow Changes

**Old Workflow:**
```
1. Submit job with SVG → 2. Job queued → 3. Job processed automatically → 4. Next job
```

**New Workflow:**
```
1. Create project → 2. Upload all layers → 3. Plot layers on demand → 4. Clear project
```

## API Endpoint Mapping

| Old Endpoint | New Endpoint | Notes |
|--------------|--------------|-------|
| `POST /submit-plot` | `POST /project` + `POST /project/layer/{id}` | Split into project creation and layer upload |
| `POST /submit-plot-json` | `POST /project` + `POST /project/layer/{id}` | Use project creation with embedded config |
| `POST /upload-plot` | `POST /project/layer/{id}` | Direct layer upload |
| `POST /upload-plot-chunk` | `POST /project/layer/{id}` | Same endpoint handles chunks |
| `GET /jobs` | `GET /status` | Status now shows current project only |
| `POST /pause` | `POST /plot/pause` | Scoped to plot operations |
| `POST /resume` | `POST /plot/resume` | Scoped to plot operations |
| `POST /stop` | `POST /plot/stop` | Scoped to plot operations |

## Code Migration Examples

### Example 1: Simple Plot Submission

**Old Code:**
```python
# Submit a single SVG file
with open('design.svg', 'rb') as f:
    response = requests.post(
        f"{BASE_URL}/submit-plot",
        files={'file': f},
        data={
            'name': 'My Design',
            'priority': 1,
            'config': json.dumps({'speed': 100})
        }
    )
job_id = response.json()['job_id']
```

**New Code:**
```python
# Create project first
project_response = requests.post(
    f"{BASE_URL}/project",
    json={
        'name': 'My Design',
        'total_layers': 1,
        'config': {'speed': 100}
    }
)

# Upload the layer
with open('design.svg', 'rb') as f:
    response = requests.post(
        f"{BASE_URL}/project/layer/layer_0",
        files={'file': f}
    )

# Start plotting when ready
plot_response = requests.post(f"{BASE_URL}/plot/layer_0")
```

### Example 2: Multi-Layer Project

**Old Code:**
```python
# Submit multiple jobs for different colors
colors = ['black', 'red', 'blue']
job_ids = []

for color in colors:
    with open(f'{color}_layer.svg', 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/submit-plot",
            files={'file': f},
            data={'name': f'{color} layer', 'priority': len(colors) - colors.index(color)}
        )
    job_ids.append(response.json()['job_id'])
```

**New Code:**
```python
# Create multi-layer project
colors = ['black', 'red', 'blue']
project_response = requests.post(
    f"{BASE_URL}/project",
    json={
        'name': 'Multi-color Design',
        'total_layers': len(colors),
        'layer_names': {
            f'layer_{i}': f'{color} layer'
            for i, color in enumerate(colors)
        }
    }
)

# Upload all layers
for i, color in enumerate(colors):
    with open(f'{color}_layer.svg', 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/project/layer/layer_{i}",
            files={'file': f}
        )

# Plot each layer
for i in range(len(colors)):
    response = requests.post(f"{BASE_URL}/plot/layer_{i}")
    # Wait for completion before next layer
    while requests.get(f"{BASE_URL}/status").json()['system']['plotter_status'] != 'IDLE':
        time.sleep(1)
```

### Example 3: Large File Upload

**Old Code:**
```python
# Chunked upload
file_size = os.path.getsize('large_design.svg')
chunk_size = 1024 * 1024  # 1MB chunks
total_chunks = (file_size + chunk_size - 1) // chunk_size
file_id = str(uuid.uuid4())

with open('large_design.svg', 'rb') as f:
    for i in range(total_chunks):
        chunk = f.read(chunk_size)
        response = requests.post(
            f"{BASE_URL}/upload-plot-chunk",
            files={'chunk_data': chunk},
            data={
                'chunk': i,
                'total_chunks': total_chunks,
                'file_id': file_id,
                'filename': 'large_design.svg',
                'name': 'Large Design'
            }
        )
```

**New Code:**
```python
# Create project first
project_response = requests.post(
    f"{BASE_URL}/project",
    json={'name': 'Large Design', 'total_layers': 1}
)

# Chunked upload to layer
file_size = os.path.getsize('large_design.svg')
chunk_size = 1024 * 1024  # 1MB chunks
total_chunks = (file_size + chunk_size - 1) // chunk_size
file_id = str(uuid.uuid4())

with open('large_design.svg', 'rb') as f:
    for i in range(total_chunks):
        chunk = f.read(chunk_size)
        response = requests.post(
            f"{BASE_URL}/project/layer/layer_0",
            files={'chunk_data': chunk},
            data={
                'chunk_number': i,
                'total_chunks': total_chunks,
                'file_id': file_id,
                'filename': 'large_design.svg'
            }
        )
```

### Example 4: Status Monitoring

**Old Code:**
```python
# Check job queue status
response = requests.get(f"{BASE_URL}/jobs")
jobs = response.json()
queued_jobs = jobs['queued_jobs']
my_job = next(j for j in queued_jobs if j['id'] == job_id)
print(f"Job position: {my_job['queue_position']}")
```

**New Code:**
```python
# Check project and plot status
response = requests.get(f"{BASE_URL}/status")
status = response.json()

# Check project upload status
project = status['project']
if project:
    print(f"Project status: {project['status']}")
    print(f"Uploaded: {project['uploaded_layers']}/{project['total_layers']}")

# Check plotting status
system = status['system']
if system['plotter_status'] == 'PLOTTING':
    print(f"Plotting layer: {system['current_layer']}")
    print(f"Progress: {system['plot_progress']}%")
```

## Breaking Changes

1. **No Job Queue**: Projects are not queued. Only one project exists at a time.

2. **No Automatic Processing**: Layers must be explicitly plotted using the `/plot/{layer_id}` endpoint.

3. **No Job History**: Completed jobs are not stored. Only current project state is maintained.

4. **Required Project Creation**: You must create a project before uploading any files.

5. **Layer IDs**: Layers are identified by `layer_0`, `layer_1`, etc., not custom IDs.

6. **Single Active Project**: Creating a new project automatically clears the previous one.

## Migration Steps

1. **Update Base Endpoints**: Replace all old endpoints with new ones according to the mapping table.

2. **Implement Project Creation**: Add project creation step before any file uploads.

3. **Update Upload Logic**:
   - Change upload endpoints to include layer ID
   - Ensure all layers are uploaded before plotting

4. **Add Explicit Plot Calls**: Replace automatic job processing with explicit plot commands.

5. **Update Status Monitoring**: Adapt to new status response structure.

6. **Handle Project Lifecycle**: Add project cleanup when appropriate.

## Best Practices for New API

1. **Always Create Project First**: Never attempt to upload without an active project.

2. **Upload All Layers Before Plotting**: Ensure project status is "ready" before plotting.

3. **Monitor Upload Progress**: Use status endpoint to track multi-layer uploads.

4. **Sequential Layer Plotting**: Plot one layer at a time and wait for completion.

5. **Clean Up Projects**: Clear projects when done to free resources.

6. **Error Handling**: Check project existence in status before operations.

## Common Pitfalls

1. **Forgetting Project Creation**: Uploads will fail without an active project.

2. **Wrong Layer IDs**: Use `layer_0`, `layer_1`, etc., not custom names.

3. **Parallel Plotting**: Only one layer can be plotted at a time.

4. **Missing Layer Uploads**: Project won't be "ready" until all declared layers are uploaded.

5. **Resource Cleanup**: Not clearing projects can lead to storage issues on Raspberry Pi.

## Support

For questions or issues during migration:
1. Check the API documentation for detailed endpoint information
2. Monitor the application logs for error details
3. Test with small projects before migrating production workflows
