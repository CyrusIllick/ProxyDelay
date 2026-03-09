"""Shared remote-execution and orchestration utilities for real-world tests."""

import multiprocessing
import os
import random
import time

import paramiko

import compute_engine
import log
import round_trip_time_stabilization_helper
from config_loader import get_topology_config

TOPOLOGY = get_topology_config()
CONGESTION_CONTROL_ALGORITHMS = TOPOLOGY["congestion_control_algorithms"]
GOOGLE_CLOUD_PROVIDER_ZONES = TOPOLOGY["gcp_zones"]
SSH_PRIVATE_KEY_PATH = TOPOLOGY.get("ssh_private_key_path", "")

DATE_COMMAND = "date"
RMEM_COMMAND = "sudo sysctl -w net.core.rmem_max=536870912 net.ipv4.tcp_rmem='4096 131072 536870912'"
WMEM_COMMAND = "sudo sysctl -w net.core.wmem_max=536870912 net.ipv4.tcp_wmem='4096 16384 537870912'"
CONGESTION_CONTROL_COMMAND = "sudo sysctl net.ipv4.tcp_congestion_control=%congestionControlAlgorithm"


def wait_for_x_seconds(seconds):
    """Sleep for `seconds` while emitting simple progress dots."""
    for _ in range(seconds):
        print(".", end="", flush=True)
        time.sleep(1)
    log.info("Sleep for " + str(seconds) + " complete!")


def generate_three_word_string():
    """Generate short random identifier used in test IDs and host names."""
    word_list = [
        "act",
        "ant",
        "art",
        "bag",
        "bat",
        "bee",
        "beg",
        "box",
        "bun",
        "bus",
        "can",
        "car",
        "cat",
        "dig",
        "dip",
        "eat",
        "ego",
        "end",
        "era",
        "far",
        "fee",
        "few",
        "fit",
        "fog",
        "fox",
        "fun",
        "gem",
        "get",
        "hip",
        "hit",
        "hot",
        "hug",
        "hut",
        "jet",
        "lay",
        "leg",
        "lid",
        "lip",
        "lot",
        "man",
        "mix",
        "mud",
        "nun",
        "oak",
        "owe",
        "pan",
        "pat",
        "pin",
        "pit",
        "pop",
        "red",
        "row",
        "run",
        "sea",
        "sip",
        "tap",
        "tie",
        "tin",
        "top",
        "vat",
        "yep",
        "zip",
        "zoo",
    ]
    random_words = random.sample(word_list, 3)
    return "-".join(random_words)


def _ssh_connect(ssh_client, host, username):
    """Connect paramiko client with optional configured private key."""
    kwargs = {"hostname": host, "username": username}
    if SSH_PRIVATE_KEY_PATH:
        kwargs["key_filename"] = SSH_PRIVATE_KEY_PATH
    ssh_client.connect(**kwargs)


def get_external_ip_address(instance_zone, instance_name):
    """Resolve public IP address for a GCP instance."""
    print("<=========================================================>")
    external_ip_address = compute_engine.get_ip(instance_zone, instance_name)
    print(f"External IP Address: {external_ip_address}")
    return external_ip_address


def run_command_on_host(host, command, username, output_file_path=None):
    """Run one remote command over SSH and optionally append output to file."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log.info("Command: " + command)
    log.info("Host: " + host)
    log.info("\n")

    _ssh_connect(ssh, host, username)
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

    return True


def run_ss_command_on_host(test_length, host, command, username, output_file_path=None):
    """Sample `ss` repeatedly on a remote host for roughly test_length seconds."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log.debug("SS command: " + command)
    _ssh_connect(ssh, host, username)

    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
    stdout.channel.settimeout(1.0)

    for _ in range(test_length * 3):
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

        time.sleep(0.4)

    return True


def run_initial_delay_command(flow_direction, instances, username):
    """Install initial tc/netem delay state before traffic starts."""
    print("Running initial delay command on outgoing traffic ports on all senders...")
    if flow_direction == "forward":
        run_delay_command_on_all_netperfs(instances, username)

    if flow_direction == "reverse":
        run_delay_command_on_netperf_ports_on_netserver(instances, username)


def run_delay_command_on_all_netperfs(instances, username):
    """Apply delay setup on every netperf instance."""
    for instance in instances:
        if instance["role"] == "netperf":
            round_trip_time_stabilization_helper.run_delay_command(instance, username)


def run_delay_command_on_netperf_ports_on_netserver(instances, username):
    """Apply per-netperf-port delay setup on netserver (reverse flow mode)."""
    for instance in instances:
        if instance["role"] != "netserver":
            continue

        for netperf_instance in instances:
            if netperf_instance["role"] != "netperf":
                continue

            if netperf_instance["round_trip_time_target"] == 0:
                continue

            round_trip_time_stabilization_helper.run_delay_command_for_specific_port(
                instance,
                username,
                netperf_instance["netperf_port"],
                netperf_instance["round_trip_time_target"],
            )


def run_date_command(external_ip_address, username):
    """Run `date` remotely as connectivity/readiness check."""
    return run_command_on_host(external_ip_address, DATE_COMMAND, username)


def run_rmem_command(external_ip_address, username):
    """Tune receive socket buffer limits on remote host."""
    run_command_on_host(external_ip_address, RMEM_COMMAND, username)


def run_wmem_command(external_ip_address, username):
    """Tune send socket buffer limits on remote host."""
    run_command_on_host(external_ip_address, WMEM_COMMAND, username)


def run_set_congestion_control_algorithm_command(external_ip_address, username, congestion_control_algorithm):
    """Set kernel TCP congestion control algorithm on remote host."""
    command = CONGESTION_CONTROL_COMMAND.replace("%congestionControlAlgorithm", congestion_control_algorithm)
    run_command_on_host(external_ip_address, command, username)


def run_command_on_aws_instance(instance_ip, username, command):
    """Run one SSH command on AWS host and print stdout."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    _ssh_connect(ssh, instance_ip, username)
    stdin, stdout, stderr = ssh.exec_command(command)
    output = stdout.read().decode("utf-8")
    print(output)
    ssh.close()


def choose_google_cloud_provider_zone():
    """Prompt user to choose one configured GCP zone."""
    index = 1
    for zone in GOOGLE_CLOUD_PROVIDER_ZONES:
        print(f"{str(index)}: {zone}")
        index += 1

    zone_index = int(input("Enter zone number: "))
    return GOOGLE_CLOUD_PROVIDER_ZONES[zone_index - 1]


def choose_congestion_control_algorithm():
    """Prompt user to select one configured congestion control algorithm."""
    print("Which congestion control algorithm do you want to use?\n")
    for idx, algorithm in enumerate(CONGESTION_CONTROL_ALGORITHMS, start=1):
        print(f"{idx}. {algorithm}")

    choice = input("\nPlease enter the number of your choice: (2) ")
    congestion_control_algorithm = "bbr" if not choice else CONGESTION_CONTROL_ALGORITHMS[int(choice) - 1]

    print(f"\nYou've chosen {congestion_control_algorithm}.\n")
    return congestion_control_algorithm


def run_netserver_command(external_ip_address, username):
    """Start netserver daemon on remote host."""
    print("<=========================================================>")
    log.info("Waiting for netserver program to start up...")

    net_server_command = "sudo netserver"
    run_command_on_host(
        external_ip_address,
        net_server_command,
        username=username,
    )

    wait_for_x_seconds(2)


def run_ss_command_for_x_seconds(host, username, test_length, port, output_file_path):
    """Collect ss samples for one port and append to output file."""
    log.info("Running run_ss_command_for_x_seconds")
    ss_command = f"sudo /root/iproute2/iproute2/misc/ss -tinmo dport = {port}"
    run_ss_command_on_host(test_length, host, ss_command, username, output_file_path)


def run_ss_command_on_all_netperfs(flow_direction, test_length, instances, timestamp, username, report_root="reports"):
    """Spawn ss samplers for all netperf instances."""
    print("Running ss command on all netperf instances...")

    netserver_external_ip_address = ""
    for instance in instances:
        if instance["role"] == "netserver":
            netserver_external_ip_address = instance["external_ip_address"]

    if netserver_external_ip_address == "":
        raise Exception("netserver_external_ip_address is empty")

    processes = []
    if random.random() < 0.5:
        instances.reverse()

    for instance in instances:
        if instance["role"] != "netperf":
            continue

        filename = (
            f"{report_root}/{timestamp}/{instance['platform']}/{instance['instance_zone']}/"
            f"{instance['instance_name']}-({instance['congestion_control_algorithm']}).txt"
        )

        if flow_direction == "forward":
            address_to_run_ss_command_on = instance["external_ip_address"]
        elif flow_direction == "reverse":
            address_to_run_ss_command_on = netserver_external_ip_address
        else:
            raise Exception("Flow direction not recognized: " + flow_direction)

        process = multiprocessing.Process(
            target=run_ss_command_for_x_seconds,
            args=(address_to_run_ss_command_on, username, test_length, instance["netperf_port"], filename),
        )
        process.start()
        processes.append(process)

    return processes


def run_netperf_command_on_all_netperfs(flow_direction, test_length, instances, username):
    """Spawn netperf traffic generators on all netperf instances."""
    print("Running netperf command on all netperf instances...")

    netserver_external_ip_address = ""
    for instance in instances:
        if instance["role"] == "netserver":
            netserver_external_ip_address = instance["external_ip_address"]

    if netserver_external_ip_address == "":
        raise Exception("netserver_external_ip_address is empty")

    processes = []
    for instance in instances:
        if instance["role"] != "netperf":
            continue

        run_rmem_command(instance["external_ip_address"], username)
        run_wmem_command(instance["external_ip_address"], username)

        run_set_congestion_control_algorithm_command(
            instance["external_ip_address"],
            username,
            instance["congestion_control_algorithm"],
        )

        if flow_direction == "forward":
            netperf_command = (
                f"netperf -H {netserver_external_ip_address} -l {test_length} "
                f"-t TCP_STREAM -- -P {instance['netperf_port']}"
            )
        elif flow_direction == "reverse":
            netperf_command = (
                f"netperf -H {netserver_external_ip_address} -l {test_length} "
                f"-t TCP_MAERTS -- -P {instance['netperf_port']}"
            )
        else:
            raise Exception("Flow direction not recognized: " + flow_direction)

        log.info(netperf_command)

        process = multiprocessing.Process(
            target=run_command_on_host,
            args=(instance["external_ip_address"], netperf_command, username),
        )
        process.start()
        processes.append(process)

    return processes
