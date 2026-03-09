"""Write human-readable per-run summary metadata."""

import os

from config_loader import get_report_root


def create_summary(test_id, username, flow_direction, test_length, instances, timestamp, report_root=None):
    """Persist summary.txt for one test run."""
    report_root = report_root or get_report_root()
    print(f"Generating summary to {report_root}/{timestamp}/summary.txt")

    reports_directory_for_this_test = f"{report_root}/{timestamp}"
    os.makedirs(reports_directory_for_this_test, exist_ok=True)

    summary_file_path = os.path.join(reports_directory_for_this_test, "summary.txt")
    with open(summary_file_path, "a", encoding="utf-8") as summary_file_pointer:
        summary_file_pointer.write("<=============================>\n")
        summary_file_pointer.write(f"TIMESTAMP: {timestamp}\n")
        summary_file_pointer.write(f"TEST ID: {test_id}\n")
        summary_file_pointer.write(f"USERNAME: {username}\n")
        summary_file_pointer.write(f"FLOW DIRECTION: {flow_direction}\n")
        summary_file_pointer.write(f"TEST DURATION: {test_length}\n")
        summary_file_pointer.write("INSTANCES:\n")
        for instance in instances:
            summary_file_pointer.write(f"{instance}\n")
