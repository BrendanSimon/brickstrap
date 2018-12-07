#!/bin/bash

## Exit on any error.
set -o errexit

#!
#! Make a runnable patch file from contents of a directory.
#! Uses the `makeself` utility.
#! 

ver_from="v0.11.1-rc3"

ver_to="v0.11.2"

patch_name="ind-efd-patch-${ver_from}-to-${ver_to}"

patch_dir="${patch_name}"

patch_out="${patch_name}.run"

patch_desc="IND EFD Patch from '${ver_from}' to '${ver_to}'"

patch_run="./run.sh"

prog_rel=$0
prog=$(basename ${prog_rel})

source_dir=$(dirname ${prog_rel})

#=============================================================================

echo "Making '${patch_desc}'"

makeself "${source_dir}/${patch_dir}" "${patch_out}" "${patch_desc}" "${patch_run}"

echo "Finished making '${patch_desc}'"

#=============================================================================

