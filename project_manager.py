"""
Project Manager for NextDraw Plotter API
Handles project-based workflow with multi-layer SVG support
"""

import os
import json
import time
import shutil
import threading
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class LayerStatus(Enum):
    """Status for individual layer uploads"""
    NOT_STARTED = "not_started"
    UPLOADING = "uploading"
    COMPLETE = "complete"
    ERROR = "error"

class ProjectStatus(Enum):
    """Overall project status"""
    CREATED = "created"
    UPLOADING = "uploading"
    READY = "ready"
    PLOTTING = "plotting"
    COMPLETE = "complete"
    ERROR = "error"

class ProjectManager:
    """Manages single active project with multi-layer support"""

    def __init__(self, storage_dir='projects'):
        self.storage_dir = storage_dir
        self.current_project = None
        self.project_lock = threading.Lock()

        # Create storage directory
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)

        # Clean up any temp directories on startup
        self._cleanup_temp_dirs()

    def create_project(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new project, clearing any existing project"""
        try:
            with self.project_lock:
                # Clear existing project if any
                if self.current_project:
                    self._clear_project()

                # Create project ID
                project_id = f"project_{int(time.time())}_{hashlib.md5(json.dumps(project_data, sort_keys=True).encode()).hexdigest()[:8]}"

                # Create project structure
                project_dir = os.path.join(self.storage_dir, project_id)
                os.makedirs(project_dir)
                os.makedirs(os.path.join(project_dir, 'layers'))
                os.makedirs(os.path.join(project_dir, 'temp'))

                # Initialize project
                self.current_project = {
                    'id': project_id,
                    'name': project_data.get('name', f'Project_{int(time.time())}'),
                    'description': project_data.get('description', ''),
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                    'status': ProjectStatus.CREATED.value,
                    'config': project_data.get('config', {}),
                    'layers': {},
                    'total_layers': project_data.get('total_layers', 1),
                    'uploaded_layers': 0,
                    'project_dir': project_dir,
                    'metadata': project_data.get('metadata', {})
                }

                # Initialize layers
                for i in range(self.current_project['total_layers']):
                    layer_id = f"layer_{i}"
                    self.current_project['layers'][layer_id] = {
                        'id': layer_id,
                        'index': i,
                        'name': project_data.get('layer_names', {}).get(layer_id, f"Layer {i}"),
                        'status': LayerStatus.NOT_STARTED.value,
                        'file_path': None,
                        'file_size': 0,
                        'upload_progress': 0,
                        'error_message': None
                    }

                # Save project state
                self._save_project_state()

                logger.info(f"Created project {project_id} with {self.current_project['total_layers']} layers")
                return self._get_project_info()

        except Exception as e:
            logger.error(f"Error creating project: {str(e)}")
            raise

    def upload_layer(self, layer_id: str, file_data: bytes, filename: str) -> Dict[str, Any]:
        """Upload a single layer SVG file"""
        try:
            with self.project_lock:
                if not self.current_project:
                    raise Exception("No active project")

                if layer_id not in self.current_project['layers']:
                    raise Exception(f"Invalid layer ID: {layer_id}")

                layer = self.current_project['layers'][layer_id]

                # Update status
                layer['status'] = LayerStatus.UPLOADING.value
                self.current_project['status'] = ProjectStatus.UPLOADING.value
                self.current_project['updated_at'] = datetime.now().isoformat()

                # Save file
                safe_filename = f"{layer_id}_{hashlib.md5(filename.encode()).hexdigest()[:8]}.svg"
                file_path = os.path.join(self.current_project['project_dir'], 'layers', safe_filename)

                with open(file_path, 'wb') as f:
                    f.write(file_data)

                # Update layer info
                layer['file_path'] = file_path
                layer['file_size'] = len(file_data)
                layer['original_filename'] = filename
                layer['uploaded_at'] = datetime.now().isoformat()
                layer['status'] = LayerStatus.COMPLETE.value
                layer['upload_progress'] = 100

                # Update project counts
                self.current_project['uploaded_layers'] = sum(
                    1 for l in self.current_project['layers'].values()
                    if l['status'] == LayerStatus.COMPLETE.value
                )

                # Check if all layers uploaded
                if self.current_project['uploaded_layers'] == self.current_project['total_layers']:
                    self.current_project['status'] = ProjectStatus.READY.value
                    logger.info(f"Project {self.current_project['id']} is ready for plotting")

                # Save state
                self._save_project_state()

                return self._get_layer_info(layer_id)

        except Exception as e:
            logger.error(f"Error uploading layer {layer_id}: {str(e)}")
            if self.current_project and layer_id in self.current_project['layers']:
                self.current_project['layers'][layer_id]['status'] = LayerStatus.ERROR.value
                self.current_project['layers'][layer_id]['error_message'] = str(e)
                self._save_project_state()
            raise

    def upload_layer_chunked(self, layer_id: str, chunk_data: bytes, chunk_info: Dict[str, Any]) -> Dict[str, Any]:
        """Handle chunked upload for large layer files"""
        try:
            with self.project_lock:
                if not self.current_project:
                    raise Exception("No active project")

                if layer_id not in self.current_project['layers']:
                    raise Exception(f"Invalid layer ID: {layer_id}")

                layer = self.current_project['layers'][layer_id]

                # Update status if first chunk
                if chunk_info['chunk_number'] == 0:
                    layer['status'] = LayerStatus.UPLOADING.value
                    self.current_project['status'] = ProjectStatus.UPLOADING.value

                # Create temp file for chunks
                temp_dir = os.path.join(self.current_project['project_dir'], 'temp')
                chunk_file_id = chunk_info.get('file_id', layer_id)
                chunk_path = os.path.join(temp_dir, f"{chunk_file_id}_chunk_{chunk_info['chunk_number']}")

                # Save chunk
                with open(chunk_path, 'wb') as f:
                    f.write(chunk_data)

                # Update progress
                layer['upload_progress'] = int((chunk_info['chunk_number'] + 1) / chunk_info['total_chunks'] * 100)

                # Check if all chunks received
                chunk_files = [f for f in os.listdir(temp_dir) if f.startswith(f"{chunk_file_id}_chunk_")]

                if len(chunk_files) == chunk_info['total_chunks']:
                    # Reassemble file
                    safe_filename = f"{layer_id}_{hashlib.md5(chunk_info['filename'].encode()).hexdigest()[:8]}.svg"
                    final_path = os.path.join(self.current_project['project_dir'], 'layers', safe_filename)

                    with open(final_path, 'wb') as final_file:
                        for i in range(chunk_info['total_chunks']):
                            chunk_path = os.path.join(temp_dir, f"{chunk_file_id}_chunk_{i}")
                            with open(chunk_path, 'rb') as chunk:
                                final_file.write(chunk.read())
                            # Remove chunk after reading
                            os.remove(chunk_path)

                    # Update layer info
                    layer['file_path'] = final_path
                    layer['file_size'] = os.path.getsize(final_path)
                    layer['original_filename'] = chunk_info['filename']
                    layer['uploaded_at'] = datetime.now().isoformat()
                    layer['status'] = LayerStatus.COMPLETE.value
                    layer['upload_progress'] = 100

                    # Update project counts
                    self.current_project['uploaded_layers'] = sum(
                        1 for l in self.current_project['layers'].values()
                        if l['status'] == LayerStatus.COMPLETE.value
                    )

                    # Check if all layers uploaded
                    if self.current_project['uploaded_layers'] == self.current_project['total_layers']:
                        self.current_project['status'] = ProjectStatus.READY.value
                        logger.info(f"Project {self.current_project['id']} is ready for plotting")

                # Save state
                self._save_project_state()

                return {
                    'layer_id': layer_id,
                    'status': layer['status'],
                    'progress': layer['upload_progress'],
                    'chunks_received': len(chunk_files),
                    'total_chunks': chunk_info['total_chunks']
                }

        except Exception as e:
            logger.error(f"Error handling chunked upload for layer {layer_id}: {str(e)}")
            if self.current_project and layer_id in self.current_project['layers']:
                self.current_project['layers'][layer_id]['status'] = LayerStatus.ERROR.value
                self.current_project['layers'][layer_id]['error_message'] = str(e)
                self._save_project_state()
            raise

    def get_project_status(self) -> Optional[Dict[str, Any]]:
        """Get current project status"""
        with self.project_lock:
            if not self.current_project:
                return None
            return self._get_project_info()

    def get_layer_info(self, layer_id: str) -> Optional[Dict[str, Any]]:
        """Get specific layer information"""
        with self.project_lock:
            if not self.current_project:
                return None
            if layer_id not in self.current_project['layers']:
                return None
            return self._get_layer_info(layer_id)

    def is_project_ready(self) -> bool:
        """Check if current project is ready for plotting"""
        with self.project_lock:
            if not self.current_project:
                return False
            return self.current_project['status'] == ProjectStatus.READY.value

    def get_layer_file_path(self, layer_id: str) -> Optional[str]:
        """Get file path for a specific layer"""
        with self.project_lock:
            if not self.current_project:
                return None
            if layer_id not in self.current_project['layers']:
                return None
            return self.current_project['layers'][layer_id].get('file_path')

    def update_project_status(self, status: ProjectStatus):
        """Update project status"""
        with self.project_lock:
            if self.current_project:
                self.current_project['status'] = status.value
                self.current_project['updated_at'] = datetime.now().isoformat()
                self._save_project_state()

    def clear_project(self) -> bool:
        """Clear current project from memory"""
        try:
            with self.project_lock:
                if self.current_project:
                    self._clear_project()
                    return True
                return False
        except Exception as e:
            logger.error(f"Error clearing project: {str(e)}")
            return False

    def _clear_project(self):
        """Internal method to clear project data and files"""
        if self.current_project and 'project_dir' in self.current_project:
            project_dir = self.current_project['project_dir']
            if os.path.exists(project_dir):
                shutil.rmtree(project_dir)
                logger.info(f"Removed project directory: {project_dir}")

        self.current_project = None

    def _save_project_state(self):
        """Save current project state to disk"""
        if not self.current_project:
            return

        state_file = os.path.join(self.current_project['project_dir'], 'project_state.json')

        # Create a copy without the project_dir path for serialization
        state_data = self.current_project.copy()
        state_data.pop('project_dir', None)

        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2)

    def _get_project_info(self) -> Dict[str, Any]:
        """Get sanitized project information"""
        if not self.current_project:
            return None

        return {
            'id': self.current_project['id'],
            'name': self.current_project['name'],
            'description': self.current_project['description'],
            'status': self.current_project['status'],
            'created_at': self.current_project['created_at'],
            'updated_at': self.current_project['updated_at'],
            'total_layers': self.current_project['total_layers'],
            'uploaded_layers': self.current_project['uploaded_layers'],
            'layers': {
                layer_id: self._get_layer_info(layer_id)
                for layer_id in self.current_project['layers']
            },
            'metadata': self.current_project.get('metadata', {})
        }

    def _get_layer_info(self, layer_id: str) -> Dict[str, Any]:
        """Get sanitized layer information"""
        if not self.current_project or layer_id not in self.current_project['layers']:
            return None

        layer = self.current_project['layers'][layer_id]
        return {
            'id': layer['id'],
            'index': layer['index'],
            'name': layer['name'],
            'status': layer['status'],
            'file_size': layer['file_size'],
            'upload_progress': layer['upload_progress'],
            'uploaded_at': layer.get('uploaded_at'),
            'error_message': layer.get('error_message'),
            'original_filename': layer.get('original_filename')
        }

    def _cleanup_temp_dirs(self):
        """Clean up temporary directories on startup"""
        try:
            for project_dir in os.listdir(self.storage_dir):
                temp_dir = os.path.join(self.storage_dir, project_dir, 'temp')
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning temp directories: {str(e)}")
