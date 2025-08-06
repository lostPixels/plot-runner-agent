# Simplified NextDraw Plotter API Changes

## Overview

The NextDraw Plotter API has been simplified to remove the concept of projects. The new API works with a single current SVG file at a time, making the workflow more straightforward and easier to understand.

## Key Changes

### 1. Removed Project Concept
- **Before**: Required creating a project, then uploading an SVG to that project
- **After**: Direct SVG upload that becomes the current working file

### 2. Simplified Endpoints
- **Removed**: `/api/project` (POST) - No longer need to create projects
- **Removed**: `/api/project/svg` - SVG upload moved to `/api/svg`
- **Removed**: `/project` (DELETE) - Replaced with `/svg/clear`
- **New**: `/api/svg/filename` (GET) - Get the filename of current SVG

### 3. Endpoint Changes

| Old Endpoint | New Endpoint | Description |
|--------------|--------------|-------------|
| `POST /api/project` | Not needed | Projects no longer exist |
| `POST /api/project/svg` | `POST /api/svg` | Upload SVG directly |
| `DELETE /project` | `DELETE /svg/clear` | Clear current SVG |
| `GET /status` | `GET /status` | Simplified response without project info |

### 4. Simplified Workflow

#### Old Workflow:
1. Create a project: `POST /api/project`
2. Upload SVG to project: `POST /api/project/svg`
3. Plot a layer: `POST /plot/<layer_name>`
4. Delete project: `DELETE /project`

#### New Workflow:
1. Upload SVG: `POST /api/svg`
2. Plot a layer: `POST /plot/<layer_name>`
3. Clear SVG (optional): `DELETE /svg/clear`

## API Usage Examples

### Upload an SVG
```bash
# Direct upload
curl -X POST -F "file=@design.svg" http://localhost:5000/api/svg

# Chunked upload (for large files)
# See API documentation for full chunked upload example
```

### Get Current SVG Filename
```bash
curl http://localhost:5000/api/svg/filename
```

Response:
```json
{
    "filename": "design.svg",
    "has_svg": true
}
```

### Plot a Layer
```bash
curl -X POST http://localhost:5000/plot/Layer1 \
  -H "Content-Type: application/json" \
  -d '{"config_content": {"speed": 2000}}'
```

### Clear Current SVG
```bash
curl -X DELETE http://localhost:5000/svg/clear
```

## File Changes

### New Files
- `svg_manager.py` - Manages single SVG file (replaces project_manager.py)
- `api-documentation.md` - Updated API documentation
- `test_simplified_api.py` - Test suite for simplified API

### Backup Files
- `app_with_projects.py` - Original app.py with project support
- `project_manager_old.py` - Original project manager
- `api-documentation-with-projects.md` - Original API documentation

## Migration Guide

### For Frontend/UI Developers

1. **Remove Project Creation Step**
   - Delete any UI for creating/naming projects
   - Remove project ID/name storage

2. **Update SVG Upload**
   - Change endpoint from `/api/project/svg` to `/api/svg`
   - Remove project context from upload

3. **Add Filename Display**
   - Use `/api/svg/filename` to show current file
   - Update UI to show single current SVG status

4. **Simplify Status Handling**
   - Status response no longer has project section
   - Only track SVG and system status

### For Backend Integration

1. **Update API Calls**
   ```python
   # Old way
   response = requests.post(f"{base_url}/api/project", json={"name": "My Project"})
   project_id = response.json()['project']['id']
   requests.post(f"{base_url}/api/project/svg", files={'file': svg_file})

   # New way
   requests.post(f"{base_url}/api/svg", files={'file': svg_file})
   ```

2. **Simplified Status Check**
   ```python
   # Status response structure changed
   status = requests.get(f"{base_url}/status").json()
   # No more status['project'], just status['svg'] and status['system']
   ```

3. **Clear SVG Instead of Delete Project**
   ```python
   # Old way
   requests.delete(f"{base_url}/project")

   # New way
   requests.delete(f"{base_url}/svg/clear")
   ```

## Benefits

1. **Simpler Workflow** - No need to manage project IDs or states
2. **Clearer Mental Model** - One SVG at a time, easy to understand
3. **Reduced API Calls** - No project creation step needed
4. **Less State Management** - No project lifecycle to track

## Testing

Run the test suite to verify the new API:

```bash
python test_simplified_api.py
```

This will test all the new endpoints and verify the simplified workflow.

## Rollback

If you need to rollback to the project-based system:

1. Restore original files:
   ```bash
   cp app_with_projects.py app.py
   cp project_manager_old.py project_manager.py
   cp api-documentation-with-projects.md api-documentation.md
   ```

2. Restart the service:
   ```bash
   sudo systemctl restart nextdraw-api
   ```

## Support

For questions or issues with the simplified API, please refer to:
- `api-documentation.md` - Complete API reference
- `test_simplified_api.py` - Working examples of all endpoints
