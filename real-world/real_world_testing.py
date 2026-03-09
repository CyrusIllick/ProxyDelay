"""Interactive entrypoint for configuring and running real-world tests."""

import datetime
from random import randrange

import compute_engine
import ec2_helper
import figure_parser
import log
import real_world_helper
import real_world_noise_helper
import round_trip_time_stabilization_helper
import summary_helper
from config_loader import get_report_root, get_topology_config

TOPOLOGY = get_topology_config()

GOOGLE_CLOUD_PROVIDER_ZONES = TOPOLOGY["gcp_zones"]
AMAZON_WEB_SERVICES_ZONES = TOPOLOGY["aws_zones"]
USERNAMES = TOPOLOGY["usernames"]
LOCAL_SERVERS = TOPOLOGY["local_servers"]
CONGESTION_CONTROL_ALGORITHMS = TOPOLOGY["congestion_control_algorithms"]
CLOUD_INTERFACE_NAME = TOPOLOGY.get("cloud_interface_name", "enp0s4")
AWS_INTERFACE_NAME = TOPOLOGY.get("aws_instance_interface_name", "eth0")
REPORT_ROOT = get_report_root()

instances = []
instances_per_zone = {}


def _local_servers_by_role(role: str):
    """Return local hosts from topology config matching a role."""
    return [server for server in LOCAL_SERVERS if server.get("role") == role]


def configure_cloud_netperf_instances(test_id):
    """Interactively add cloud netperf sender/receiver instance entries."""
    print("<=========================================================>")
    print("Netperf Instances in Google Cloud Platform")

    for zone in GOOGLE_CLOUD_PROVIDER_ZONES:
        platform = "gcp"
        num_instances_str = input(f"How many GCP netperf instances do you want in {zone}? (0)")
        num_instances = int(num_instances_str) if num_instances_str else 0
        instances_per_zone[zone] = int(num_instances)

        for _ in range(num_instances):
            create_instance_dict_entry(test_id, platform, zone)

    print("Netperf Instances in Amazon Web Services")
    for zone in AMAZON_WEB_SERVICES_ZONES:
        platform = "aws"
        num_instances_str = input(f"How many AWS netperf instances do you want in {zone}? (0)")
        num_instances = int(num_instances_str) if num_instances_str else 0
        instances_per_zone[zone] = int(num_instances)

        for _ in range(num_instances):
            create_instance_dict_entry(test_id, platform, zone)


def create_instance_dict_entry(test_id, platform, zone):
    """Append one cloud netperf instance descriptor to global instance list."""
    congestion_control_algorithm = real_world_helper.choose_congestion_control_algorithm()
    random_number_as_string = str(randrange(10000000))
    generated_name = test_id + "-" + random_number_as_string
    log.info("Instance added with name: " + generated_name)

    if platform == "gcp":
        interface_name = CLOUD_INTERFACE_NAME
    elif platform == "aws":
        interface_name = AWS_INTERFACE_NAME
    else:
        interface_name = "eth0"

    instance_dict = {
        "platform": platform,
        "role": "netperf",
        "instance_name": generated_name,
        "instance_zone": zone,
        "external_ip_address": "",
        "congestion_control_algorithm": congestion_control_algorithm,
        "instance_id": "",
        "round_trip_time_target": 0,
        "netperf_port": 0,
        "interface_name": interface_name,
    }
    instances.append(instance_dict)


def create_cloud_instances(username):
    """Create all configured non-local instances in parallel."""
    processes = []

    for instance in instances:
        if instance["platform"] == "local":
            continue

        if instance["platform"] == "gcp":
            process = multiprocessing.Process(
                target=compute_engine.start_instance_from_image,
                args=(instance["instance_zone"], instance["instance_name"], username),
            )
            processes.append(process)
            process.start()

        if instance["platform"] == "aws":
            process = multiprocessing.Process(
                target=ec2_helper.start_instance_from_image,
                args=(instance["instance_name"], ec2_helper.AWS_IMAGE_ID, username),
            )
            processes.append(process)
            process.start()

    for process in processes:
        process.join()

    for instance in instances:
        if instance["platform"] == "aws":
            instance_id = ec2_helper.get_instance_id_by_name(instance["instance_name"])
            instance["instance_id"] = instance_id
            log.info(str(instance["instance_id"]))


def populate_external_ip_addresses():
    """Resolve and store external IP addresses for cloud instances."""
    print("Populating external IP addresses...")

    for instance in instances:
        if instance["platform"] == "gcp":
            external_ip_address = real_world_helper.get_external_ip_address(
                instance["instance_zone"],
                instance["instance_name"],
            )
            instance["external_ip_address"] = external_ip_address

        if instance["platform"] == "aws":
            external_ip_address = ec2_helper.get_ip(instance["instance_id"])
            instance["external_ip_address"] = external_ip_address


def show_instance_status():
    """Print instance role/status summary for current test plan."""
    print("Instances:")

    for instance in instances:
        instance_status = ""

        if instance["platform"] == "local":
            instance_status = "online"

        if instance["platform"] == "gcp":
            instance_status = compute_engine.get_instance_status(
                instance["instance_zone"],
                instance["instance_name"],
            )

        if instance["platform"] == "aws":
            instance_status = ec2_helper.get_instance_status(instance["instance_id"])

        if instance_status == "":
            raise Exception("instance_status is empty")

        print("Name: " + instance["instance_name"])
        print("Role: " + instance["role"])
        print("Status: " + instance_status)


def choose_user():
    """Prompt for SSH username from topology config."""
    if not USERNAMES:
        raise Exception("No usernames configured in config/topology.json")

    print("<=========================================================>")
    for i, name in enumerate(USERNAMES, 1):
        print(f"{i}. {name}")

    username_number = int(input("Choose a username number: "))
    username = USERNAMES[username_number - 1]
    print(f"You are now running tests as {username}")
    return username


def choose_flow_direction():
    """Prompt for test traffic direction."""
    print("<=========================================================>")
    print("Would you like traffic to flow from netperfs to netserver [forward]")
    print("or from netserver to netperfs [reverse]? (1)")

    print("1. Forward")
    print("2. Reverse")

    choice = int(input("Enter choice: ") or "1")

    if choice == 1:
        return "forward"
    if choice == 2:
        return "reverse"
    raise Exception("Invalid flow direction choice")


def choose_test_duration():
    """Prompt for test duration in seconds."""
    print("<=========================================================>")
    test_length = int(input("Enter the duration of testing (seconds): "))
    print(f"You are running the test for {test_length} seconds")
    return test_length


def choose_netserver_in_cloud_or_on_premises(flow_direction):
    """Prompt for netserver placement (cloud vs on-prem)."""
    print("<=========================================================>")

    if flow_direction == "forward":
        message = "Where would like the netserver (traffic receiver) to run?"
    elif flow_direction == "reverse":
        message = "Where would like the netserver (traffic sender) to run?"
    else:
        raise Exception("Flow direction not recognized: " + flow_direction)

    print(message)
    print("1. In the cloud")
    print("2. On premises")

    choice = int(input("Enter choice: "))
    return choice


def choose_netperf_in_cloud_or_on_premises(flow_direction):
    """Prompt for netperf placement (cloud, on-prem, or both)."""
    if flow_direction == "forward":
        message = "Where would you like the netperf(s) (traffic senders) to run?"
    elif flow_direction == "reverse":
        message = "Where would you like the netperf(s) (traffic receivers) to run?"
    else:
        raise Exception("Flow direction not recognized: " + flow_direction)

    print("<=========================================================>")
    print(message)

    print("1. In the cloud")
    print("2. On premises")
    print("3. Both in the cloud and on premises")

    choice = int(input("Enter choice: "))
    return choice


def configure_netperf(flow_direction, test_id):
    """Configure all netperf endpoints for this run."""
    netperf_location = choose_netperf_in_cloud_or_on_premises(flow_direction)

    if netperf_location == 1:
        configure_cloud_netperf_instances(test_id)
    elif netperf_location == 2:
        configure_local_netperf_instances(flow_direction)
    elif netperf_location == 3:
        configure_cloud_netperf_instances(test_id)
        configure_local_netperf_instances(flow_direction)


def configure_round_trip_time_target_on_all_senders(flow_direction):
    """Collect desired RTT target per sender flow for proxy-delay control."""
    print(r"""
      _____  ______ _           __     __
     |  __ \|  ____| |        /\\ \   / /
     | |  | | |__  | |       /  \\ \_/ /
     | |  | |  __| | |      / /\ \\   /
     | |__| | |____| |____ / ____ \| |
     |_____/|______|______/_/    \_\_|
    """)

    if flow_direction == "forward":
        flow_label = "netperf -> netserver"
    elif flow_direction == "reverse":
        flow_label = "netserver -> netperf"
    else:
        raise Exception("Flow direction not recognized: " + flow_direction)

    for instance in instances:
        if instance["role"] != "netperf":
            continue

        print("What would you like the round trip time (ms) to be for the following flow:\n")
        print("Instance name: " + instance["instance_name"])
        print("Instance platform: " + instance["platform"])
        print("Instance zone: " + instance["instance_zone"])
        print("Flow direction: " + flow_label)

        choice = input("\nEnter choice: (0) ")
        instance["round_trip_time_target"] = 0 if not choice else int(choice)


def choose_zone_for_netserver(flow_direction):
    """Prompt for the zone used by cloud netserver placement."""
    print("<=========================================================>")
    if flow_direction == "forward":
        message = "Which zone would you like the netserver (traffic receiver) to run in?"
    elif flow_direction == "reverse":
        message = "Which zone would you like the netserver (traffic sender) to run in?"
    else:
        raise Exception("Flow direction not recognized: " + flow_direction)

    print("<=========================================================>")
    print(message)

    zone = real_world_helper.choose_google_cloud_provider_zone()
    return zone


def delete_instances():
    """Delete all cloud instances created for this run."""
    print("Deleting cloud instances...")

    for instance in instances:
        if instance["platform"] == "gcp":
            compute_engine.delete_instance(instance["instance_zone"], instance["instance_name"])
        if instance["platform"] == "aws":
            ec2_helper.delete_instance(instance["instance_id"])


def configure_netserver(flow_direction, test_id):
    """Configure netserver endpoint and append it to global instance list."""
    netserver_location = choose_netserver_in_cloud_or_on_premises(flow_direction)

    platform = ""
    netserver_instance_zone = ""
    netserver_external_ip_address = ""
    interface_name = ""
    instance_name = ""

    if netserver_location == 1:
        random_number_as_string = str(randrange(10000000))
        generated_name = test_id + "-" + random_number_as_string

        platform = "gcp"
        netserver_instance_zone = choose_zone_for_netserver(flow_direction)
        netserver_external_ip_address = ""
        interface_name = CLOUD_INTERFACE_NAME
        instance_name = generated_name

    elif netserver_location == 2:
        local_netserver_choice = configure_local_netserver()

        platform = "local"
        netserver_instance_zone = "on-prem"
        netserver_external_ip_address = local_netserver_choice["external_ip_address"]
        interface_name = local_netserver_choice["interface_name"]
        instance_name = local_netserver_choice["instance_name"]

    if platform == "":
        raise Exception("platform is empty")
    if netserver_instance_zone == "":
        raise Exception("netserver_instance_zone is empty")
    if instance_name == "":
        raise Exception("instance_name is empty")

    congestion_control_algorithm = real_world_helper.choose_congestion_control_algorithm()

    instance_dict = {
        "platform": platform,
        "role": "netserver",
        "instance_name": instance_name,
        "instance_zone": netserver_instance_zone,
        "external_ip_address": netserver_external_ip_address,
        "congestion_control_algorithm": congestion_control_algorithm,
        "instance_id": "",
        "round_trip_time_target": 0,
        "netperf_port": 0,
        "interface_name": interface_name,
    }

    instances.append(instance_dict)


def setup_netserver(username):
    """Apply host tuning and CC selection on netserver host(s)."""
    for instance in instances:
        if instance["role"] != "netserver":
            continue

        netserver_external_ip_address = instance["external_ip_address"]
        real_world_helper.run_rmem_command(netserver_external_ip_address, username)
        real_world_helper.run_wmem_command(netserver_external_ip_address, username)
        real_world_helper.run_set_congestion_control_algorithm_command(
            netserver_external_ip_address,
            username,
            instance["congestion_control_algorithm"],
        )


def configure_local_netserver():
    """Prompt user to choose one configured local netserver."""
    local_netservers = _local_servers_by_role("netserver")
    if not local_netservers:
        raise Exception("No local netserver entries in config/topology.json")

    print("<=========================================================>")
    print("Which local netserver do you want to use?")

    for idx, netserver in enumerate(local_netservers, start=1):
        print(f"{idx}. {netserver['instance_name']}")

    choice = input("Please enter the number of your choice: (1) ")
    selected = local_netservers[0] if not choice else local_netservers[int(choice) - 1]

    print(f"You've chosen {selected['instance_name']}.")
    return selected


def configure_local_netperf_instances(flow_direction):
    """Interactively add local netperf endpoints."""
    local_netperfs = _local_servers_by_role("netperf")
    if not local_netperfs:
        raise Exception("No local netperf entries in config/topology.json")

    print("<=========================================================>")
    for local_netperf in local_netperfs:
        if flow_direction == "forward":
            message = "Do you want to use " + local_netperf["instance_name"] + " as a traffic sender? (Y/n)"
        elif flow_direction == "reverse":
            message = "Do you want to use " + local_netperf["instance_name"] + " as a traffic receiver? (Y/n)"
        else:
            raise Exception("Flow direction not recognized: " + flow_direction)

        include_netperf_str = input(message)
        include_netperf = include_netperf_str if include_netperf_str else "y"

        if include_netperf.lower() != "y":
            continue

        if flow_direction == "forward":
            congestion_control_algorithm = real_world_helper.choose_congestion_control_algorithm()
        elif flow_direction == "reverse":
            congestion_control_algorithm = "cubic"
        else:
            raise Exception("Flow direction not recognized: " + flow_direction)

        instance_dict = {
            "role": "netperf",
            "platform": "local",
            "instance_name": local_netperf["instance_name"],
            "instance_zone": "on-prem",
            "external_ip_address": local_netperf["external_ip_address"],
            "congestion_control_algorithm": congestion_control_algorithm,
            "round_trip_time_target": 0,
            "netperf_port": 0,
            "interface_name": local_netperf["interface_name"],
        }
        instances.append(instance_dict)


def set_netperf_ports_on_all_netperfs():
    """Assign unique netperf TCP ports to each netperf endpoint."""
    port = 10000

    for instance in instances:
        if instance["role"] != "netperf":
            continue

        instance["netperf_port"] = port
        port += 1


def run_tests():
    """Run full interactive real-world workflow end to end."""
    print("Log level: " + str(log.log_level))

    ct = datetime.datetime.now()
    timestamp = ct.strftime("%Y-%m-%d--%H:%M:%S")

    test_id = real_world_helper.generate_three_word_string()

    username = choose_user()
    flow_direction = choose_flow_direction()
    test_length = choose_test_duration()

    configure_netserver(flow_direction, test_id)
    configure_netperf(flow_direction, test_id)
    configure_round_trip_time_target_on_all_senders(flow_direction)

    real_world_noise_helper.configure_noise(test_id, instances)

    create_cloud_instances(username)
    real_world_helper.wait_for_x_seconds(2)

    populate_external_ip_addresses()
    setup_netserver(username)
    show_instance_status()
    set_netperf_ports_on_all_netperfs()

    ss_command_processes = real_world_helper.run_ss_command_on_all_netperfs(
        flow_direction,
        test_length,
        instances,
        timestamp,
        username,
        report_root=REPORT_ROOT,
    )

    real_world_helper.wait_for_x_seconds(2)
    real_world_helper.run_initial_delay_command(flow_direction, instances, username)

    netperf_command_processes = real_world_helper.run_netperf_command_on_all_netperfs(
        flow_direction,
        test_length,
        instances,
        username,
    )

    round_trip_time_stabilization_command_processes = (
        round_trip_time_stabilization_helper.stabilize_rtt_for_all_outgoing_flows(
            flow_direction,
            instances,
            test_length,
            username,
        )
    )

    noise_processes = real_world_noise_helper.start_noise_processes(instances, test_length, username)

    processes = (
        ss_command_processes
        + netperf_command_processes
        + round_trip_time_stabilization_command_processes
        + noise_processes
    )

    for process in processes:
        process.join()

    delete_instances()

    data_array = figure_parser.generate_data_array(timestamp, report_root=REPORT_ROOT)
    figure_parser.create_graphs_directory(timestamp, report_root=REPORT_ROOT)
    figure_parser.generate_graphs(timestamp, data_array, report_root=REPORT_ROOT)
    figure_parser.generate_statistics(timestamp, data_array, report_root=REPORT_ROOT)

    summary_helper.create_summary(
        test_id,
        username,
        flow_direction,
        test_length,
        instances,
        timestamp,
        report_root=REPORT_ROOT,
    )


def main():
    """CLI entrypoint."""
    run_tests()


if __name__ == "__main__":
    main()
