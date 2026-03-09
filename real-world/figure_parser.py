"""Parse recorded ss output and generate plots/statistics for real-world tests."""

import glob
import os
import re
import statistics

import matplotlib.pyplot as plt

import log
from config_loader import get_report_root

GRAPH_PARAMETERS = [
    ("rtt_min", "Min Rtt", False),
    ("rtt_avg", "Rtt", False),
    ("bw", "Mbps", True),
    ("pacing_rate", "Mbps", True),
    ("cwnd", "cwnd", False),
    ("mrtt", "Mrtt", False),
    ("delivery_rate", "Mbps", True),
    ("notsent", "Megabytes", True),
    ("delivered", "Megabytes", True),
]


def _resolve_report_root(report_root=None):
    """Return explicit report_root or configured default."""
    return report_root or get_report_root()


def convert_to_title(string):
    """Convert snake_case metric key into title-cased label."""
    words = string.split("_")
    capitalized_words = [word.capitalize() for word in words]
    return " ".join(capitalized_words)


def plot_data(instance_data_array, parameter, save_path):
    """Plot one metric for all instances and write figure to save_path."""
    log.debug("Plotting data for: " + parameter[0])
    plt.figure(parameter[0])

    delta_time = find_delta_time(instance_data_array)
    line_styles = [
        (0, (1, 1)),
        (0, (5, 5)),
        (0, (3, 5, 1, 5)),
        (5, (10, 3)),
        (0, (3, 5, 1, 5, 1, 5)),
        (0, (5, 1)),
        (0, (3, 10, 1, 10)),
        (0, (3, 1, 1, 1)),
        (0, (3, 10, 1, 10, 1, 10)),
        (0, (3, 1, 1, 1, 1, 1)),
    ]

    for i, instance_data in enumerate(instance_data_array):
        plt.plot(
            extractTimeData(delta_time, instance_data),
            extractDataFromDictionaries(parameter[0], instance_data, parameter[2]),
            label=f"{instance_data['platform']}-{instance_data['instance_zone']}: {instance_data['instance_name']}",
            linewidth=2,
            linestyle=line_styles[i % len(line_styles)],
        )

    plt.xlim(0, 60)
    plt.xlabel("Time (s)", fontsize=16)
    plt.ylabel(f"{parameter[1]}", fontsize=16)
    plt.xticks(fontsize=14)
    plt.yticks(fontsize=14)
    plt.grid(True)
    plt.title(f"{convert_to_title(parameter[0])} Plot", fontsize=18)
    plt.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), fancybox=True, shadow=True, ncol=1)
    plt.subplots_adjust(left=0.15, right=0.95, top=0.9, bottom=0.35)
    plt.savefig(save_path)


def getDictionaryValue(pattern, output_string, group_number):
    """Extract one regex capture group from a line, returning empty string on miss."""
    if re.search(pattern, output_string) is None:
        return ""
    else:
        return re.search(pattern, output_string).group(group_number)


def find_delta_time(instance_data_array):
    """Find earliest sample timestamp across all instances."""
    delta_time = extractDataFromDictionaries("time_secs", instance_data_array[0], False)[0]
    for instance_data in instance_data_array:
        poss_delta = extractDataFromDictionaries("time_secs", instance_data, False)[0]
        if poss_delta < delta_time:
            delta_time = poss_delta
    return delta_time


def extractTimeData(delta_time, instance_data):
    """Return normalized time axis for one instance."""
    array_of_data = []

    for result in instance_data["results"]:
        if result["time_secs"] != "":
            array_of_data.append(float(result["time_secs"] - delta_time))
        else:
            array_of_data.append(0)

    return array_of_data


def turnToDictionary(output_string, time_idx, time_secs):
    """Parse one ss output line into normalized metric dictionary."""
    rto_pattern = r"rto:(\d+)"
    rtt_pattern = r"rtt:(\d+\.\d+)/(\d+\.\d+)"
    mss_pattern = r"mss:(\d+)"
    pmtu_pattern = r"pmtu:(\d+)"
    cwnd_pattern = r"cwnd:(\d+)"
    bytes_sent_pattern = r"bytes_sent:(\d+)"
    bytes_acked_pattern = r"bytes_acked:(\d+)"
    segs_out_pattern = r"segs_out:(\d+)"
    segs_in_pattern = r"segs_in:(\d+)"
    data_segs_out_pattern = r"data_segs_out:(\d+)"
    bw_pattern = r"bw:(\d+)bps"
    mrtt_pattern = r"mrtt:(\d+(\.\d*)?)"
    pacing_rate_pattern = r"pacing_rate (\d+)bps"
    delivered_pattern = r"delivered:(\d+)"
    unacked_pattern = r"unacked:(\d+)"
    rcv_space_pattern = r"rcv_space:(\d+)"
    rcv_ssthresh_pattern = r"rcv_ssthresh:(\d+)"
    notsent_pattern = r"notsent:(\d+)"
    minrtt_pattern = r"minrtt:(\d+\.\d+)"
    snd_wnd_pattern = r"snd_wnd:(\d+)"
    lastack_pattern = r"lastack:(\d+)"
    delivery_rate_pattern = r"delivery_rate (\d+)bps"

    item = {
        "time": time_idx,
        "time_secs": time_secs,
        "rto": getDictionaryValue(rto_pattern, output_string, 1),
        "rtt_avg": getDictionaryValue(rtt_pattern, output_string, 1),
        "rtt_min": getDictionaryValue(rtt_pattern, output_string, 2),
        "mss": getDictionaryValue(mss_pattern, output_string, 1),
        "pmtu": getDictionaryValue(pmtu_pattern, output_string, 1),
        "cwnd": getDictionaryValue(cwnd_pattern, output_string, 1),
        "bytes_sent": getDictionaryValue(bytes_sent_pattern, output_string, 1),
        "bytes_acked": getDictionaryValue(bytes_acked_pattern, output_string, 1),
        "segs_out": getDictionaryValue(segs_out_pattern, output_string, 1),
        "segs_in": getDictionaryValue(segs_in_pattern, output_string, 1),
        "data_segs_out": getDictionaryValue(data_segs_out_pattern, output_string, 1),
        "bw": getDictionaryValue(bw_pattern, output_string, 1),
        "mrtt": getDictionaryValue(mrtt_pattern, output_string, 1),
        "pacing_rate": getDictionaryValue(pacing_rate_pattern, output_string, 1),
        "delivered": getDictionaryValue(delivered_pattern, output_string, 1),
        "unacked": getDictionaryValue(unacked_pattern, output_string, 1),
        "rcv_space": getDictionaryValue(rcv_space_pattern, output_string, 1),
        "rcv_ssthresh": getDictionaryValue(rcv_ssthresh_pattern, output_string, 1),
        "notsent": getDictionaryValue(notsent_pattern, output_string, 1),
        "minrtt": getDictionaryValue(minrtt_pattern, output_string, 1),
        "snd_wnd": getDictionaryValue(snd_wnd_pattern, output_string, 1),
        "lastack": getDictionaryValue(lastack_pattern, output_string, 1),
        "delivery_rate": getDictionaryValue(delivery_rate_pattern, output_string, 1),
    }

    return item


def extractDataFromDictionaries(key_to_extract, instance_data, truncate):
    """Extract one metric series from parsed instance results."""
    array_of_data = []

    for result in instance_data["results"]:
        if result[key_to_extract] != "":
            if truncate:
                array_of_data.append(float(result[key_to_extract]) / 1000000)
            else:
                array_of_data.append(float(result[key_to_extract]))
        else:
            array_of_data.append(0)

    return array_of_data


def get_last_statistic_from_file(timestamp, instance, statistic, report_root=None):
    """Return last observed value of one statistic from one parsed file."""
    report_root = _resolve_report_root(report_root)
    filename = (
        f"{report_root}/{timestamp}/{instance['platform']}/{instance['instance_zone']}/"
        f"{instance['instance_name']}-({instance['congestion_control_algorithm']}).txt"
    )

    for line in reversed(list(open(filename, encoding="utf-8"))):
        line = line.strip()
        if line.startswith("skmem"):
            dictionary_result = turnToDictionary(line, 0, 0)
            return dictionary_result[statistic]


def get_statistic_from_single_output(output, statistic):
    """Extract one statistic from a live ss command output iterator."""
    for line in output:
        line = line.strip()
        if line.startswith("skmem"):
            dictionary_result = turnToDictionary(line, 0, 0)
            log.debug(dictionary_result)
            return dictionary_result[statistic]


def generate_data_array(timestamp, report_root=None):
    """Load all parsed per-instance text files for a timestamp into memory."""
    report_root = _resolve_report_root(report_root)
    print("Generating data array...")

    instance_data_array = []

    for platform_directory in glob.glob(f"{report_root}/{timestamp}/*/"):
        platform = os.path.basename(os.path.normpath(platform_directory))

        for zone_directory in glob.glob(os.path.join(platform_directory, "*")):
            zone = os.path.basename(os.path.normpath(zone_directory))

            for txt_file in glob.glob(os.path.join(zone_directory, "*.txt")):
                results_array = []

                with open(txt_file, encoding="utf-8") as f:
                    current_timestamp = 0
                    for line in f:
                        line = line.strip()
                        if line.startswith("#"):
                            current_timestamp += 1
                            time_secs = float(line[2:])
                        if line.startswith("skmem"):
                            dictionary_result = turnToDictionary(line, current_timestamp, time_secs)
                            results_array.append(dictionary_result)

                instance_dict = {
                    "platform": platform,
                    "instance_zone": zone,
                    "instance_name": os.path.basename(txt_file).split(".")[0],
                    "test_timestamp": timestamp,
                    "results": results_array,
                }

                instance_data_array.append(instance_dict)

    return instance_data_array


def create_graphs_directory(timestamp, report_root=None):
    """Create graphs output directory for one timestamp."""
    report_root = _resolve_report_root(report_root)
    print("Creating graphs directory...")

    output_directory = f"{report_root}/{timestamp}/graphs"
    os.makedirs(output_directory, exist_ok=True)


def generate_graph(timestamp, instance_data_array, parameter, report_root=None):
    """Generate and save one graph for one metric parameter."""
    report_root = _resolve_report_root(report_root)
    output_directory = f"{report_root}/{timestamp}/graphs"
    save_path = os.path.join(output_directory, f"{parameter[0]}.png")
    plot_data(instance_data_array, parameter, save_path)


def generate_statistic(timestamp, instance_data_array, parameter, report_root=None):
    """Append summary statistics for one metric parameter."""
    report_root = _resolve_report_root(report_root)
    statistics_directory = f"{report_root}/{timestamp}"

    statistics_file_path = os.path.join(statistics_directory, "statistics.txt")
    with open(statistics_file_path, "a", encoding="utf-8") as stats_file:
        stats_file.write("<=============================>\n")
        stats_file.write(f"PARAMETER: {parameter[0]}\n")
        for instance_data in instance_data_array:
            parameter_data = extractDataFromDictionaries(parameter[0], instance_data, parameter[2])
            mean_val = statistics.mean(parameter_data)
            median_val = statistics.median(parameter_data)
            stdev_val = statistics.stdev(parameter_data) if len(parameter_data) > 1 else 0.0
            stats_file.write(
                f"PLATFORM: {instance_data['platform']}\n"
                f"INSTANCE: {instance_data['instance_name']}\n"
                f"\tMean: {mean_val}\n"
                f"\tMedian: {median_val}\n"
                f"\tStd Dev: {stdev_val}\n\n"
            )


def generate_statistics(timestamp, instance_data_array, report_root=None):
    """Generate statistics.txt for all configured graph parameters."""
    report_root = _resolve_report_root(report_root)
    print(f"Generating statistics.txt to {report_root}/{timestamp}...")

    for graph_parameter in GRAPH_PARAMETERS:
        generate_statistic(timestamp, instance_data_array, graph_parameter, report_root=report_root)


def generate_graphs(timestamp, instance_data_array, report_root=None):
    """Generate all metric graphs for one timestamp."""
    report_root = _resolve_report_root(report_root)
    print(f"Generating graphs to {report_root}/{timestamp}...")

    for graph_parameter in GRAPH_PARAMETERS:
        generate_graph(timestamp, instance_data_array, graph_parameter, report_root=report_root)
