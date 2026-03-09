"""AWS EC2 lifecycle helpers used by real-world orchestration."""

import logging as log
import os
import time
from typing import Optional

import boto3
import paramiko
from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError

import real_world_helper
from config_loader import get_cloud_config

CLOUD = get_cloud_config()
AWS_CFG = CLOUD["aws"]

AWS_IMAGE_ID = AWS_CFG.get("image_id", "")
AWS_REGION = AWS_CFG.get("region", "us-east-1")
AWS_PROFILE = AWS_CFG.get("profile", "")
AWS_INSTANCE_TYPE = AWS_CFG.get("instance_type", "t3.micro")
AWS_KEY_NAME = AWS_CFG.get("key_name", "")

if AWS_IMAGE_ID == "":
    raise ValueError("AWS image_id must be set in config/cloud.json")


def _build_ec2_client():
    """Build boto3 EC2 client, honoring optional profile and region."""
    if AWS_PROFILE:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        return session.client("ec2")
    return boto3.client("ec2", region_name=AWS_REGION)


ec2 = _build_ec2_client()

DATE_COMMAND = "date"
RMEM_COMMAND = "sudo sysctl -w net.core.rmem_max=900000000 net.ipv4.tcp_rmem='4096 131072 900000000'"
WMEM_COMMAND = "sudo sysctl -w net.core.wmem_max=900000000 net.ipv4.tcp_wmem='4096 16384 900000000'"


def start_instance_from_image(instance_name, image_id, username):
    """Create an EC2 instance from image and wait for SSH readiness."""
    instance_config = {
        "ImageId": image_id,
        "InstanceType": AWS_INSTANCE_TYPE,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {
                        "Key": "Name",
                        "Value": instance_name,
                    }
                ],
            }
        ],
        "MinCount": 1,
        "MaxCount": 1,
    }

    if AWS_KEY_NAME:
        instance_config["KeyName"] = AWS_KEY_NAME

    response = ec2.run_instances(**instance_config)

    sleep_time = 10
    log.debug("WAITING FOR " + str(sleep_time) + " SECONDS WHILE AWS INSTANCE COMES ONLINE")
    real_world_helper.wait_for_x_seconds(sleep_time)

    instance_id = response["Instances"][0]["InstanceId"]

    while True:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        if "PublicIpAddress" in instance:
            external_ip_address = instance["PublicIpAddress"]
            print(f"Instance {instance_name} started with ID: {instance_id} and IP: {external_ip_address}")
            break
        else:
            log.debug("Waiting for instance to have a public IP address...")
            real_world_helper.wait_for_x_seconds(1)

    seconds = 1
    print(external_ip_address)

    while True:
        try:
            if real_world_helper.run_date_command(external_ip_address, username):
                log.debug(f"Instance {instance_name} started with ID: {instance_id}")
                return instance_id
        except (NoValidConnectionsError, AuthenticationException):
            log.debug("Waiting for valid SSH connection...")

        log.debug("Time elapsed (s): " + str(seconds))
        real_world_helper.wait_for_x_seconds(1)
        seconds += 1


def stop_instance(instance_id):
    """Stop an EC2 instance."""
    ec2.stop_instances(InstanceIds=[instance_id])
    print(f"{instance_id} stopped")


def delete_instance(instance_id):
    """Terminate an EC2 instance."""
    ec2.terminate_instances(InstanceIds=[instance_id])
    log.debug(f"{instance_id} deleted")


def get_ip(instance_id):
    """Return public IPv4 address for an EC2 instance."""
    response = ec2.describe_instances(InstanceIds=[instance_id])
    return response["Reservations"][0]["Instances"][0]["PublicIpAddress"]


def get_instance_status(instance_id):
    """Return EC2 instance state."""
    response = ec2.describe_instances(InstanceIds=[instance_id])
    return response["Reservations"][0]["Instances"][0]["State"]["Name"]


def run_command_on_instance(host, command, username, output_file_path=None):
    """Run SSH command on an EC2 host and optionally append output to a file."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log.debug("Command: " + command)

    try:
        ssh.connect(
            host,
            username=username,
        )
        stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)

        if output_file_path:
            directory_path = os.path.dirname(output_file_path)
            os.makedirs(directory_path, exist_ok=True)

            with open(output_file_path, "a", encoding="utf-8") as output_file:
                output_file.write("# %f\n" % (time.time(),))
                for line in iter(stdout.readline, ""):
                    output_file.write(line)
        else:
            for line in iter(stdout.readline, ""):
                print(line, end="")
    except Exception as e:
        print("Error:", e)
        return False
    finally:
        ssh.close()

    return True


def get_instance_id_by_name(instance_name) -> Optional[str]:
    """Find instance ID by Name tag, returning None when not found."""
    response = ec2.describe_instances(
        Filters=[
            {
                "Name": "tag:Name",
                "Values": [instance_name],
            }
        ]
    )

    if "Reservations" in response and len(response["Reservations"]) > 0:
        instances = response["Reservations"][0]["Instances"]
        if len(instances) > 0:
            return instances[0]["InstanceId"]

    return None
