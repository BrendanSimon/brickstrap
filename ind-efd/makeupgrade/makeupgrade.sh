#!/bin/bash

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

echo "Making '${upgrade_desc}'"

makeself ${upgrade_dir} ${upgrade_out} "${upgrade_desc}" ${upgrade_run}

echo "Finished making '${upgrade_desc}'"

