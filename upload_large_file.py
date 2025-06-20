#!/usr/bin/env python3
"""
Large File Upload Utility for NextDraw Plotter API
Handles chunked uploads for very large SVG files (100MB+)
"""

import os
import sys
import json
import time
import hashlib
import requests
from pathlib import Path
import argparse
from typing import Optional, Dict, Any

class LargeFileUploader:
    def __init__(self, base_url: str = "http://localhost", chunk_size: int = 5 * 1024 * 1024):
        """
        Initialize the uploader
        
        Args:
            base_url: Base URL of the NextDraw API
            chunk_size: Size of each chunk in bytes (default 5MB)
        """
        self.base_url = base_url.rstrip('/')
        self.chunk_size = chunk_size
        self.session = requests.Session()
        
        # Set session timeouts
        self.session.timeout = (30, 300)  # (connect, read) timeouts
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file for integrity checking"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def upload_small_file(self, file_path: str, job_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload file using standard multipart upload (< 100MB)
        
        Args:
            file_path: Path to the SVG file
            job_config: Job configuration dictionary
            
        Returns:
            API response dictionary
        """
        print(f"Uploading file via standard multipart upload...")
        
        with open(file_path, 'rb') as f:
            files = {'svg_file': (os.path.basename(file_path), f, 'image/svg+xml')}
            data = {
                'name': job_config.get('name', os.path.basename(file_path)),
                'description': job_config.get('description', ''),
                'config': json.dumps(job_config.get('config', {})),
                'priority': str(job_config.get('priority', 1))
            }
            
            response = self.session.post(
                f"{self.base_url}/plot/upload",
                files=files,
                data=data
            )
            
        return response.json() if response.status_code in [200, 201] else {
            "error": f"HTTP {response.status_code}: {response.text}"
        }
    
    def upload_chunked_file(self, file_path: str, job_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload large file using chunked upload
        
        Args:
            file_path: Path to the SVG file
            job_config: Job configuration dictionary
            
        Returns:
            API response dictionary
        """
        file_size = os.path.getsize(file_path)
        total_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        file_id = hashlib.md5(f"{file_path}{time.time()}".encode()).hexdigest()
        
        print(f"Uploading file via chunked upload...")
        print(f"File size: {file_size:,} bytes")
        print(f"Chunk size: {self.chunk_size:,} bytes")
        print(f"Total chunks: {total_chunks}")
        print(f"File ID: {file_id}")
        
        try:
            with open(file_path, 'rb') as f:
                for chunk_num in range(total_chunks):
                    # Read chunk
                    chunk_data = f.read(self.chunk_size)
                    if not chunk_data:
                        break
                    
                    # Prepare form data
                    files = {'chunk_data': (f'chunk_{chunk_num}', chunk_data, 'application/octet-stream')}
                    data = {
                        'chunk': str(chunk_num),
                        'total_chunks': str(total_chunks),
                        'file_id': file_id,
                        'filename': os.path.basename(file_path)
                    }
                    
                    # Add job config to last chunk
                    if chunk_num == total_chunks - 1:
                        data.update({
                            'name': job_config.get('name', os.path.basename(file_path)),
                            'description': job_config.get('description', ''),
                            'config': json.dumps(job_config.get('config', {})),
                            'priority': str(job_config.get('priority', 1))
                        })
                    
                    # Upload chunk with retry logic
                    for attempt in range(3):
                        try:
                            response = self.session.post(
                                f"{self.base_url}/plot/chunk",
                                files=files,
                                data=data,
                                timeout=(30, 120)
                            )
                            
                            if response.status_code in [200, 201]:
                                result = response.json()
                                
                                # Progress indicator
                                progress = (chunk_num + 1) / total_chunks * 100
                                print(f"\rProgress: {progress:.1f}% ({chunk_num + 1}/{total_chunks})", end='', flush=True)
                                
                                # If this was the last chunk, return the final result
                                if chunk_num == total_chunks - 1:
                                    print()  # New line after progress
                                    return result
                                
                                break  # Success, move to next chunk
                            else:
                                if attempt == 2:  # Last attempt
                                    return {"error": f"Chunk {chunk_num} failed: HTTP {response.status_code}"}
                                time.sleep(2 ** attempt)  # Exponential backoff
                                
                        except requests.exceptions.RequestException as e:
                            if attempt == 2:  # Last attempt
                                return {"error": f"Chunk {chunk_num} failed: {str(e)}"}
                            time.sleep(2 ** attempt)  # Exponential backoff
            
            print()  # New line after progress
            return {"error": "Upload completed but no final response received"}
            
        except Exception as e:
            return {"error": f"Upload failed: {str(e)}"}
    
    def upload_file(self, file_path: str, job_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Upload file using the most appropriate method based on file size
        
        Args:
            file_path: Path to the SVG file
            job_config: Optional job configuration
            
        Returns:
            API response dictionary
        """
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
        
        if not file_path.lower().endswith('.svg'):
            return {"error": "Only SVG files are supported"}
        
        # Default job config
        if job_config is None:
            job_config = {}
        
        # Set default name if not provided
        if 'name' not in job_config:
            job_config['name'] = Path(file_path).stem
        
        file_size = os.path.getsize(file_path)
        print(f"File: {file_path}")
        print(f"Size: {file_size:,} bytes ({file_size / (1024*1024):.1f} MB)")
        
        # Choose upload method based on file size
        if file_size < 100 * 1024 * 1024:  # < 100MB
            return self.upload_small_file(file_path, job_config)
        else:
            return self.upload_chunked_file(file_path, job_config)
    
    def check_api_health(self) -> bool:
        """Check if the API is accessible"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def get_upload_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of uploaded job"""
        try:
            response = self.session.get(f"{self.base_url}/jobs/{job_id}")
            return response.json() if response.status_code == 200 else {"error": "Job not found"}
        except Exception as e:
            return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Upload large SVG files to NextDraw Plotter API")
    parser.add_argument("file_path", help="Path to the SVG file to upload")
    parser.add_argument("--url", default="http://localhost", help="Base URL of the NextDraw API")
    parser.add_argument("--name", help="Job name (defaults to filename)")
    parser.add_argument("--description", default="", help="Job description")
    parser.add_argument("--priority", type=int, default=1, help="Job priority (1-10)")
    parser.add_argument("--chunk-size", type=int, default=5, help="Chunk size in MB for large files")
    parser.add_argument("--speed-pendown", type=int, help="Pen down speed (1-100)")
    parser.add_argument("--speed-penup", type=int, help="Pen up speed (1-100)")
    parser.add_argument("--pen-pos-down", type=int, help="Pen down position (0-100)")
    parser.add_argument("--pen-pos-up", type=int, help="Pen up position (0-100)")
    parser.add_argument("--dry-run", action="store_true", help="Validate file but don't upload")
    
    args = parser.parse_args()
    
    # Validate file
    if not os.path.exists(args.file_path):
        print(f"Error: File not found: {args.file_path}")
        sys.exit(1)
    
    if not args.file_path.lower().endswith('.svg'):
        print("Error: Only SVG files are supported")
        sys.exit(1)
    
    # Build job config
    job_config = {
        "name": args.name or Path(args.file_path).stem,
        "description": args.description,
        "priority": args.priority,
        "config": {}
    }
    
    # Add plotter config if specified
    if args.speed_pendown is not None:
        job_config["config"]["speed_pendown"] = args.speed_pendown
    if args.speed_penup is not None:
        job_config["config"]["speed_penup"] = args.speed_penup
    if args.pen_pos_down is not None:
        job_config["config"]["pen_pos_down"] = args.pen_pos_down
    if args.pen_pos_up is not None:
        job_config["config"]["pen_pos_up"] = args.pen_pos_up
    
    # Create uploader
    uploader = LargeFileUploader(
        base_url=args.url,
        chunk_size=args.chunk_size * 1024 * 1024
    )
    
    if args.dry_run:
        file_size = os.path.getsize(args.file_path)
        print(f"Dry run mode - file validation:")
        print(f"  File: {args.file_path}")
        print(f"  Size: {file_size:,} bytes ({file_size / (1024*1024):.1f} MB)")
        print(f"  Upload method: {'Chunked' if file_size >= 100*1024*1024 else 'Standard'}")
        print(f"  Job config: {json.dumps(job_config, indent=2)}")
        sys.exit(0)
    
    # Check API health
    print("Checking API connection...")
    if not uploader.check_api_health():
        print(f"Error: Cannot connect to API at {args.url}")
        print("Make sure the NextDraw API server is running and accessible.")
        sys.exit(1)
    
    print("API connection OK")
    print()
    
    # Upload file
    print("Starting upload...")
    start_time = time.time()
    
    result = uploader.upload_file(args.file_path, job_config)
    
    upload_time = time.time() - start_time
    
    # Display result
    if "error" in result:
        print(f"Upload failed: {result['error']}")
        sys.exit(1)
    else:
        print(f"Upload successful!")
        print(f"Upload time: {upload_time:.1f} seconds")
        print(f"Job ID: {result.get('job_id', 'Unknown')}")
        print(f"Queue position: {result.get('position', 'Unknown')}")
        
        if 'file_size' in result:
            file_size = result['file_size']
            rate = file_size / upload_time / (1024 * 1024)  # MB/s
            print(f"Upload rate: {rate:.1f} MB/s")
        
        # Monitor job status for a few seconds
        job_id = result.get('job_id')
        if job_id:
            print("\nMonitoring job status...")
            for i in range(10):
                time.sleep(2)
                status = uploader.get_upload_status(job_id)
                if "error" not in status:
                    job_status = status.get('status', 'unknown')
                    print(f"Job status: {job_status}")
                    if job_status in ['running', 'completed', 'failed']:
                        break
                else:
                    break

if __name__ == "__main__":
    main()