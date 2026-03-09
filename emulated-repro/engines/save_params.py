import os
import os.path
import socket
import sys
import threading 
import time

def main():
    print("Parameters used in this test.\n")
    params = get_params()
    print()
    print()
    for pk, pv in params.items():
        print(f"{pk}: {pv}")

def parse_cc_param(param_string):
    cc_list = []
    groups = param_string.split(',')
    for group in groups:
        (cc_name, count) = group.split(':')
        count = int(count)
        for i in range(0, count):
            cc_list.append(cc_name)
    return cc_list

def get_params():
    params = {
        'bw':          -1, # input bottleneck bw in Mbit/sec; required
        'rtt':         -1, # RTT in ms; required
        'buf':         -1, # input bottleneck buffer in packets; required
        'loss':         0, # input bottleneck loss rate in percent; optional
        'policer':      0, # input bottleneck policer rate, Mbit/sec; optional
        'cc':          '', # congestion control algorithm: required
        'interval':     0, # interval between flow starts, in secs; optional
        'dur':         -1, # length of test in secs: required
        'outdir':      '', # output directory for results
        'qdisc':       '', # qdisc at downstream bottleneck (empty for FIFO)
        'cmd':         '', # command to run (e.g. set sysctl values)
        'pcap':         100, # bytes per packet to capture; 0 for no tracing #just guessing with the value 100
        'ecn_low':      0, # set ip route features ecn_low on server?
        'mem':          0, # set netperf memory buffer sizes to this value
        'extra_delay':   0,
        'a_delay':      0,
        'b_delay':      0,
        'c_delay':      0,
        'd_delay':      0,
        'e_delay':      0,
        'f_delay':      0,
        'g_delay':      0,
        'h_delay':      0,
        'i_delay':      0,
        'j_delay':      0,
        'proxy_init':      0,
        'proxy_on':     0
    }

    for key in params.keys():
        if key not in os.environ:
            if params[key] != 0:
              sys.stderr.write('missing %s in environment variables\n' % key)
              sys.exit(1)
        elif key == 'cc':
            params[key] = parse_cc_param(os.environ[key])
        elif type(params[key]) == str:
            params[key] = os.environ[key]
        else:
            params[key] = float(os.environ[key])

    params['receiver_ip'] = '192.168.3.100'
    return params

        


if __name__ == "__main__":
    main()
