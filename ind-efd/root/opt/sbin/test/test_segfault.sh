#!/bin/bash

##
## This script is used to try and exacerbate a segfault condition which
## appears to occur on systems that have been running for a long time.
##
## The theory is that Linux memory gets tight after a while (due to disk
## caching in system memory, as evident by the kernel buffers continually
## growing -- use `free` or `cat /proc/meminfo | grep Buffers`
##
## This script will write a large amount (>1GB) or random data to 
## a tempory file on the SD card (/mnt/data/tmp/test-segfault-data)
## which should quickly fill up the kernel buffers and force the kernel
## to start aging buffers, etc.
##

max_count=3

#data_file="/mnt/data/tmp/test_segfault_data"
data_file="./test_segfault_data"

## size of data file in block_size * counts.
data_bs="100M"
data_count=20

count=0
while [ ${count} -lt ${max_count} ] ; do
    let count=${count}+1
    echo "Writing random data to: ${data_file} (count = ${count})"
    time dd if=/dev/urandom of=${data_file} bs=${data_bs} count=${data_count} iflag=fullblock
    echo "Done. (count = ${count})"
    sleep 1
done

