#!/bin/sh

#!=============================================================================
#!  EFD logrotate script
#!  Customised version of /usr/bin/logrotate.sh
#!=============================================================================

# skip in favour of systemd timer
if [ -d /run/systemd/system ]; then
    exit 0
fi

# this cronjob persists removals (but not purges)
if [ ! -x /usr/sbin/logrotate ]; then
    exit 0
fi

/usr/sbin/logrotate /etc/logrotate-efd.conf
EXITVALUE=$?
if [ $EXITVALUE != 0 ]; then
    /usr/bin/logger -t efd_logrotate "ALERT exited abnormally with [$EXITVALUE]"
fi
exit $EXITVALUE
