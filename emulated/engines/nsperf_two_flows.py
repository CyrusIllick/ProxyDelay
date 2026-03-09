#!/usr/bin/python2
#
# Use netem, network namespaces, and veth virtual NICs
# to run a multi-flow TCP test on a single Linux machine.
#
# There is one network namespace for each emulated host.
# The emulated hosts are as follows:
#
#   srv: server (sender)
#   srvb: second server (sender)
#   srta: router for first server
#   srtb: router for second server
#   srt: server router router that connects both routers
#   mid: middle host to emulate delays and bandwidth constraints
#   crt: client router
#   cli: client (receiver)
#
# Most hosts have both a left ("l") and right ("r") virtual NIC.
# The server has only an "r" NIC and the client has only an "l" NIC.
#
# The topology is as follows:
# This is how I would like it to be 
#   +-------+    +------+  +-------+ +-------+ +-------+ +-------+
#   |  srv  |    | srta |  |  srt  | |  mid  | |  crt  | |  cli  |
#   |     r +-+--+l    r+--+l lb r +-+ l   r +-+ l   r +-+ l     |
#   +-------+    +---+--+  +---+--+ +-------+ +-------+ +-------+
#   +-------+              ----+---+ 
#   | srvb  |              |   r   | 
#   |    r  +-+------------+l srtb |
#   +-------+              --------+
# Code adapted from nsperf.py in the Google BBR repository:
#   https://github.com/google/bbr
# Original nsperf.py authors:
# Authors:
#  Neal Cardwell
#  Soheil Hassas Yeganeh
#  Kevin (Yudong) Yang
#  Arjun Roy

import os
import os.path
import socket
import sys
import threading
import time
import random

HOSTS = ['cli', 'crt', 'mid', 'srt', 'srv', 'srvb', 'srtb', 'srta']
IP_MODE = socket.AF_INET6
SS_INTERVAL_SECONDS = 0.1  # gather 'ss' stats each X seconds
FIRST_PORT = 10000         # first TCP port to use

# The latest version of 'ip', 'ss', and 'tc' binaries from iproute2, built by
# the ./configure.sh script:
IP_PATH = '/root/iproute2/iproute2/ip/ip'
SS_PATH = '/root/iproute2/iproute2/misc/ss'
TC_PATH = '/root/iproute2/iproute2/tc/tc'

# Function that finds where netperf is downloaded for when it needs to be called
def netperf():
    if os.path.isfile('./netperf'):
        return './netperf'
    else:
        return '/usr/bin/netperf'

# Function that finds where netserver is for when it needs to be called
def netserver():
    if os.path.isfile('./netserver'):
        return './netserver'
    else:
        return '/usr/bin/netserver'

# log stuff in tmp file and then at the end of test extract and copy the
# important stuff 
def log_dir():
    return '/tmp/'

# This function reall is just important for os.system(cmd) which 
# executes the command (which is a string) in a subshell. Falls the standard C 
# function system() and is just runs a command on the operating system
def run(cmd, verbose=True):
    if verbose:
        print('running: |%s|' % (cmd))
        sys.stdout.flush()
    status = os.system(cmd)
    if status != 0:
        sys.stderr.write('error %d executing: %s' % (status, cmd))

# Function that runs linux commands and returns the output
def run_and_grab(cmd, verbose=True):
    if verbose:
        print('running: |%s|' % (cmd))
        sys.stdout.flush()
    output_stream = os.popen(cmd)
    output = output_stream.read()
    output_stream.close()
    return output

# Needs to have TC_path and SS_path set up which should be working because of
# configure.sh script
def check_dependencies():
    """Check prerequisites for running this tool."""
    if (not os.path.isfile(SS_PATH) or not os.path.isfile(TC_PATH)):
        sys.stderr.write('nsperf.py: '
                         'please run ./configure.sh to install dependencies\n')
        sys.exit(1)


def cleanup():
    """Delete all veth pairs and all network namespaces."""
    for host in HOSTS:
        run(' ip netns exec %(host)s ip link del dev %(host)s.l ' % {'host': host})
        run(' ip netns exec %(host)s ip link del dev %(host)s.r ' % {'host': host})
        run(' ip netns exec %(host)s ip link del dev %(host)s.lb ' % {'host': host})
        run(' ip netns del %(host)s 2> /dev/null' % {'host': host})


def setup_logging():
    """Set up all logging."""
    # Zero out /var/log/kern-debug.log so that we only get our test logs.
    run('logrotate -f /etc/logrotate.conf')


def setup_namespaces():
    """Set up all network namespaces."""
    for host in HOSTS:
        run('ip netns add %(host)s' % {'host': host})


def setup_loopback():
    """Set up loopback devices for all namespaces."""
    for host in HOSTS:
        run('ip netns exec %(host)s ifconfig lo up' % {'host': host})


def setup_veth():
    """Set up all veth interfaces."""
    c = ''
    c += 'ip link add srvb.r type veth peer name srtb.l\n' 
    c += 'ip link add srtb.r type veth peer name srt.lb\n'
    c += 'ip link add srta.r type veth peer name srt.l\n'
    c += 'ip link add srv.r type veth peer name srta.l\n'
    c += 'ip link add srt.r type veth peer name mid.l\n'
    c += 'ip link add mid.r type veth peer name crt.l\n'
    c += 'ip link add crt.r type veth peer name cli.l\n'

    c += 'ip link set dev srta.r netns srta\n'
    c += 'ip link set dev srta.l netns srta\n'
    c += 'ip link set dev srvb.r netns srvb\n'
    c += 'ip link set dev srtb.l netns srtb\n'
    c += 'ip link set dev srtb.r netns srtb\n'
    c += 'ip link set dev srt.lb netns srt\n'
    c += 'ip link set dev srv.r netns srv\n'
    c += 'ip link set dev srt.r netns srt\n'
    c += 'ip link set dev srt.l netns srt\n'
    c += 'ip link set dev mid.r netns mid\n'
    c += 'ip link set dev mid.l netns mid\n'
    c += 'ip link set dev crt.l netns crt\n'
    c += 'ip link set dev crt.r netns crt\n'
    c += 'ip link set dev cli.l netns cli\n'

    c += 'ip netns exec srta ip link set srta.r up\n' 
    c += 'ip netns exec srta ip link set srta.l up\n'
    c += 'ip netns exec srtb ip link set srtb.r up\n'
    c += 'ip netns exec srtb ip link set srtb.l up\n'
    c += 'ip netns exec srvb ip link set srvb.r up\n'
    c += 'ip netns exec srt ip link set srt.lb up\n'
    c += 'ip netns exec srv ip link set srv.r up\n'
    c += 'ip netns exec srt ip link set srt.r up\n'
    c += 'ip netns exec srt ip link set srt.l up\n'
    c += 'ip netns exec mid ip link set mid.r up\n'
    c += 'ip netns exec mid ip link set mid.l up\n'
    c += 'ip netns exec crt ip link set crt.r up\n'
    c += 'ip netns exec crt ip link set crt.l up\n'
    c += 'ip netns exec cli ip link set cli.l up\n'

    # Disable TSO, GSO, GRO, or else netem limit is interpreted per
    # multi-MSS skb, not per packet on the emulated wire.
    c += 'ip netns exec srt ethtool -K srt.r tso off gso off gro off\n'
    c += 'ip netns exec mid ethtool -K mid.l tso off gso off gro off\n'
    c += 'ip netns exec mid ethtool -K mid.r tso off gso off gro off\n'
    c += 'ip netns exec crt ethtool -K crt.l tso off gso off gro off\n' 
    c += 'ip netns exec srt ethtool -K srt.lb tso off gso off gro off\n'  
    c += 'ip netns exec srt ethtool -K srt.l tso off gso off gro off\n'  
    c += 'ip netns exec srtb ethtool -K srtb.r tso off gso off gro off\n'
    c += 'ip netns exec srta ethtool -K srta.r tso off gso off gro off\n'
    c += 'ip netns exec srtb ethtool -K srtb.l tso off gso off gro off\n'
    c += 'ip netns exec srta ethtool -K srta.l tso off gso off gro off\n'

    # server
    c += 'ip netns exec srv ip addr add 192.168.0.1/24 dev srv.r\n'

    # second server
    c += 'ip netns exec srvb ip addr add 192.168.4.1/24 dev srvb.r\n' 
    
    # server router
    c += 'ip netns exec srt ip addr add 192.168.6.100/24 dev srt.l\n'
    c += 'ip netns exec srt ip addr add 192.168.1.1/24   dev srt.r\n'
    c += 'ip netns exec srt ip addr add 192.168.5.100/24 dev srt.lb\n'

    # server router b 
    c += 'ip netns exec srtb ip addr add 192.168.5.1/24 dev srtb.r\n'
    c += 'ip netns exec srtb ip addr add 192.168.4.100/24 dev srtb.l\n'

    # server router a 
    c += 'ip netns exec srta ip addr add 192.168.6.1/24 dev srta.r\n' 
    c += 'ip netns exec srta ip addr add 192.168.0.100/24 dev srta.l\n'

    # mid
    c += 'ip netns exec mid ip addr add 192.168.1.100/24 dev mid.l\n'
    c += 'ip netns exec mid ip addr add 192.168.2.1/24   dev mid.r\n'

    # client router
    c += 'ip netns exec crt ip addr add 192.168.2.100/24 dev crt.l\n'
    c += 'ip netns exec crt ip addr add 192.168.3.1/24   dev crt.r\n'

    # client
    c += 'ip netns exec cli ip addr add 192.168.3.100/24 dev cli.l\n'

    run(c)


def setup_routes(params):
    """Set up all routes."""
    c = ''

    # server
    c += 'h=srv\n'
    c += 'ip=' + IP_PATH + '\n'
    c += 'tc=' + TC_PATH + '\n'
    c += 'ip netns exec $h $tc qdisc add dev $h.r root fq\n'
    c += 'ip netns exec $h $ip route add default via 192.168.0.100 dev $h.r'
    if params['ecn_low']:
        c += ' features ecn_low'
    c += '\n'
    c += 'echo $h =================== ; ip netns exec $h $ip route show\n'
    
    # second server 
    c += 'h=srvb\n'
    c += 'ip netns exec $h $tc qdisc add dev $h.r root fq\n'
    c += 'ip netns exec $h $ip route add default via 192.168.4.100 dev $h.r\n'
    c += 'echo $h ==================== ; ip netns exec $h $ip route show\n'

    # server router
    c += 'h=srt\n'
    c += 'ip netns exec $h ip route add 192.168.0.0/24 via 192.168.6.1\n'  
    c += 'ip netns exec $h ip route add 192.168.4.0/24 via 192.168.5.1\n'  
    c += 'ip netns exec $h ip route add default via 192.168.1.100 dev $h.r\n'
    c += 'echo $h =================== ; ip netns exec $h $ip route show\n'

    #server router b 
    c += 'h=srtb\n'
    # c += 'ip netns exec $h $tc qdisc add dev $h.r root netem delay 100ms\n'
    c += 'ip netns exec $h ip route add default via 192.168.5.100 dev $h.r\n'
    c += 'echo $h =================== ; ip netns exec $h $ip route show\n'

    #server router a 
    c += 'h=srta\n'
    # c += 'ip netns exec $h $tc qdisc add dev $h.r root netem delay 100ms\n'
    c += 'ip netns exec $h ip route add default via 192.168.6.100 dev $h.r\n'
    c += 'echo $h =================== ; ip netns exec $h $ip route show\n'

    # mid
    c += 'h=mid\n'
    c += 'ip netns exec $h ip route add 192.168.3.0/24 via 192.168.2.100\n'
    c += 'ip netns exec $h ip route add default via 192.168.1.1 dev $h.l\n'
    c += 'echo $h =================== ; ip netns exec $h $ip route show\n'

    # client router
    c += 'h=crt\n'
    c += 'ip netns exec $h ip route add default via 192.168.2.1 dev $h.l\n'
    c += 'echo $h =================== ; ip netns exec $h $ip route show\n'

    # cli
    c += 'h=cli\n'
    c += 'ip netns exec $h ip route add default via 192.168.3.1 dev $h.l\n'
    c += 'echo $h =================== ; ip netns exec $h $ip route show\n'
    
    run(c)


def setup_forwarding():
    """Enable forwarding in each namespace."""
    for host in HOSTS:
        run('ip netns exec %(host)s sysctl -q -w '
            'net.ipv4.ip_forward=1 '
            'net.ipv6.conf.all.forwarding=1' % {'host': host})


def netem_limit(rate, delay, buf):
    """Get netem limit in packets.

    Needs to hold the packets in emulated pipe and emulated buffer.
    """
    bdp_bits = (rate * 1000000.0) * (delay / 1000.0)
    bdp_bytes = bdp_bits / 8.0
    bdp = int(bdp_bytes / 1500.0)
    # limit = bdp + buf
    limit = buf
    return limit


# Parse string like 'cubic:1,bbr:2' and return an array like:
# ['cubic', 'bbr', 'bbr']
def parse_cc_param(param_string):
    """Expand a compact CC spec (for example: 'bbr1:1,bbr:1') into a per-flow list."""
    cc_list = []
    groups = param_string.split(',')
    for group in groups:
        (cc_name, count) = group.split(':')
        count = int(count)
        for i in range(0, count):
            cc_list.append(cc_name)
    return cc_list


def get_params():
    """Read and validate runtime parameters from environment variables.

    Wrapper scripts in ../scripts export these variables before invoking this
    engine, so this function acts as the single runtime contract for test
    configuration.
    """
    # Invocations of this tool should set the following parameters as
    # environment variables.
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
        'pcap':         0, # bytes per packet to capture; 0 for no tracing #just guessing with the value 100
        'ecn_low':      0, # set ip route features ecn_low on server?
        'mem':          0, # set netperf memory buffer sizes to this value
        'a_delay':      0, # delay for route srva -- client
        'b_delay':      0, # delay for route srvb --> client
        'proxy_init':   0, # value of the proxy delay
        'proxy_on':     0, # boolean to indicate if proxy is on 
    }

    for key in params.keys():
        print('parsing key %s' % key)
        if key in os.environ:
           print('looking at env var with key %s, val %s' % (key, os.environ[key]))
        else:
           print('no env var with key %s' % (key))
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

    print(params)
    params['netperf'] = netperf()
    params['receiver_ip'] = '192.168.3.100'
    return params


# Put bandwidth rate limiting using HTB, tied to user-specified
# queuing discipline at that bottleneck, on traffic coming in the cli.l device.
def setup_htb_and_qdisc(d):
    """Set up HTB for rate limiting, and user-specified qdisc for the queue."""

    c = ''

    # First load the necessary modules.
    c += ('rmmod ifb\n'
          'modprobe ifb numifbs=10\n'
          'modprobe act_mirred\n')

    # Clear old queuing disciplines (qdisc) on the interfaces
    d['ext']         = 'cli.l'
    d['ext_ingress'] = 'cli.ifb0'
    d['host'] = 'cli'
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc del dev %(ext)s root\n') % d
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc del dev %(ext)s ingress\n') % d
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc del dev %(ext_ingress)s root\n') % d
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc del dev %(ext_ingress)s ingress\n') % d

    # Create ingress ifb0 on client interface.
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc add dev %(ext)s handle ffff: ingress\n') % d
    c += ('ip netns exec %(host)s '
          'ip link add %(ext_ingress)s type ifb\n') % d
    c += ('ip netns exec %(host)s '
          'ip link set dev %(ext_ingress)s up\n') % d
    c += ('ip netns exec %(host)s '
          'ifconfig %(ext_ingress)s txqueuelen 128000\n') % d
    c += ('ip netns exec %(host)s '
          'ifconfig %(ext_ingress)s\n') % d

    # Forward all ingress traffic to the IFB device.
    c += ('ip netns exec %(host)s '
          '%(tc)s filter add dev %(ext)s parent ffff: protocol all u32 '
          'match u32 0 0 action mirred egress redirect '
          'dev %(ext_ingress)s\n') % d

    # Create an egress filter on the IFB device.
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc add dev %(ext_ingress)s root handle 1: '
          'htb default 11\n') % d

    # Add root class HTB with rate limiting.
    c += ('ip netns exec %(host)s '
          '%(tc)s class add dev %(ext_ingress)s parent 1: classid 1:11 '
          '  htb rate %(IRATE)sMbit ceil %(IRATE)sMbit\n') % d

    # Add qdisc for downstream bottleneck.
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc add dev %(ext_ingress)s parent 1:11 handle 20: '
          '%(QDISC)s\n') % d

    c += ('ip netns exec %(host)s %(tc)s -stat qdisc show\n') % d

    return c


def setup_netem(params):
    """Set up bottleneck shaping and per-path delays with netem.

    The central bottleneck queue is configured on crt.* interfaces. Path delay
    asymmetry is configured on srta/srtb, and optional proxy delay is applied
    on the return direction when proxy_on=1.
    """

    d = {}

    # Parameters for data direction.
    d['IRATE']   = params['bw']      # Mbit/sec
    d['IDELAY']  = params['rtt'] / 2 # ms
    d['IBUF']    = params['buf']     # packets
    d['ILOSS']   = params['loss']
    d['IREO']    = 0  
    d['ILIMIT'] = netem_limit(rate=d['IRATE'], delay=d['IDELAY'], buf=d['IBUF'])
    d['POLICER'] = params['policer'] # Mbit/sec
    d['QDISC']   = params['qdisc']
    d['a_delay'] = params['a_delay']
    d['b_delay'] = params['b_delay']
    d['proxy_init'] = params['proxy_init']
    d['proxy_on'] = params['proxy_on']

    # Parameters for ACK direction.
    d['ORATE']  = 1000 # Mbit/sec; 
    d['ODELAY'] = params['rtt'] / 2 # ms
    d['OBUF']   = 1000 # packets;
    d['OLOSS']  = 0  
    d['OREO']   = 0  
    d['OLIMIT'] = netem_limit(rate=d['ORATE'], delay=d['ODELAY'], buf=d['OBUF'])

    d['tc'] = TC_PATH

    c = ''

    if d['QDISC'] == '':
        # If the user doesn't need a fancy qdisc, and FIFO will do,
        # then use netem for rate limiting and buffering,
        # since netem seems more accurate than HTB.
        d['INETEM_RATE'] = 'rate %(IRATE)sMbit' % d
    else:
        d['INETEM_RATE'] = ''
        d['ILIMIT'] = '%d' % (2*1000*1000*1000) # buffer is in user's qdisc

    # Inbound from sender -> receiver. Downstream rate limiting is on cli.l.
    d['host'] = 'crt'
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc add dev %(host)s.r root netem '
          'limit %(ILIMIT)s '
          'loss random %(ILOSS)s%% %(INETEM_RATE)s\n') % d

    # Outbound from receiver -> sender.
    d['host'] = 'crt'
    c += ('ip netns exec %(host)s '
          '%(tc)s qdisc add dev %(host)s.l root netem '
          'limit %(OLIMIT)s '
          'loss random %(OLOSS)s%% '
          'rate %(ORATE)sMbit\n') % d

    c += ('ip netns exec %(host)s %(tc)s -stat qdisc show\n') % d
    
    d['host'] = 'srtb'
    c += ('ip netns exec %(host)s '
         '%(tc)s qdisc add dev %(host)s.l root netem '
         'limit %(OLIMIT)s delay %(b_delay)sms %(IREO)sms '
         'loss random %(ILOSS)s%% '
         'rate 1000Mbit\n') % d

    c += ('ip netns exec %(host)s %(tc)s -stat qdisc show\n') % d

    d['host'] = 'srta'
    c += ('ip netns exec %(host)s '
         '%(tc)s qdisc add dev %(host)s.l root netem '
         'limit %(OLIMIT)s delay %(a_delay)sms %(IREO)sms '
         'loss random %(ILOSS)s%% '
         'rate 1000Mbit\n') % d

    #srv routers added delay on return starts at zero, extra dealy will be added in when minRTT values come in
    #adding in new artificial delay based on min rtt measurements
    if(d['proxy_on'] == 1):
        d['host'] = 'srtb'
        c += ('ip netns exec %(host)s '
            '%(tc)s qdisc add dev %(host)s.r root netem '
            'delay %(proxy_init)sms '
            'limit %(ILIMIT)s '
            'loss random %(ILOSS)s%% '
            'rate 1000Mbit\n') % d

    c += ('ip netns exec %(host)s %(tc)s -stat qdisc show\n') % d
    if(d['proxy_on'] == 1):
        d['host'] = 'srta'
        c += ('ip netns exec %(host)s '
            '%(tc)s qdisc add dev %(host)s.r root netem '
            'delay %(proxy_init)sms '
            'limit %(ILIMIT)s '
            'loss random %(ILOSS)s%% '
            'rate 1000Mbit\n') % d

    c += ('ip netns exec %(host)s %(tc)s -stat qdisc show\n') % d

    if (d['QDISC'] != ''):
        c += setup_htb_and_qdisc(d)

    run(c)

def ss_log_thread(params):
    """Collect periodic TCP/socket snapshots during the test run.

    Output is appended to ss.log and queue.log under outdir and timestamped so
    downstream parsers can align stats with test time.
    """
    dur = params['dur']
    outdir = params['outdir']
    ss_log_path = os.path.join(outdir, 'ss.log')
    receiver_ip = params['receiver_ip']
    num_conns = len(params['cc'])

    queue_log_path = os.path.join(outdir, 'queue.log')
    # ONLY USE THIS IF USING CODEL QUEUE
    # codel_log_path = os.path.join(outdir, 'codel.log')


    t0 = time.time()
    t = t0
    port_cnt = num_conns
    f = open(ss_log_path, 'w')
    f.truncate()
    f.close()
    f = open(queue_log_path, 'w')
    f.truncate()
    f.close()

    # f = open(codel_log_path, 'w')
    # f.truncate()
    # f.close()

    if IP_MODE == socket.AF_INET6:
        ss_ip = '[%s]'
    else:
        ss_ip = '%s'
    ss_ip %= receiver_ip
    ss_cmd = ('ip netns exec srv '
              '%s -tinmo "dport >= :%d and dport < :%d and dst %s" >> %s' % (
                  SS_PATH,
                  FIRST_PORT, FIRST_PORT + port_cnt, ss_ip, ss_log_path))


    ss_cmd_2 = ('ip netns exec srvb '
              '%s -tinmo "dport >= :%d and dport < :%d and dst %s" >> %s' % (
                  SS_PATH,
                  FIRST_PORT+1, FIRST_PORT + 1 + port_cnt, ss_ip, ss_log_path))


    ss_cmd_3 =  ('ip netns exec crt %s -stat qdisc show | tail -n 1 >> %s' % (TC_PATH, queue_log_path))

    # ONLY USE IF USING CODEL QUEUE
    # ss_cmd_4 =  ('ip netns exec cli %s -stat qdisc show | tail -n 4 >> %s' % (TC_PATH, codel_log_path))

    while t < t0 + dur:
        f = open(ss_log_path, 'a')
        f.write('# %f\n' % (time.time(),))
        f.close()
        f = open(queue_log_path, 'a')
        f.write('# %f\n' % (time.time(),))
        f.close()
        # ONLY FOR CODEL: 
        # f = open(codel_log_path, 'a')
        # f.write('# %f\n' % (time.time(),))
        # f.close()
        run(ss_cmd, verbose=False)
        run(ss_cmd_2, verbose=False)
        run(ss_cmd_3, verbose=False)
        # run(ss_cmd_4, verbose=False) #ONLY FOR CODEL QUEUE
        t += SS_INTERVAL_SECONDS
        to_sleep = t - time.time()
        if to_sleep > 0:
            time.sleep(to_sleep)

def launch_ss(params):
    t = threading.Thread(target=ss_log_thread, args=(params,))
    t.start()
    return t

def sender_proxy_thread(host, router, dur, port, proxy_init, receiver_ip):
    """Adaptive sender-side proxy delay control loop.

    The thread samples mrtt from ss output once per second and updates the
    router netem delay on the return path to track the configured proxy target.
    """
    d = {}
    d['tc'] = TC_PATH
    d['ILIMIT'] = '%d' % (20*1000) # buffer is in user's qdisc

    t0 = time.time()
    t = t0

    if IP_MODE == socket.AF_INET6:
        ss_ip = '[%s]'
    else:
        ss_ip = '%s'

    ss_ip %= receiver_ip
    
    ss_cmd = ('ip netns exec %s '
              '%s -tinmOH "dport >= :%d and dport < :%d and dst %s"' % (
                  host, SS_PATH,
                  port, port + 1, ss_ip))

    initial_proxy = int(proxy_init)
    set_del = initial_proxy
    cur = initial_proxy
    min_seen = [set_del] * 5
    pidx = 0
    actual = 0
    prev_set_del = set_del
    prev_min_rtt = 0
    while t < t0 + dur:
        ssa = run_and_grab(ss_cmd, verbose=False)
        minRTT = ssa[ssa.find('mrtt')+5:]
        # print("ss value value before entering the loop for host %s = %s" % (host, ssa))
        c = ''
        if(minRTT != ''): minRTT = int(float(minRTT[:minRTT.find(',')]))
        if(minRTT != 0 and minRTT != ''):
            # -------- VERSION 1 -------- #
            actual = minRTT - cur
            min_seen[pidx % 5] = actual
            to_change = set_del - cur - min(min_seen)
            if((to_change > 3 or to_change < -3) and (actual > 0) and (cur + to_change > 0)):
                cur += to_change
                d['host'] = router 
                d['minRTT'] = cur
                c += ('ip netns exec %(host)s '
                    '%(tc)s qdisc change dev %(host)s.r root netem '
                    'limit %(ILIMIT)s '
                    'delay %(minRTT)sms '
                    'rate 1000Mbit\n') % d

            # -------- VERSION 2 -------- #
            # prev_set_del = set_del
            # if(set_del > initial_proxy / 2):
            #     set_del -= 10 
            # if(prev_min_rtt == 0):
            #     prev_min_rtt = minRTT 
            # actual = prev_min_rtt - cur
            # prev_min_rtt = minRTT
            # print("")
            # print("minRTT seen for %s = %s" % (host, minRTT))
            # print("current add for %s = %s" % (host, cur))
            # print("Actual rtt for %s = %s" % (host, actual))
            # print("")
            # if(actual < 0): actual = 0 
            # min_seen[pidx % 5] = actual
            # to_change = prev_set_del - cur - min(min_seen)

            # if((to_change > 3 or to_change < -3) and (actual > 0) and (cur + to_change > 0)):
            #     cur += to_change
            #     d['host'] = router 
            #     d['minRTT'] = cur
            #     c += ('ip netns exec %(host)s '
            #         '%(tc)s qdisc change dev %(host)s.r root netem '
            #         'limit %(ILIMIT)s '
            #         'delay %(minRTT)sms '
            #         'rate 1000Mbit\n') % d
        pidx += 1
        run(c)
        t += 1  #run this command every t seconds
        to_sleep = t - time.time()
        if to_sleep > 0:
            time.sleep(to_sleep)

def launch_sender_proxy_thread(host, router, port, params):
    proxy_init = params['proxy_init']
    dur = params['dur']
    receiver_ip = params['receiver_ip']
    t = threading.Thread(target=sender_proxy_thread, args=(host, router, dur, port, proxy_init, receiver_ip))
    return t

def run_test(params):
    """Run one two-flow test case and write all raw artifacts to outdir.

    Expected invocation is:
      python nsperf_two_flows.py stream
    """
    print('command: %s' % (sys.argv))
    run('uname -a; date; uptime')

    # Configure sender namespaces.
    run('ip netns exec srv bash -c "%s"' % params['cmd'])

    # Trying to configure the other sender namespace
    run('ip netns exec srvb bash -c "%s"' % params['cmd'])

    # Configure receiver namespace.
    run('ip netns exec cli bash -c "%s"' % params['cmd'])

    # Set up receiver process.
    run('pkill -f netserver')
    run('ip netns exec cli %s -N' % (netserver()))

    time.sleep(1) #adding this in to see if this will allow for enough time after the netserver starts

    # Set up output directory.
    outdir = params['outdir']
    run('mkdir -p %s' % outdir)

    # Set up sender-side packet capture.
    if params['pcap'] > 0:
        snaplen = params['pcap']
        path = os.path.join(outdir, 'out.pcap')
        run('ip netns exec srv tcpdump -i srv.r -s %(snaplen)d -w %(path)s &' %
            {'path': path, 'snaplen': snaplen})
        time.sleep(1)  # wait for tcpdump to come up

    # Set up periodic sender-side 'ss' stat capture.
    ss_thread = launch_ss(params)
    
    proxy_a_thread = launch_sender_proxy_thread('srv', 'srta', FIRST_PORT, params)
    proxy_b_thread = launch_sender_proxy_thread('srvb', 'srtb', FIRST_PORT+1, params)
    if(params['proxy_on'] == 1):
        proxy_a_thread.start()
        proxy_b_thread.start()
    if sys.argv[1] == 'stream':
        num_conns = len(params['cc'])
        print('num_conns = %d' % (num_conns))
        t0 = time.time()
        t = t0
        # Two-flow generalized mode:
        # - If one CC is provided, both flows use it (backward-compatible).
        # - If two CCs are provided, flow A (srv) uses cc[0] and flow B (srvb) uses cc[1].
        cc_a = params['cc'][0]
        cc_b = params['cc'][1] if len(params['cc']) > 1 else params['cc'][0]
        #NOTE: Right now this code only works if there is one flow coming from each server
        conn_params = params.copy()
        conn_params['bg'] = '&'  # all but the last in the background
        conn_params['cc'] = cc_a
        conn_params['port'] = FIRST_PORT + 0
        conn_params['outfile'] = '%s/netperf.out.a.txt' % (outdir)
        conn_params['bg'] = '&' #setting the first srv to be background and the second srv to be in foreground
        if params['mem']:
            conn_params['memflags'] = (
                '-s %(mem)s,%(mem)s -S %(mem)s,%(mem)s ' %
                params)
        else:
            conn_params['memflags'] = ''
        run('ip netns exec srv %(netperf)s '
            '-l %(dur)d -H %(receiver_ip)s -- -k THROUGHPUT %(memflags)s'
            '-K %(cc)s -P %(port)s '
            '> %(outfile)s '
            '%(bg)s' % conn_params)

        t += params['interval']
        to_sleep = t - time.time()
        if to_sleep > 0:
            time.sleep(to_sleep)

        conn_params['bg'] = ''  
        conn_params['port'] = FIRST_PORT + 1
        conn_params['outfile'] = '%s/netperf.out.b.txt' % (outdir)
        conn_params['cc'] = cc_b
        run('ip netns exec srvb %(netperf)s '
            '-l %(dur)d -H %(receiver_ip)s -- -k THROUGHPUT %(memflags)s'
            '-K %(cc)s -P %(port)s '
            '> %(outfile)s '
            '%(bg)s' % conn_params)

        
    elif sys.argv[1] == 'rr':
        params['request_size'] = (10 + 20 + 40 + 80 + 160) * 1448
        params['test'] = sys.argv[2]
        conn_params['port'] = FIRST_PORT
        run('ip netns exec srv %(netperf)s '
            ' -P 0 -t %(test)s -H %(receiver_ip)s -- '
            '-K %(cc)s -P %(port)s '
            '-r %(request_size)d,1 '
            '-o P50_LATENCY,P90_LATENCY,P99_LATENCY,MAX_LATENCY,'
            'TRANSACTION_RATE,'
            'LOCAL_TRANSPORT_RETRANS,REMOTE_TRANSPORT_RETRANS' % params)
    else:
        sys.stderr.write('unknown test type argument: %s\n' % sys.argv[1])
        sys.exit(1)

    ss_thread.join()
    if(params['proxy_on'] == 1):
        proxy_b_thread.join()
        proxy_a_thread.join()

    run('killall tcpdump')

    run('ls -l /tmp/*.gz')
    run('cp -af /var/log/kern-debug.log ' + outdir)
    run('rm -f ' + outdir + '/*.gz')
    run('ls -l /tmp/*.gz')
    run('gzip '  + outdir + '/kern-debug.log')
    run('gzip  ' + outdir + '/out.pcap')
    run('ls -l /tmp/*gz')

def print_banner(message):
    print("\n\n\n")
    print("****************")
    print(message)
    print("****************")
    print("\n")

def main():
    """Execute full namespace setup -> run -> cleanup lifecycle."""
    print_banner("Checking Dependencies")
    check_dependencies()

    print_banner("Getting Params")
    params = get_params()

    print_banner("Pre test Cleanup")
    cleanup()

    print_banner("Setup Logging")
    setup_logging()

    print_banner("Setup Namespaces")
    setup_namespaces()

    print_banner("Setup Loopback")
    setup_loopback()

    print_banner("Setup Virtual Ethernet Ports")
    setup_veth()

    print_banner("Setup Routes")
    setup_routes(params)

    print_banner("Setup Forwarding")
    setup_forwarding()

    print_banner("Setup Netem")
    setup_netem(params)

    print_banner("Run Tests")
    run_test(params)

    print_banner("Post Test Cleanup")
    cleanup()

    print_banner("Killing netserver")
    run('killall -w netserver') 

    return 0


if __name__ == '__main__':
    sys.exit(main())
