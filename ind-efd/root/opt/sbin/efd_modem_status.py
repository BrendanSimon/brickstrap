#!/usr/bin/env python2

import subprocess
import shlex
import re
import sys

def run():
    ##
    ## Get a list of all modems (should always be 1)
    ##
    modem_list_cmd = 'mmcli -L'
    args = shlex.split(modem_list_cmd)

    output = subprocess.check_output(args)

    lines = output.split('\n')
    modem_line = [ x for x in lines if 'ModemManager' in x ]

    ##
    ## Extract modem number from output
    ##
    modem = modem_line[0].split()[0].split('/')[-1]

    print("Modem Number: {}".format(modem))

    ##
    ## Get status for the modem.
    ##
    modem_status_cmd = 'mmcli -m {}'.format(modem)
    args = shlex.split(modem_status_cmd)
    output = subprocess.check_output(args)

    ##
    ## Extract info of interest.
    ##
    lines = output.split('\n')
    pattern = r'|'.join([r'state:', r'quality:'])
    regex = re.compile(pattern)
    modem_status = [ s for s in lines if regex.findall(s) ]
    modem_status = '\n'.join(modem_status)

    print("{}".format(modem_status))

    sys.stdout.flush()

#!============================================================================

if __name__ == "__main__":
    argh.dispatch_command(run)

