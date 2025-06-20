"""
WSGI configuration for NextDraw Plotter API
Production-ready WSGI entry point for Gunicorn
"""

import os
import sys
import logging
from pathlib import Path

# Add the application directory to the Python path
app_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(app_dir))

# Set up logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(app_dir / 'logs' / 'gunicorn.log')
    ]
)

# Import the Flask application
from app import app as application

if __name__ == "__main__":
    application.run()