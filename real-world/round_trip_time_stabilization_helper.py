"""Helpers for applying and adapting per-flow proxy delay via tc/netem."""

import multiprocessing
import time

import paramiko

import figure_parser
import log
import real_world_helper
from config_loader import get_topology_config

TOPOLOGY = get_topology_config()
SSH_PRIVATE_KEY_PATH = TOPOLOGY.get("ssh_private_key_path", "")

QDISC_SETUP_COMMAND = ""
QDISC_SETUP_COMMAND += "sudo modprobe ifb;"
QDISC_SETUP_COMMAND += " sudo ip link add ifb2 type ifb 2>/dev/null || true;"
QDISC_SETUP_COMMAND += " sudo ip link set ifb2 up;"
QDISC_SETUP_COMMAND += " sudo tc qdisc replace dev %interface handle ffff: ingress;"
QDISC_SETUP_COMMAND += (
    " sudo tc filter replace dev %interface parent ffff: protocol ip u32 "
    "match ip dport %port 0xffff action mirred egress redirect dev ifb2;"
)
QDISC_SETUP_COMMAND += " sudo tc qdisc replace dev ifb2 root netem delay %delayms;"

QDISC_UPDATE_COMMAND = "sudo tc qdisc change dev ifb2 root netem delay %delayms;"


def run_delay_command(instance, username):
    """Install ingress->ifb redirect and initial netem delay for one instance."""
    command = QDISC_SETUP_COMMAND
    command = command.replace("%delay", str(instance["round_trip_time_target"]))
    command = command.replace("%interface", instance["interface_name"])
    command = command.replace("%port", str(instance["netperf_port"]))
    real_world_helper.run_command_on_host(instance["external_ip_address"], command, username)


def run_delay_command_for_specific_port(instance, username, port, round_trip_time_target):
    """Install delay control for a specific port on a specific instance."""
    command = QDISC_SETUP_COMMAND
    command = command.replace("%delay", str(round_trip_time_target))
    command = command.replace("%interface", instance["interface_name"])
    command = command.replace("%port", str(port))
    real_world_helper.run_command_on_host(instance["external_ip_address"], command, username)


def stabilize_rtt_for_all_outgoing_flows_on_netserver(instances, test_length, username):
    """Spawn stabilizer processes when sender is the netserver (reverse mode)."""
    processes = []

    for instance in instances:
        if instance["role"] != "netserver":
            continue

        for netperf_instance in instances:
            if netperf_instance["role"] == "netperf":
                if netperf_instance["round_trip_time_target"] == 0:
                    continue

                process = multiprocessing.Process(
                    target=stabilize_delay_on_port_for_x_seconds,
                    args=(
                        test_length,
                        instance,
                        netperf_instance["netperf_port"],
                        netperf_instance["round_trip_time_target"],
                        username,
                    ),
                )
                process.start()
                processes.append(process)

    return processes


def stabilize_rtt_for_all_outgoing_flows_on_netperfs(instances, test_length, username):
    """Spawn stabilizer processes when senders are netperf nodes (forward mode)."""
    processes = []

    for instance in instances:
        if instance["role"] != "netperf":
            continue

        if instance["round_trip_time_target"] == 0:
            continue

        process = multiprocessing.Process(
            target=stabilize_delay_on_port_for_x_seconds,
            args=(
                test_length,
                instance,
                instance["netperf_port"],
                instance["round_trip_time_target"],
                username,
            ),
        )
        process.start()
        processes.append(process)

    return processes


def stabilize_rtt_for_all_outgoing_flows(flow_direction, instances, test_length, username):
    """Dispatch RTT stabilizers according to test traffic direction."""
    print("Stabilizing delay for all outgoing traffic...")
    if flow_direction == "forward":
        round_trip_time_stabilization_command_processes = stabilize_rtt_for_all_outgoing_flows_on_netperfs(
            instances,
            test_length,
            username,
        )
    elif flow_direction == "reverse":
        round_trip_time_stabilization_command_processes = stabilize_rtt_for_all_outgoing_flows_on_netserver(
            instances,
            test_length,
            username,
        )
    else:
        raise Exception("Flow direction not recognized: " + flow_direction)

    return round_trip_time_stabilization_command_processes


def stabilize_delay_on_port_for_x_seconds(test_length, instance, port, round_trip_time_target, username):
    """Continuously adjust netem delay to track a target RTT for one flow."""
    log.info("<=========================================================>")
    log.info("Running stabilize_delay_on_port_for_x_seconds on the following instance:")
    log.info("Instance name:" + instance["instance_name"])
    log.info("Port:" + str(port))

    host = instance["external_ip_address"]
    ss_command = f"sudo /root/iproute2/iproute2/misc/ss -tinmo dport = {port}"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log.debug("Command: " + ss_command)
    connect_kwargs = {"hostname": host, "username": username}
    if SSH_PRIVATE_KEY_PATH:
        connect_kwargs["key_filename"] = SSH_PRIVATE_KEY_PATH
    ssh.connect(**connect_kwargs)

    stdin, stdout, stderr = ssh.exec_command(ss_command, get_pty=True)
    stdout.channel.settimeout(1.0)

    statistic = "mrtt"
    delay_array = [round_trip_time_target]
    current_add = round_trip_time_target

    baseline = 0
    init_mrtt_found = False

    for _ in range(int(test_length / 3)):
        time.sleep(2)

        log.debug(f"RUNNING SS COMMAND FOR {host} at time {time.time()}")
        stdin, stdout, stderr = ssh.exec_command(ss_command, get_pty=True)
        output = iter(stdout.readline, "")

        mrtt_of_instance = figure_parser.get_statistic_from_single_output(output, statistic)

        if mrtt_of_instance is None or mrtt_of_instance == "":
            log.warning("MRTT of " + instance["instance_name"] + " with port " + str(port) + " is None")
            continue

        mrtt_of_instance = int(float(mrtt_of_instance))
        if mrtt_of_instance == 0:
            log.warning("MRTT of " + instance["instance_name"] + " with port " + str(port) + " is 0")
            continue

        if init_mrtt_found is False:
            baseline = mrtt_of_instance
        else:
            if mrtt_of_instance > baseline:
                continue

        init_mrtt_found = True

        log.info("MRTT of " + instance["instance_name"] + " with port " + str(port) + ": " + str(mrtt_of_instance))

        if round_trip_time_target == mrtt_of_instance:
            continue

        if -3 < (round_trip_time_target - mrtt_of_instance) < 3:
            continue

        delay = round_trip_time_target + current_add - mrtt_of_instance
        current_add = delay

        if current_add == 0:
            continue

        if delay < 0:
            log.warning("New delay value is less than zero")
            delay = 0
            current_add = 0

        delay_array.append(delay)

        log.info(str(delay_array))
        log.info(
            "Setting delay on "
            + instance["instance_name"]
            + " with port "
            + str(port)
            + " to "
            + str(delay)
            + "ms"
        )

        command = QDISC_UPDATE_COMMAND.replace("%delay", str(delay))
        log.debug(command)

        stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
        time.sleep(5)

    return True
