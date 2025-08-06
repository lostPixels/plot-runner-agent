"""
SVG Manager for NextDraw Plotter API
Handles single SVG file management without projects
"""

import os
import json
import time
import shutil
import threading
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class SVGManager:
    """Manages single active SVG file with multiple layers"""

    def __init__(self, storage_dir='svg_storage'):
        self.storage_dir = storage_dir
        self.current_svg = None
        self.svg_lock = threading.RLock()

        # Create storage directory
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)

        # Clean up any temp directories on startup
        self._cleanup_temp_dirs()

    def upload_svg(self, file_data: bytes, filename: str) -> Dict[str, Any]:
        """Upload a new SVG file, replacing any existing one"""
        try:
            with self.svg_lock:
                # Clear existing SVG if any
                if self.current_svg:
                    self._clear_svg()

                # Create unique directory for this SVG
                svg_id = f"svg_{int(time.time())}_{hashlib.md5(filename.encode()).hexdigest()[:8]}"
                svg_dir = os.path.join(self.storage_dir, svg_id)
                os.makedirs(svg_dir)
                os.makedirs(os.path.join(svg_dir, 'temp'))

                # Save file
                safe_filename = f"design_{hashlib.md5(filename.encode()).hexdigest()[:8]}.svg"
                file_path = os.path.join(svg_dir, safe_filename)

                with open(file_path, 'wb') as f:
                    f.write(file_data)

                # Initialize SVG info
                self.current_svg = {
                    'id': svg_id,
                    'svg_file': file_path,
                    'file_size': len(file_data),
                    'original_filename': filename,
                    'uploaded_at': datetime.now().isoformat(),
                    'available_layers': [],
                    'svg_dir': svg_dir,
                    'upload_progress': 100
                }

                # Extract layer information from SVG
                self._extract_layers_from_svg(file_path)

                # Save state
                self._save_svg_state()

                logger.info(f"SVG uploaded successfully: {filename}")
                return self._get_svg_info()

        except Exception as e:
            logger.error(f"Error uploading SVG: {str(e)}")
            raise

    def upload_svg_chunked(self, chunk_data: bytes, chunk_info: Dict[str, Any]) -> Dict[str, Any]:
        """Handle chunked upload for large SVG files"""
        try:
            with self.svg_lock:
                # Create SVG directory on first chunk
                if chunk_info['chunk_number'] == 0:
                    # Clear existing SVG if any
                    if self.current_svg:
                        self._clear_svg()

                    # Create new SVG directory
                    svg_id = f"svg_{int(time.time())}_{hashlib.md5(chunk_info['filename'].encode()).hexdigest()[:8]}"
                    svg_dir = os.path.join(self.storage_dir, svg_id)
                    os.makedirs(svg_dir)
                    os.makedirs(os.path.join(svg_dir, 'temp'))

                    # Initialize SVG info
                    self.current_svg = {
                        'id': svg_id,
                        'svg_dir': svg_dir,
                        'original_filename': chunk_info['filename'],
                        'upload_progress': 0,
                        'uploading': True
                    }

                if not self.current_svg or not self.current_svg.get('uploading'):
                    raise Exception("No active upload session")

                # Create temp file for chunks
                temp_dir = os.path.join(self.current_svg['svg_dir'], 'temp')
                chunk_file_id = chunk_info.get('file_id', 'svg_upload')
                chunk_path = os.path.join(temp_dir, f"{chunk_file_id}_chunk_{chunk_info['chunk_number']}")

                # Save chunk
                with open(chunk_path, 'wb') as f:
                    f.write(chunk_data)

                # Update progress
                self.current_svg['upload_progress'] = int((chunk_info['chunk_number'] + 1) / chunk_info['total_chunks'] * 100)

                # Check if all chunks received
                chunk_files = [f for f in os.listdir(temp_dir) if f.startswith(f"{chunk_file_id}_chunk_")]

                if len(chunk_files) == chunk_info['total_chunks']:
                    # Reassemble file
                    safe_filename = f"design_{hashlib.md5(chunk_info['filename'].encode()).hexdigest()[:8]}.svg"
                    final_path = os.path.join(self.current_svg['svg_dir'], safe_filename)

                    with open(final_path, 'wb') as final_file:
                        for i in range(chunk_info['total_chunks']):
                            chunk_path = os.path.join(temp_dir, f"{chunk_file_id}_chunk_{i}")
                            with open(chunk_path, 'rb') as chunk:
                                final_file.write(chunk.read())
                            # Remove chunk after reading
                            os.remove(chunk_path)

                    # Update SVG info
                    self.current_svg['svg_file'] = final_path
                    self.current_svg['file_size'] = os.path.getsize(final_path)
                    self.current_svg['uploaded_at'] = datetime.now().isoformat()
                    self.current_svg['upload_progress'] = 100
                    self.current_svg['uploading'] = False
                    self.current_svg['available_layers'] = []

                    # Extract layer information from SVG
                    self._extract_layers_from_svg(final_path)

                # Save state
                self._save_svg_state()

                return {
                    'progress': self.current_svg['upload_progress'],
                    'chunks_received': len(chunk_files),
                    'total_chunks': chunk_info['total_chunks']
                }

        except Exception as e:
            logger.error(f"Error handling chunked upload: {str(e)}")
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

            self.current_svg['available_layers'] = layers
            logger.info(f"Found {len(layers)} layers in SVG: {[l['name'] for l in layers]}")

        except Exception as e:
            logger.warning(f"Could not parse SVG layers: {str(e)}. Treating as single layer.")
            self.current_svg['available_layers'] = [{
                'id': 'default',
                'name': 'Default Layer'
            }]

    def get_svg_status(self) -> Optional[Dict[str, Any]]:
        """Get current SVG status"""
        logger.debug("get_svg_status: Attempting to acquire lock")
        with self.svg_lock:
            logger.debug("get_svg_status: Lock acquired")
            if not self.current_svg:
                logger.debug("get_svg_status: No current SVG, returning None")
                return None
            result = self._get_svg_info()
            logger.debug("get_svg_status: Returning SVG info")
            return result

    def _is_svg_ready_internal(self) -> bool:
        """Internal check if SVG is ready for plotting (no lock)"""
        if not self.current_svg:
            return False
        return 'svg_file' in self.current_svg and not self.current_svg.get('uploading', False)

    def is_svg_ready(self) -> bool:
        """Check if SVG is ready for plotting"""
        logger.debug("is_svg_ready: Attempting to acquire lock")
        with self.svg_lock:
            logger.debug("is_svg_ready: Lock acquired")
            result = self._is_svg_ready_internal()
            logger.debug(f"is_svg_ready: Returning {result}")
            return result

    def get_svg_file_path(self) -> Optional[str]:
        """Get the SVG file path"""
        with self.svg_lock:
            if not self.current_svg:
                return None
            return self.current_svg.get('svg_file')

    def get_original_filename(self) -> Optional[str]:
        """Get the original filename of the current SVG"""
        with self.svg_lock:
            if not self.current_svg:
                return None
            return self.current_svg.get('original_filename')

    def get_available_layers(self) -> List[Dict[str, str]]:
        """Get list of available layers in the SVG"""
        with self.svg_lock:
            if not self.current_svg:
                return []
            return self.current_svg.get('available_layers', [])

    def is_valid_layer(self, layer_name: str) -> bool:
        """Check if a layer name exists in the current SVG"""
        with self.svg_lock:
            if not self.current_svg:
                return False

            # Check if it's the special 'all' layer
            if layer_name == 'all':
                return True

            # Check if layer exists by name or id
            for layer in self.current_svg.get('available_layers', []):
                if layer['name'] == layer_name or layer['id'] == layer_name:
                    return True
            return False

    def clear_svg(self) -> bool:
        """Clear current SVG from memory"""
        try:
            with self.svg_lock:
                if self.current_svg:
                    self._clear_svg()
                    return True
                return False
        except Exception as e:
            logger.error(f"Error clearing SVG: {str(e)}")
            return False

    def _clear_svg(self):
        """Internal method to clear SVG data and files"""
        if self.current_svg and 'svg_dir' in self.current_svg:
            svg_dir = self.current_svg['svg_dir']
            if os.path.exists(svg_dir):
                shutil.rmtree(svg_dir)
                logger.info(f"Removed SVG directory: {svg_dir}")

        self.current_svg = None

    def _save_svg_state(self):
        """Save current SVG state to disk"""
        if not self.current_svg:
            return

        state_file = os.path.join(self.current_svg['svg_dir'], 'svg_state.json')

        # Create a copy without the svg_dir path for serialization
        state_data = self.current_svg.copy()
        state_data.pop('svg_dir', None)

        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2)

    def _get_svg_info(self) -> Dict[str, Any]:
        """Get sanitized SVG information"""
        logger.debug("_get_svg_info: Building SVG info")
        if not self.current_svg:
            logger.debug("_get_svg_info: No current SVG")
            return None

        result = {
            'id': self.current_svg['id'],
            'file_size': self.current_svg.get('file_size', 0),
            'upload_progress': self.current_svg.get('upload_progress', 0),
            'original_filename': self.current_svg.get('original_filename'),
            'uploaded_at': self.current_svg.get('uploaded_at'),
            'available_layers': self.current_svg.get('available_layers', []),
            'is_ready': self._is_svg_ready_internal()
        }
        logger.debug(f"_get_svg_info: Returning info for SVG {result.get('original_filename', 'unknown')}")
        return result

    def _cleanup_temp_dirs(self):
        """Clean up temporary directories on startup"""
        try:
            for svg_dir in os.listdir(self.storage_dir):
                temp_dir = os.path.join(self.storage_dir, svg_dir, 'temp')
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning temp directories: {str(e)}")
