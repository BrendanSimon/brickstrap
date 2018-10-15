#!/bin/bash

## Exit on any error.
set -o errexit

##
## Make a runnable patch file from contents of a directory.
## Uses the `makeself` utility.
## 

ver="v0.12.0-rc1-buster"

upgrade_name="ind-efd-upgrade-${ver}"

upgrade_dir="${upgrade_name}"

upgrade_out="${upgrade_name}.run"

upgrade_desc="IND EFD Upgrade to '${ver}'"

upgrade_run="./run.sh"

upgrade_archive="ind-efd-${ver}.tar.gz"

prog_rel=$0
prog_abs=$(readlink -m ${prog_rel})
prog=$(basename ${prog_rel})
echo "DEBUG: prog_rel = '${prog_rel}'"
echo "DEBUG: prog_abs = '${prog_abs}'"
echo "DEBUG: prog     = '${prog}'"

#source_dir=$(dirname ${prog_rel})
source_dir=$(dirname ${prog_abs})
#source_dir=$(dirname ${prog})

##===========================================================================

echo "Making '${upgrade_desc}'"
if false ; then
    echo "    source_dir      = '${source_dir}'"
    echo "    upgrade_dir     = '${upgrade_dir}'"
    echo "    upgrade_run     = '${upgrade_run}'"
    echo "    upgrade_archive = '${upgrade_archive}'"
fi

## Make upgrade directory, copy in run script and other files.
echo "Create upgrade directory: '${upgrade_dir}'..."
rm --force --recursive "${upgrade_dir}"
mkdir --parents "${upgrade_dir}"

echo "Copying run script to upgrade directory..."
rsync "${source_dir}/${upgrade_run}" "${upgrade_dir}/"

echo "Copying upgrade archive to upgrade directory..."
rsync "${upgrade_archive}" "${upgrade_dir}/"

## Makeself
echo "Running 'makeself'..."
makeself ${upgrade_dir} ${upgrade_out} "${upgrade_desc}" ${upgrade_run}

echo "Finished making '${upgrade_desc}'"

##===========================================================================
