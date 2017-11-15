#!/bin/bash

## Exit on any error.
set -o errexit

##
## Make a runnable patch file from contents of a directory.
## Uses the `makeself` utility.
## 

ver="v0.10.2"

upgrade_name="ind-efd-upgrade-${ver}"

upgrade_dir="${upgrade_name}"

upgrade_out="${upgrade_name}.run"

upgrade_desc="IND EFD Upgrade to '${ver}'"

upgrade_run="./run.sh"

upgrade_archive="ind-efd-${ver}.tar.gz"

prog_rel=$0
prog=$(basename ${prog_rel})

source_dir=$(dirname ${prog_rel})

##===========================================================================

echo "Making '${upgrade_desc}'"

## Make upgrade directory, copy in run script and other files.
rm --force --recursive "${upgrade_dir}"
mkdir --parents "${upgrade_dir}"
rsync "${source_dir}/${upgrade_run}" "${upgrade_dir}/"
rsync "${upgrade_archive}" "${upgrade_dir}/"

## Makeself
makeself ${upgrade_dir} ${upgrade_out} "${upgrade_desc}" ${upgrade_run}

echo "Finished making '${upgrade_desc}'"

##===========================================================================

