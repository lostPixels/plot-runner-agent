"""
Project Manager for NextDraw Plotter API
Handles project-based workflow with single SVG containing multiple layers
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
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class ProjectStatus(Enum):
    """Overall project status"""
    CREATED = "created"
    UPLOADING = "uploading"
    READY = "ready"
    PLOTTING = "plotting"
    COMPLETE = "complete"
    ERROR = "error"

class ProjectManager:
    """Manages single active project with SVG containing multiple layers"""

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
                    'svg_file': None,
                    'svg_uploaded': False,
                    'file_size': 0,
                    'available_layers': [],  # Will be populated when SVG is uploaded
                    'project_dir': project_dir,
                    'metadata': project_data.get('metadata', {}),
                    'upload_progress': 0,
                    'data': project_data.get('data', {})
                }

                # Save project state
                self._save_project_state()

                logger.info(f"Created project {project_id}")
                return self._get_project_info()

        except Exception as e:
            logger.error(f"Error creating project: {str(e)}")
            raise

    def upload_svg(self, file_data: bytes, filename: str) -> Dict[str, Any]:
        """Upload the single SVG file containing all layers"""
        try:
            with self.project_lock:
                if not self.current_project:
                    raise Exception("No active project")

                # Update status
                self.current_project['status'] = ProjectStatus.UPLOADING.value
                self.current_project['updated_at'] = datetime.now().isoformat()

                # Save file
                safe_filename = f"design_{hashlib.md5(filename.encode()).hexdigest()[:8]}.svg"
                file_path = os.path.join(self.current_project['project_dir'], safe_filename)

                with open(file_path, 'wb') as f:
                    f.write(file_data)

                # Update project info
                self.current_project['svg_file'] = file_path
                self.current_project['file_size'] = len(file_data)
                self.current_project['original_filename'] = filename
                self.current_project['uploaded_at'] = datetime.now().isoformat()
                self.current_project['svg_uploaded'] = True
                self.current_project['upload_progress'] = 100

                # Extract layer information from SVG
                self._extract_layers_from_svg(file_path)

                # Update status to ready
                self.current_project['status'] = ProjectStatus.READY.value
                logger.info(f"Project {self.current_project['id']} is ready for plotting")

                # Save state
                self._save_project_state()

                return self._get_project_info()

        except Exception as e:
            logger.error(f"Error uploading SVG: {str(e)}")
            if self.current_project:
                self.current_project['status'] = ProjectStatus.ERROR.value
                self.current_project['error_message'] = str(e)
                self._save_project_state()
            raise

    def upload_svg_chunked(self, chunk_data: bytes, chunk_info: Dict[str, Any]) -> Dict[str, Any]:
        """Handle chunked upload for large SVG files"""
        try:
            with self.project_lock:
                if not self.current_project:
                    raise Exception("No active project")

                # Update status if first chunk
                if chunk_info['chunk_number'] == 0:
                    self.current_project['status'] = ProjectStatus.UPLOADING.value

                # Create temp file for chunks
                temp_dir = os.path.join(self.current_project['project_dir'], 'temp')
                chunk_file_id = chunk_info.get('file_id', 'svg_upload')
                chunk_path = os.path.join(temp_dir, f"{chunk_file_id}_chunk_{chunk_info['chunk_number']}")

                # Save chunk
                with open(chunk_path, 'wb') as f:
                    f.write(chunk_data)

                # Update progress
                self.current_project['upload_progress'] = int((chunk_info['chunk_number'] + 1) / chunk_info['total_chunks'] * 100)

                # Check if all chunks received
                chunk_files = [f for f in os.listdir(temp_dir) if f.startswith(f"{chunk_file_id}_chunk_")]

                if len(chunk_files) == chunk_info['total_chunks']:
                    # Reassemble file
                    safe_filename = f"design_{hashlib.md5(chunk_info['filename'].encode()).hexdigest()[:8]}.svg"
                    final_path = os.path.join(self.current_project['project_dir'], safe_filename)

                    with open(final_path, 'wb') as final_file:
                        for i in range(chunk_info['total_chunks']):
                            chunk_path = os.path.join(temp_dir, f"{chunk_file_id}_chunk_{i}")
                            with open(chunk_path, 'rb') as chunk:
                                final_file.write(chunk.read())
                            # Remove chunk after reading
                            os.remove(chunk_path)

                    # Update project info
                    self.current_project['svg_file'] = final_path
                    self.current_project['file_size'] = os.path.getsize(final_path)
                    self.current_project['original_filename'] = chunk_info['filename']
                    self.current_project['uploaded_at'] = datetime.now().isoformat()
                    self.current_project['svg_uploaded'] = True
                    self.current_project['upload_progress'] = 100

                    # Extract layer information from SVG
                    self._extract_layers_from_svg(final_path)

                    # Update status to ready
                    self.current_project['status'] = ProjectStatus.READY.value
                    logger.info(f"Project {self.current_project['id']} is ready for plotting")

                # Save state
                self._save_project_state()

                return {
                    'status': self.current_project['status'],
                    'progress': self.current_project['upload_progress'],
                    'chunks_received': len(chunk_files),
                    'total_chunks': chunk_info['total_chunks']
                }

        except Exception as e:
            logger.error(f"Error handling chunked upload: {str(e)}")
            if self.current_project:
                self.current_project['status'] = ProjectStatus.ERROR.value
                self.current_project['error_message'] = str(e)
                self._save_project_state()
            raise

    def _extract_layers_from_svg(self, svg_path: str):
        """Extract layer information from the SVG file"""
        try:
            tree = ET.parse(svg_path)
            root = tree.getroot()

            # Define namespace
            ns = {'svg': 'http://www.w3.org/2000/svg',
                  'inkscape': 'http://www.inkscape.org/namespaces/inkscape'}

            layers = []

            # Look for Inkscape layers (groups with inkscape:groupmode="layer")
            for group in root.findall(".//svg:g[@inkscape:groupmode='layer']", ns):
                layer_name = group.get('{http://www.inkscape.org/namespaces/inkscape}label', '')
                layer_id = group.get('id', '')

                if layer_name:
                    layers.append({
                        'id': layer_id,
                        'name': layer_name
                    })

            # If no Inkscape layers found, look for regular groups
            if not layers:
                for i, group in enumerate(root.findall(".//svg:g", ns)):
                    layer_id = group.get('id', f'layer_{i}')
                    layer_name = group.get('inkscape:label', layer_id)

                    layers.append({
                        'id': layer_id,
                        'name': layer_name
                    })

            # If still no groups found, treat the entire SVG as one layer
            if not layers:
                layers.append({
                    'id': 'default',
                    'name': 'Default Layer'
                })

            self.current_project['available_layers'] = layers
            logger.info(f"Found {len(layers)} layers in SVG: {[l['name'] for l in layers]}")

        except Exception as e:
            logger.warning(f"Could not parse SVG layers: {str(e)}. Treating as single layer.")
            self.current_project['available_layers'] = [{
                'id': 'default',
                'name': 'Default Layer'
            }]

    def get_project_status(self) -> Optional[Dict[str, Any]]:
        """Get current project status"""
        with self.project_lock:
            if not self.current_project:
                return None
            return self._get_project_info()

    def is_project_ready(self) -> bool:
        """Check if current project is ready for plotting"""
        with self.project_lock:
            if not self.current_project:
                return False
            return self.current_project['status'] == ProjectStatus.READY.value

    def get_svg_file_path(self) -> Optional[str]:
        """Get the SVG file path for the current project"""
        with self.project_lock:
            if not self.current_project:
                return None
            return self.current_project.get('svg_file')

    def get_original_svg_file_name(self) -> Optional[str]:
        """Get the original SVG file name for the current project"""
        with self.project_lock:
            if not self.current_project:
                return None
            return self.current_project.get('original_svg_file_name')

    def get_available_layers(self) -> List[Dict[str, str]]:
        """Get list of available layers in the SVG"""
        with self.project_lock:
            if not self.current_project:
                return []
            return self.current_project.get('available_layers', [])

    def is_valid_layer(self, layer_name: str) -> bool:
        """Check if a layer name exists in the current project"""
        with self.project_lock:
            if not self.current_project:
                return False

            # Check if it's the special 'all' layer
            if layer_name == 'all':
                return True

            # Check if layer exists by name or id
            for layer in self.current_project.get('available_layers', []):
                if layer['name'] == layer_name or layer['id'] == layer_name:
                    return True
            return False

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
            'svg_uploaded': self.current_project['svg_uploaded'],
            'file_size': self.current_project['file_size'],
            'upload_progress': self.current_project['upload_progress'],
            'original_filename': self.current_project.get('original_filename'),
            'available_layers': self.current_project.get('available_layers', []),
            'metadata': self.current_project.get('metadata', {})
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
