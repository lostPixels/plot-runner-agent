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
- Single SVG file containing multiple layers internally
- Upload one SVG file, then plot individual layers by name
- Simplified state with focus on current project only

### 2. Workflow Changes

**Old Workflow:**

```
1. Submit job with SVG → 2. Job queued → 3. Job processed automatically → 4. Next job
```

**New Workflow:**

```
1. Create project → 2. Upload SVG file → 3. Plot layers on demand → 4. Clear project
```

## API Endpoint Mapping

| Old Endpoint              | New Endpoint                          | Notes                                      |
| ------------------------- | ------------------------------------- | ------------------------------------------ |
| `POST /submit-plot`       | `POST /project` + `POST /project/svg` | Split into project creation and SVG upload |
| `POST /submit-plot-json`  | `POST /project` + `POST /project/svg` | Use project creation with embedded config  |
| `POST /upload-plot`       | `POST /project/svg`                   | Direct SVG upload                          |
| `POST /upload-plot-chunk` | `POST /project/svg`                   | Same endpoint handles chunks               |
| `GET /jobs`               | `GET /status`                         | Status now shows current project only      |
| `POST /pause`             | `POST /plot/pause`                    | Scoped to plot operations                  |
| `POST /resume`            | `POST /plot/resume`                   | Scoped to plot operations                  |
| `POST /stop`              | `POST /plot/stop`                     | Scoped to plot operations                  |

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
        'config': {'speed': 100}
    }
)

# Upload the SVG file
with open('design.svg', 'rb') as f:
    response = requests.post(
        f"{BASE_URL}/project/svg",
        files={'file': f}
    )

# Get available layers from response
available_layers = response.json()['project']['available_layers']

# Start plotting a specific layer by name
plot_response = requests.post(f"{BASE_URL}/plot/{available_layers[0]['name']}")
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
# Create project
project_response = requests.post(
    f"{BASE_URL}/project",
    json={
        'name': 'Multi-color Design',
        'description': 'Design with multiple color layers'
    }
)

# Upload single SVG containing all layers
with open('multi_layer_design.svg', 'rb') as f:
    response = requests.post(
        f"{BASE_URL}/project/svg",
        files={'file': f}
    )

# Get available layers
available_layers = response.json()['project']['available_layers']

# Plot each layer by name
for layer in available_layers:
    response = requests.post(f"{BASE_URL}/plot/{layer['name']}")
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
    json={'name': 'Large Design'}
)

# Chunked upload of SVG
file_size = os.path.getsize('large_design.svg')
chunk_size = 1024 * 1024  # 1MB chunks
total_chunks = (file_size + chunk_size - 1) // chunk_size
file_id = str(uuid.uuid4())

with open('large_design.svg', 'rb') as f:
    for i in range(total_chunks):
        chunk = f.read(chunk_size)
        response = requests.post(
            f"{BASE_URL}/project/svg",
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
    print(f"SVG uploaded: {project['svg_uploaded']}")
    print(f"Available layers: {[l['name'] for l in project['available_layers']]}")

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

4. **Required Project Creation**: You must create a project before uploading the SVG file.

5. **Layer Names**: Layers are identified by their names from within the SVG file, not by IDs.

6. **Single Active Project**: Creating a new project automatically clears the previous one.

7. **Single SVG File**: Only one SVG file per project, containing all layers internally.

## Migration Steps

1. **Update Base Endpoints**: Replace all old endpoints with new ones according to the mapping table.

2. **Implement Project Creation**: Add project creation step before any file uploads.

3. **Update Upload Logic**:
    - Change to single SVG upload endpoint
    - Extract layer information from the uploaded SVG

4. **Add Explicit Plot Calls**: Replace automatic job processing with explicit plot commands.

5. **Update Status Monitoring**: Adapt to new status response structure.

6. **Handle Project Lifecycle**: Add project cleanup when appropriate.

## Best Practices for New API

1. **Always Create Project First**: Never attempt to upload without an active project.

2. **Upload SVG Before Plotting**: Ensure project status is "ready" before plotting.

3. **Monitor Upload Progress**: Use status endpoint to track SVG upload progress.

4. **Sequential Layer Plotting**: Plot one layer at a time and wait for completion.

5. **Clean Up Projects**: Clear projects when done to free resources.

6. **Error Handling**: Check project existence in status before operations.

## Common Pitfalls

1. **Forgetting Project Creation**: Uploads will fail without an active project.

2. **Wrong Layer Names**: Use exact layer names as shown in available_layers response.

3. **Parallel Plotting**: Only one layer can be plotted at a time.

4. **Missing SVG Upload**: Project won't be "ready" until SVG file is uploaded.

5. **Resource Cleanup**: Not clearing projects can lead to storage issues on Raspberry Pi.

## Support

For questions or issues during migration:

1. Check the API documentation for detailed endpoint information
2. Monitor the application logs for error details
3. Test with small projects before migrating production workflows
