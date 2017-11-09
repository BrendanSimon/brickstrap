#!/bin/bash

##
## Make a runnable patch file from contents of a directory.
## Uses the `makeself` utility.
## 

ver_from="v0.10.1"

ver_to="v0.10.2-dev"

patch_name="ind-efd-patch-${ver_from}-to-${ver_to}"

patch_dir="${patch_name}"

patch_out="${patch_name}.run"

patch_desc="IND EFD Patch from '${ver_from}' to '${ver_to}'"

patch_run="./run.sh"

echo "Making '${patch_desc}'"

makeself ${patch_dir} ${patch_out} "${patch_desc}" ${patch_run}

echo "Finished making '${patch_desc}'"

