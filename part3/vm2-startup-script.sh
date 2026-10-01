#!/bin/bash
set -e

# Update package lists and install required dependencies
apt-get update
apt-get install -y python3 python3-pip git

# Navigate to a system directory and clone the tutorial repository
cd /opt
if [ ! -d "flask-tutorial" ]; then
    git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
fi
cd flask-tutorial

# Handle PEP 668 externally managed environment restrictions if running Ubuntu 23.04+ / 24.04+
python3 setup.py install || pip3 install --break-system-packages -e . || pip3 install -e .

# Set Flask environment variable and initialize the database
export FLASK_APP=flaskr
flask init-db

# Run the Flask app in the background listening on all interfaces (port 5000)
nohup flask run -h 0.0.0.0 --port 5000 > /var/log/flask.log 2>&1 &