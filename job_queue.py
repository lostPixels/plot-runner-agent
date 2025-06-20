"""
Job Queue Manager for NextDraw Plotter API
Handles queuing, tracking, and managing plot jobs.
"""

import json
import os
import time
import uuid
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class JobQueue:
    """Manages plot job queue and job lifecycle"""
    
    def __init__(self, queue_file='job_queue.json'):
        self.queue_file = queue_file
        self.jobs = {}
        self.queue = []  # Job IDs in order
        self.lock = threading.Lock()
        self.max_queue_size = 100
        self.load_queue()
    
    def load_queue(self):
        """Load job queue from file"""
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                    self.jobs = data.get('jobs', {})
                    self.queue = data.get('queue', [])
                logger.info(f"Job queue loaded from {self.queue_file}")
            else:
                logger.info("No existing job queue file found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading job queue: {str(e)}")
            self.jobs = {}
            self.queue = []
    
    def save_queue(self):
        """Save job queue to file"""
        try:
            data = {
                'jobs': self.jobs,
                'queue': self.queue,
                'last_updated': datetime.now().isoformat()
            }
            
            # Create backup
            if os.path.exists(self.queue_file):
                backup_file = f"{self.queue_file}.backup"
                os.rename(self.queue_file, backup_file)
            
            with open(self.queue_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug("Job queue saved")
            
        except Exception as e:
            logger.error(f"Error saving job queue: {str(e)}")
            # Restore backup if save failed
            backup_file = f"{self.queue_file}.backup"
            if os.path.exists(backup_file):
                os.rename(backup_file, self.queue_file)
    
    def add_job(self, job_data: Dict[str, Any]) -> str:
        """Add a new job to the queue"""
        try:
            with self.lock:
                # Check queue size limit
                if len(self.queue) >= self.max_queue_size:
                    raise Exception(f"Queue is full (max {self.max_queue_size} jobs)")
                
                # Generate unique job ID
                job_id = str(uuid.uuid4())
                
                # Create job record
                job = {
                    'id': job_id,
                    'name': job_data.get('name', f'Job_{int(time.time())}'),
                    'description': job_data.get('description', ''),
                    'svg_content': job_data.get('svg_content'),
                    'svg_file': job_data.get('svg_file'),
                    'config_overrides': job_data.get('config_overrides', {}),
                    'priority': job_data.get('priority', 1),
                    'status': 'queued',
                    'submitted_at': job_data.get('submitted_at', datetime.now().isoformat()),
                    'started_at': None,
                    'completed_at': None,
                    'error_message': None,
                    'result': None,
                    'progress': 0
                }
                
                # Add to jobs dict and queue
                self.jobs[job_id] = job
                
                # Insert based on priority (higher priority first)
                inserted = False
                for i, existing_job_id in enumerate(self.queue):
                    existing_job = self.jobs.get(existing_job_id, {})
                    if job['priority'] > existing_job.get('priority', 1):
                        self.queue.insert(i, job_id)
                        inserted = True
                        break
                
                if not inserted:
                    self.queue.append(job_id)
                
                # Save queue
                self.save_queue()
                
                logger.info(f"Job {job_id} ({job['name']}) added to queue at position {self.get_position(job_id)}")
                return job_id
                
        except Exception as e:
            logger.error(f"Error adding job: {str(e)}")
            raise
    
    def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get the next job to process"""
        try:
            with self.lock:
                for job_id in self.queue[:]:
                    job = self.jobs.get(job_id)
                    if job and job['status'] == 'queued':
                        job['status'] = 'running'
                        job['started_at'] = datetime.now().isoformat()
                        self.save_queue()
                        logger.info(f"Job {job_id} started")
                        return job
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting next job: {str(e)}")
            return None
    
    def complete_job(self, job_id: str, result: Dict[str, Any]):
        """Mark a job as completed"""
        try:
            with self.lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    job['status'] = 'completed'
                    job['completed_at'] = datetime.now().isoformat()
                    job['result'] = result
                    job['progress'] = 100
                    
                    # Remove from active queue
                    if job_id in self.queue:
                        self.queue.remove(job_id)
                    
                    self.save_queue()
                    logger.info(f"Job {job_id} completed successfully")
                
        except Exception as e:
            logger.error(f"Error completing job {job_id}: {str(e)}")
    
    def fail_job(self, job_id: str, error_message: str):
        """Mark a job as failed"""
        try:
            with self.lock:
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    job['status'] = 'failed'
                    job['completed_at'] = datetime.now().isoformat()
                    job['error_message'] = error_message
                    
                    # Remove from active queue
                    if job_id in self.queue:
                        self.queue.remove(job_id)
                    
                    self.save_queue()
                    logger.error(f"Job {job_id} failed: {error_message}")
                
        except Exception as e:
            logger.error(f"Error failing job {job_id}: {str(e)}")
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        try:
            with self.lock:
                if job_id not in self.jobs:
                    return False
                
                job = self.jobs[job_id]
                
                # Can only cancel queued jobs
                if job['status'] != 'queued':
                    return False
                
                job['status'] = 'cancelled'
                job['completed_at'] = datetime.now().isoformat()
                
                # Remove from queue
                if job_id in self.queue:
                    self.queue.remove(job_id)
                
                self.save_queue()
                logger.info(f"Job {job_id} cancelled")
                return True
                
        except Exception as e:
            logger.error(f"Error cancelling job {job_id}: {str(e)}")
            return False
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID"""
        return self.jobs.get(job_id)
    
    def get_all_jobs(self) -> Dict[str, Any]:
        """Get all jobs with queue information"""
        try:
            with self.lock:
                # Get queued jobs in order
                queued_jobs = []
                for job_id in self.queue:
                    if job_id in self.jobs:
                        job = self.jobs[job_id].copy()
                        job['queue_position'] = self.queue.index(job_id) + 1
                        queued_jobs.append(job)
                
                # Get completed/failed jobs (last 50)
                completed_jobs = []
                for job in self.jobs.values():
                    if job['status'] in ['completed', 'failed', 'cancelled']:
                        completed_jobs.append(job)
                
                # Sort completed jobs by completion time (newest first)
                completed_jobs.sort(
                    key=lambda x: x.get('completed_at', ''),
                    reverse=True
                )
                completed_jobs = completed_jobs[:50]
                
                return {
                    'queued_jobs': queued_jobs,
                    'completed_jobs': completed_jobs,
                    'queue_length': len(self.queue),
                    'total_jobs': len(self.jobs)
                }
                
        except Exception as e:
            logger.error(f"Error getting all jobs: {str(e)}")
            return {'queued_jobs': [], 'completed_jobs': [], 'queue_length': 0, 'total_jobs': 0}
    
    def get_position(self, job_id: str) -> int:
        """Get position of job in queue (1-based)"""
        try:
            if job_id in self.queue:
                return self.queue.index(job_id) + 1
            return -1
        except:
            return -1
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue status summary"""
        try:
            with self.lock:
                queued_count = len([j for j in self.jobs.values() if j['status'] == 'queued'])
                running_count = len([j for j in self.jobs.values() if j['status'] == 'running'])
                completed_count = len([j for j in self.jobs.values() if j['status'] == 'completed'])
                failed_count = len([j for j in self.jobs.values() if j['status'] == 'failed'])
                cancelled_count = len([j for j in self.jobs.values() if j['status'] == 'cancelled'])
                
                return {
                    'queue_length': len(self.queue),
                    'total_jobs': len(self.jobs),
                    'status_counts': {
                        'queued': queued_count,
                        'running': running_count,
                        'completed': completed_count,
                        'failed': failed_count,
                        'cancelled': cancelled_count
                    },
                    'next_job': self.queue[0] if self.queue else None
                }
                
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {
                'queue_length': 0,
                'total_jobs': 0,
                'status_counts': {
                    'queued': 0,
                    'running': 0,
                    'completed': 0,
                    'failed': 0,
                    'cancelled': 0
                },
                'next_job': None
            }
    
    def cleanup_old_jobs(self, max_age_days: int = 7):
        """Clean up old completed/failed jobs"""
        try:
            with self.lock:
                current_time = datetime.now()
                jobs_to_remove = []
                
                for job_id, job in self.jobs.items():
                    if job['status'] in ['completed', 'failed', 'cancelled']:
                        completed_at = job.get('completed_at')
                        if completed_at:
                            job_time = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                            age_days = (current_time - job_time).days
                            
                            if age_days > max_age_days:
                                jobs_to_remove.append(job_id)
                
                # Remove old jobs
                for job_id in jobs_to_remove:
                    del self.jobs[job_id]
                    if job_id in self.queue:
                        self.queue.remove(job_id)
                
                if jobs_to_remove:
                    self.save_queue()
                    logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")
                
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {str(e)}")
    
    def clear_queue(self):
        """Clear all queued jobs (not running/completed)"""
        try:
            with self.lock:
                jobs_to_remove = []
                
                for job_id in self.queue[:]:
                    job = self.jobs.get(job_id)
                    if job and job['status'] == 'queued':
                        jobs_to_remove.append(job_id)
                
                for job_id in jobs_to_remove:
                    self.jobs[job_id]['status'] = 'cancelled'
                    self.jobs[job_id]['completed_at'] = datetime.now().isoformat()
                    self.queue.remove(job_id)
                
                self.save_queue()
                logger.info(f"Cleared {len(jobs_to_remove)} queued jobs")
                
        except Exception as e:
            logger.error(f"Error clearing queue: {str(e)}")
    
    def reorder_job(self, job_id: str, new_position: int) -> bool:
        """Reorder a job in the queue"""
        try:
            with self.lock:
                if job_id not in self.queue:
                    return False
                
                job = self.jobs.get(job_id)
                if not job or job['status'] != 'queued':
                    return False
                
                # Remove job from current position
                self.queue.remove(job_id)
                
                # Insert at new position (1-based)
                new_index = max(0, min(new_position - 1, len(self.queue)))
                self.queue.insert(new_index, job_id)
                
                self.save_queue()
                logger.info(f"Job {job_id} moved to position {new_position}")
                return True
                
        except Exception as e:
            logger.error(f"Error reordering job {job_id}: {str(e)}")
            return False
    
    def update_job_progress(self, job_id: str, progress: int):
        """Update job progress (0-100)"""
        try:
            with self.lock:
                if job_id in self.jobs:
                    self.jobs[job_id]['progress'] = max(0, min(100, progress))
                    # Don't save for every progress update to avoid excessive I/O
                    
        except Exception as e:
            logger.error(f"Error updating job progress {job_id}: {str(e)}")