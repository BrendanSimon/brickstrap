#!/bin/bash
 
NOW=$(date +%Y%m%dT%H%M%S)

VERSION="0.10.1"
#VERSION="0.10.1-dev"
#VERSION="sepl-dev-${NOW}"
 
BOARD="ind-efd"
 
OUT="${BOARD}-v${VERSION}"
 
OUT_TAR="${OUT}.tar"
 
OUT_TGZ="${OUT_TAR}.gz"
 
BRICKSTRAP="../brickstrap/brickstrap.sh"

COMMAND=${1:-"all"}


read -r -d '' USAGE <<-'EOF'
  usage: ./build.sh <command>

  Commands
  --------
  create-conf          generate the multistrap.conf file
* simulate-multistrap  run multistrap with the --simulate option (for debugging)
  run-multistrap       run multistrap (creates rootfs and downloads packages)
  copy-root            copy files from board definition folder to the rootfs
  configure-packages   configure the packages in the rootfs
* run-hook <hook>      run a single hook in the board configuration folder
  run-hooks            run all of the hooks in the board configuration folder
* create-rootfs        run all of the above commands (except *) in order
  create-tar           create a tar file from the rootfs folder
  create-image         create a disk image file from the tar file
  create-report        run custom reporting script <board>/custom-report.sh
* shell                run a bash shell in the rootfs
* delete               deletes all of the files created by other commands
  all                  run all of the above commands (except *) in order
EOF


if [ -z "${COMMAND}" ]; then
    echo >&2 "${USAGE}"
    exit -1
fi

#
# Build everything.
# -b = board definition directory (looks in brickstrap source dir by default)
# -d = output directory (also used for .tar and .img filenames)
# -f = force build if output directory already exists.
#
 
echo "BOARD = ${BOARD}"
echo "OUT = ${OUT}"

${BRICKSTRAP} -b ${BOARD} -d ${OUT} -f ${COMMAND}
 
#
# Compress the tar image.
#
if [ "${COMMAND}" = "all" ]; then
    cat ${OUT_TAR} | gzip --best --rsyncable > ${OUT_TGZ}  
fi

