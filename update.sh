#!/bin/bash
cd "$(dirname "$0")"
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
# Also update NextDraw library
pip install --upgrade https://software-download.bantamtools.com/nd/api/nextdraw_api.zip
sudo systemctl restart nextdraw-api
