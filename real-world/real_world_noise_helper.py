"""Optional background traffic helpers for real-world tests."""

import math
import multiprocessing
from random import randrange

import real_world_helper
from config_loader import get_topology_config

TOPOLOGY = get_topology_config()
LOCAL_SERVERS = TOPOLOGY["local_servers"]
CLOUD_INTERFACE_NAME = TOPOLOGY.get("cloud_interface_name", "enp0s4")

IPERF_SERVER_COMMAND = "iperf3 -s -p %port > /dev/null 2>&1 &"
IPERF_CLIENT_COMMAND = "iperf3 -c %ipAddress -p %port -u -b3G -t%burstTime"


def _local_servers_by_role(role: str):
    """Return local servers from topology config matching a role."""
    return [server for server in LOCAL_SERVERS if server.get("role") == role]


def configure_noise_sender():
    """Interactively choose local host that will send iperf noise traffic."""
    print("<=========================================================>")
    print("Which local server do you want to use to send noise?")

    available_servers = _local_servers_by_role("netperf")
    if not available_servers:
        raise Exception("No local netperf entries configured for noise sender")

    for idx, server in enumerate(available_servers, start=1):
        print(f"{idx}. {server['instance_name']}")

    choice = input("Please enter the number of your choice: (1) ")
    selected = available_servers[0] if not choice else available_servers[int(choice) - 1]

    print(f"You've chosen {selected['instance_name']}.")

    instance_dict = {
        "platform": "local",
        "role": "noise-sender",
        "instance_name": selected["instance_name"],
        "instance_zone": "on-prem",
        "external_ip_address": selected["external_ip_address"],
        "congestion_control_algorithm": "cubic",
        "round_trip_time_target": 0,
        "netperf_port": 0,
        "interface_name": selected["interface_name"],
    }

    return instance_dict


def configure_noise_receiver(test_id):
    """Configure cloud receiver instance entry for noise traffic."""
    print("<=========================================================>")
    print("Noise Receiver in Google Cloud Platform")

    zone = real_world_helper.choose_google_cloud_provider_zone()

    random_number_as_string = str(randrange(10000000))
    generated_name = test_id + "-" + random_number_as_string

    instance_dict = {
        "platform": "gcp",
        "role": "noise-receiver",
        "instance_name": generated_name,
        "instance_zone": zone,
        "external_ip_address": "",
        "congestion_control_algorithm": "cubic",
        "round_trip_time_target": 0,
        "netperf_port": 0,
        "interface_name": CLOUD_INTERFACE_NAME,
    }

    return instance_dict


def configure_noise(test_id, instances):
    """Optionally append noise sender/receiver instance entries."""
    print("<=========================================================>")
    message = "Do you want to add some noise to this test? (Y/n)"

    include_noise_str = input(message)
    include_noise = include_noise_str if include_noise_str else "y"

    if include_noise.lower() == "y":
        noise_sender_instance = configure_noise_sender()
        instances.append(noise_sender_instance)

        noise_receiver_instance = configure_noise_receiver(test_id)
        instances.append(noise_receiver_instance)


def start_noise_client(instances, port, test_length, username):
    """Run bursty UDP iperf traffic from selected local noise sender."""
    destination_ip_address = ""

    for instance in instances:
        if instance["role"] == "noise-receiver":
            destination_ip_address = instance["external_ip_address"]
            break

    if destination_ip_address == "":
        return

    burst_time = 9
    number_of_bursts = int(math.ceil(test_length / burst_time))

    single_command = IPERF_CLIENT_COMMAND.replace("%ipAddress", destination_ip_address)
    single_command = single_command.replace("%port", str(port))
    single_command = single_command.replace("%burstTime", str(burst_time))

    command = ""
    for _ in range(0, number_of_bursts):
        command += single_command + " ; "
    command = command[:-2]
    print(f"noise command = {command}")

    for instance in instances:
        if instance["role"] != "noise-sender":
            continue

        real_world_helper.run_command_on_host(instance["external_ip_address"], command, username)


def start_noise_processes(instances, test_length, username):
    """Start asynchronous noise traffic process(es)."""
    processes = []

    noise_port = 5201
    process = multiprocessing.Process(
        target=start_noise_client,
        args=(instances, noise_port, test_length, username),
    )
    process.start()
    processes.append(process)

    return processes
