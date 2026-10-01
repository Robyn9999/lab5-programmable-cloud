#!/usr/bin/env python3
import os, sys, time, uuid
import googleapiclient.discovery
import google.oauth2.service_account as service_account

CRED_FILE = "service-credentials.json"
if not os.path.exists(CRED_FILE):
    sys.exit(f"Missing {CRED_FILE}")

# Authenticate from laptop
creds = service_account.Credentials.from_service_account_file(
    CRED_FILE, scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
project = os.getenv("GOOGLE_CLOUD_PROJECT") or creds.project_id
compute = googleapiclient.discovery.build("compute", "v1", credentials=creds)

# Use us-west2-a as specified in your lab instructions
zone = "us-west2-a"

# Load newest Ubuntu image
img = compute.images().getFromFamily(project="ubuntu-os-cloud", family="ubuntu-2204-lts").execute()

# Pack the payload files into instance metadata
metadata_files = {
    "vm2-startup-script": "vm2-startup-script.sh",
    "service-credentials": CRED_FILE,
    "vm1-launch-vm2-code": "vm1-launch-vm2-code.py",
}
metadata_items = [{"key": k, "value": open(v).read()} for k, v in metadata_files.items()]
metadata_items.append({"key": "project", "value": project})

# VM-1 bootstrap shell script
metadata_items.append({
    "key": "startup-script",
    "value": """#!/bin/bash
mkdir -p /srv && cd /srv
curl -s http://metadata/computeMetadata/v1/instance/attributes/vm2-startup-script -H "Metadata-Flavor: Google" > vm2-startup-script.sh
curl -s http://metadata/computeMetadata/v1/instance/attributes/service-credentials -H "Metadata-Flavor: Google" > service-credentials.json
curl -s http://metadata/computeMetadata/v1/instance/attributes/vm1-launch-vm2-code -H "Metadata-Flavor: Google" > vm1-launch-vm2-code.py
export GOOGLE_CLOUD_PROJECT=$(curl -s http://metadata/computeMetadata/v1/instance/attributes/project -H "Metadata-Flavor: Google")
chmod 600 service-credentials.json

apt-get update && apt-get install -y python3-pip
pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib --break-system-packages || pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
python3 ./vm1-launch-vm2-code.py > /var/log/vm1-launcher.log 2>&1
"""
})

# Define VM-1 using e2-micro to avoid f1-micro stock exhaustion
vm1_name = f"vm1-launcher-{uuid.uuid4().hex[:8]}"
config = {
    "name": vm1_name,
    "machineType": f"zones/{zone}/machineTypes/e2-micro",
    "disks": [{
        "boot": True,
        "autoDelete": True,
        "initializeParams": {"sourceImage": img["selfLink"], "diskSizeGb": "10"}
    }],
    "networkInterfaces": [{
        "network": "global/networks/default",
        "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}]
    }],
    "metadata": {"items": metadata_items}
}

print(f"Creating {vm1_name} in {zone}...")
op = compute.instances().insert(project=project, zone=zone, body=config).execute()

# Poll operation and verify completion
while True:
    res = compute.zoneOperations().get(project=project, zone=zone, operation=op["name"]).execute()
    if res.get("status") == "DONE":
        if "error" in res:
            raise RuntimeError(f"VM creation failed: {res['error']}")
        break
    time.sleep(2)

# Retrieve instance details
vm1 = compute.instances().get(project=project, zone=zone, instance=vm1_name).execute()
ip = vm1["networkInterfaces"][0]["accessConfigs"][0].get("natIP")
print(f"VM-1 running at {ip}. Check /var/log/vm1-launcher.log on VM-1 to watch VM-2 spawn.")