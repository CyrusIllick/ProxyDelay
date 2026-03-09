"""Google Compute Engine lifecycle helpers used by real-world orchestration."""

import logging as log
import time

from googleapiclient import discovery
from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError

import real_world_helper
from config_loader import get_cloud_config
from real_world_helper import get_external_ip_address, run_date_command

CLOUD = get_cloud_config()
GCP_CFG = CLOUD["gcp"]

PROJECT = GCP_CFG.get("project_id", "")
GCP_IMAGE_NAME = GCP_CFG.get("image_name", "")
MACHINE_TYPE = GCP_CFG.get("machine_type", "e2-medium")

if PROJECT == "" or GCP_IMAGE_NAME == "":
    raise ValueError("GCP project_id and image_name must be set in config/cloud.json")

compute = discovery.build("compute", "v1")


def start_host_instance(zone_name, instance_name):
    """Start an existing GCE instance and wait until RUNNING."""
    compute.instances().start(
        project=PROJECT,
        zone=zone_name,
        instance=instance_name,
    ).execute()

    inst_status = None
    while inst_status != "RUNNING":
        inst_status = get_instance_status(zone_name, instance_name)
        print(f"{instance_name} status: {inst_status}")

    log.debug(f"Waiting for {instance_name} to come online...")
    real_world_helper.wait_for_x_seconds(30)
    log.debug(f"{instance_name} started")


def start_instance_from_image(zone_name, instance_name, username):
    """Create a GCE VM from configured image and wait for SSH readiness."""
    image_response = compute.images().get(project=PROJECT, image=GCP_IMAGE_NAME).execute()
    source_disk_image = image_response["selfLink"]
    machine_type = f"zones/{zone_name}/machineTypes/{MACHINE_TYPE}"

    config = {
        "name": instance_name,
        "machineType": machine_type,
        "disks": [
            {
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": source_disk_image,
                },
            }
        ],
        "networkInterfaces": [
            {
                "network": "global/networks/default",
                "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
            }
        ],
    }

    operation = compute.instances().insert(project=PROJECT, zone=zone_name, body=config).execute()["name"]

    log.info(f"Waiting to start {instance_name}...")

    seconds = 1
    result_status = ""

    while result_status != "DONE":
        result = compute.zoneOperations().get(project=PROJECT, zone=zone_name, operation=operation).execute()
        result_status = result["status"]

        log.debug("Time elapsed (s): " + str(seconds))
        real_world_helper.wait_for_x_seconds(1)
        seconds += 1

    seconds = 1
    external_ip_address = get_external_ip_address(zone_name, instance_name)

    sleep_time = 5
    log.debug("WAITING FOR " + str(sleep_time) + " SECONDS WHILE GCP INSTANCE COMES ONLINE")
    real_world_helper.wait_for_x_seconds(sleep_time)

    while True:
        try:
            if run_date_command(external_ip_address, username):
                return external_ip_address
        except (NoValidConnectionsError, AuthenticationException):
            log.debug("Waiting for valid SSH connection...")

        log.debug("Time elapsed (s): " + str(seconds))
        time.sleep(1)
        seconds += 1


def stop_instance(zone_name, instance_name):
    """Stop a GCE instance."""
    compute.instances().stop(project=PROJECT, zone=zone_name, instance=instance_name).execute()
    print(f"{instance_name} stopped")


def delete_instance(zone_name, instance_name):
    """Delete a GCE instance."""
    compute.instances().delete(project=PROJECT, zone=zone_name, instance=instance_name).execute()
    log.debug(f"{instance_name} deleted")


def get_ip(zone_name, instance_name):
    """Return external IPv4 address for a GCE instance."""
    response = compute.instances().get(project=PROJECT, zone=zone_name, instance=instance_name).execute()
    external_ip = response["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
    return external_ip


def get_instance_status(zone_name, instance_name):
    """Return GCE instance status string."""
    return compute.instances().get(project=PROJECT, zone=zone_name, instance=instance_name).execute()["status"]
