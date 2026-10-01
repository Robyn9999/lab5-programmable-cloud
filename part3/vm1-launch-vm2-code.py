#!/usr/bin/env python3
import os, time, uuid
import googleapiclient.discovery
import google.oauth2.service_account as service_account

# Read local service credentials and project
creds = service_account.Credentials.from_service_account_file(
    "service-credentials.json",
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
project = os.getenv("GOOGLE_CLOUD_PROJECT") or creds.project_id
compute = googleapiclient.discovery.build("compute", "v1", credentials=creds)
zone = "us-west1-b"

# Dynamic image lookup
img = compute.images().getFromFamily(project="ubuntu-os-cloud", family="ubuntu-2204-lts").execute()
flask_startup = open("vm2-startup-script.sh").read()

vm2_name = f"flask-vm-{uuid.uuid4().hex[:8]}"
config = {
    "name": vm2_name,
    "machineType": f"zones/{zone}/machineTypes/f1-micro",
    "disks": [{
        "boot": True,
        "autoDelete": True,
        "initializeParams": {"sourceImage": img["selfLink"], "diskSizeGb": "10"}
    }],
    "networkInterfaces": [{
        "network": "global/networks/default",
        "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}]
    }],
    "metadata": {
        "items": [{"key": "startup-script", "value": flask_startup}]
    }
}

print(f"VM-1 launching VM-2 ({vm2_name})...")
op = compute.instances().insert(project=project, zone=zone, body=config).execute()

while True:
    res = compute.zoneOperations().get(project=project, zone=zone, operation=op["name"]).execute()
    if res.get("status") == "DONE":
        break
    time.sleep(2)

vm2 = compute.instances().get(project=project, zone=zone, instance=vm2_name).execute()
ip = vm2["networkInterfaces"][0]["accessConfigs"][0].get("natIP")
print(f"VM-2 ready! Public URL: http://{ip}:5000")