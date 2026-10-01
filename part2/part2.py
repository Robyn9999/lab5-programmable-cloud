#!/usr/bin/env python3

import argparse
import os
import time
from pprint import pprint

import googleapiclient.discovery
import google.auth


# Authenticate
credentials, project = google.auth.default()

# Create Compute Engine API service
service = googleapiclient.discovery.build(
    "compute",
    "v1",
    credentials=credentials
)


def list_instances(compute, project, zone):
    """List all instances in the specified zone."""
    result = (
        compute.instances()
        .list(project=project, zone=zone)
        .execute()
    )

    return result["items"] if "items" in result else []


def get_instance(compute, project, zone, instance_name):
    """Get a specific instance."""
    return (
        compute.instances()
        .get(
            project=project,
            zone=zone,
            instance=instance_name,
        )
        .execute()
    )


def get_boot_disk(instance):
    """Find the boot disk attached to an instance."""
    for disk in instance.get("disks", []):
        if disk.get("boot"):
            return disk

    raise RuntimeError(
        f"No boot disk found for instance {instance['name']}"
    )


def wait_for_zone_operation(compute, project, zone, operation):
    """Wait for a zonal Compute Engine operation to finish."""

    print(f"Waiting for operation {operation['name']}...")

    while True:
        result = (
            compute.zoneOperations()
            .get(
                project=project,
                zone=zone,
                operation=operation["name"],
            )
            .execute()
        )

        if result["status"] == "DONE":
            if "error" in result:
                raise RuntimeError(
                    f"Operation failed: {result['error']}"
                )

            return result

        time.sleep(1)


def create_snapshot(
    compute,
    project,
    zone,
    disk_name,
    snapshot_name,
):
    """Create a snapshot from a zonal disk."""

    print(
        f"Creating snapshot '{snapshot_name}' "
        f"from disk '{disk_name}'..."
    )

    operation = (
        compute.disks()
        .createSnapshot(
            project=project,
            zone=zone,
            disk=disk_name,
            body={
                "name": snapshot_name
            },
        )
        .execute()
    )

    wait_for_zone_operation(
        compute,
        project,
        zone,
        operation,
    )

    print(f"Snapshot '{snapshot_name}' created.")


def create_disk_from_snapshot(
    compute,
    project,
    zone,
    disk_name,
    snapshot_name,
):
    """Create a new disk from the snapshot."""

    print(
        f"Creating disk '{disk_name}' "
        f"from snapshot '{snapshot_name}'..."
    )

    disk_body = {
        "name": disk_name,
        "sizeGb": 10,
        "type": (
            f"zones/{zone}/diskTypes/pd-standard"
        ),
        "sourceSnapshot": (
            f"projects/{project}/global/snapshots/"
            f"{snapshot_name}"
        ),
    }

    operation = (
        compute.disks()
        .insert(
            project=project,
            zone=zone,
            body=disk_body,
        )
        .execute()
    )

    wait_for_zone_operation(
        compute,
        project,
        zone,
        operation,
    )

    print(f"Disk '{disk_name}' created.")


def create_instance_from_disk(
    compute,
    project,
    zone,
    instance_name,
    disk_name,
):
    """Create a VM using the specified boot disk."""

    instance_body = {
        "name": instance_name,

        "machineType": (
            f"zones/{zone}/machineTypes/f1-micro"
        ),

        "disks": [
            {
                "boot": True,
                "autoDelete": True,
                "source": (
                    f"zones/{zone}/disks/{disk_name}"
                ),
            }
        ],

        "networkInterfaces": [
            {
                "network": "global/networks/default",

                # Give the clone its own external IP
                "accessConfigs": [
                    {
                        "type": "ONE_TO_ONE_NAT",
                        "name": "External NAT",
                        "networkTier": "PREMIUM",
                    }
                ],
            }
        ],

        # Required for the Flask firewall rule
        "tags": {
            "items": ["allow-5000"]
        },
    }

    print(f"Creating instance '{instance_name}'...")

    start_time = time.perf_counter()

    operation = (
        compute.instances()
        .insert(
            project=project,
            zone=zone,
            body=instance_body,
        )
        .execute()
    )

    wait_for_zone_operation(
        compute,
        project,
        zone,
        operation,
    )

    elapsed = time.perf_counter() - start_time

    print(
        f"Instance '{instance_name}' "
        f"created in {elapsed:.2f} seconds."
    )

    return elapsed


def get_external_ip(instance):
    """Get the external IP address of an instance."""

    network_interfaces = instance.get(
        "networkInterfaces", []
    )

    if not network_interfaces:
        return None

    access_configs = network_interfaces[0].get(
        "accessConfigs", []
    )

    if not access_configs:
        return None

    return access_configs[0].get("natIP")


def main():
    zone = "us-west2-a"

    print("Your running instances are:")

    instances = list_instances(
        service,
        project,
        zone,
    )

    for instance in instances:
        print(
            f"  {instance['name']} "
            f"({instance.get('status', 'UNKNOWN')})"
        )

    print()

    # Ask for the Part One instance
    instance_name = "quickstart-60bf196a93"

    # Get the original instance
    original_instance = get_instance(
        service,
        project,
        zone,
        instance_name,
    )

    # Find its boot disk
    boot_disk = get_boot_disk(original_instance)

    disk_source = boot_disk["source"]
    original_disk_name = disk_source.split("/")[-1]

    print(
        f"\nOriginal boot disk: "
        f"{original_disk_name}"
    )

    # Snapshot name required by assignment
    snapshot_name = (
        f"base-snapshot-{instance_name}"
    )

    # Create snapshot
    create_snapshot(
        service,
        project,
        zone,
        original_disk_name,
        snapshot_name,
    )

    print()

    # Create three clones
    timings = []

    for i in range(1, 4):

        clone_disk_name = (
            f"{instance_name}-clon-disk-{i}"
        )

        clone_instance_name = (
            f"{instance_name}-clon-{i}"
        )

        print("=" * 60)
        print(f"Creating clone {i}")
        print("=" * 60)

        # Create disk from snapshot
        create_disk_from_snapshot(
            service,
            project,
            zone,
            clone_disk_name,
            snapshot_name,
        )

        # Create VM from the new disk
        elapsed = create_instance_from_disk(
            service,
            project,
            zone,
            clone_instance_name,
            clone_disk_name,
        )

        # Retrieve the newly created VM
        clone_instance = get_instance(
            service,
            project,
            zone,
            clone_instance_name,
        )

        # Get external IP
        external_ip = get_external_ip(
            clone_instance
        )

        timings.append(
            (
                clone_instance_name,
                elapsed,
                external_ip,
            )
        )

        print(
            f"External IP: "
            f"{external_ip}"
        )

        if external_ip:
            print(
                f"Flask URL: "
                f"http://{external_ip}:5000"
            )

        print()

    # Print final results
    print("\n" + "=" * 60)
    print("CLONE CREATION RESULTS")
    print("=" * 60)

    for name, elapsed, external_ip in timings:
        print(
            f"{name}: "
            f"{elapsed:.2f} seconds"
        )

        if external_ip:
            print(
                f"  External IP: {external_ip}"
            )
            print(
                f"  Flask URL: "
                f"http://{external_ip}:5000"
            )

    print("\nTIMING.md values:")

    for name, elapsed, _ in timings:
        print(
            f"- {name}: {elapsed:.2f} seconds"
        )


if __name__ == "__main__":
    main()