#!/bin/bash
cd "$(dirname "$0")"
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
# Also update NextDraw library
pip install --upgrade https://software-download.bantamtools.com/nd/1_7_3/nd_api_173.zip
sudo systemctl restart nextdraw-api
