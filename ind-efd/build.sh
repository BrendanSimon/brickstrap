#!/bin/bash

NOW=$(date +%Y%m%dT%H%M%S)

VERSION="0.12.2-rc1"
#VERSION="sepl-dev-${NOW}"

BOARD="ind-efd"

OUT="${BOARD}-v${VERSION}"
ROOT="${BOARD}-root-v${VERSION}"
BOOT="${BOARD}-boot-v${VERSION}"
DATA="${BOARD}-data-v${VERSION}"

OUT_LOG="${OUT}.log"

OUT_TXT="${OUT}.txt"

OUT_TAR="${OUT}.tar"

ROOT_TAR="${ROOT}.tar"
ROOT_TGZ="${ROOT_TAR}.gz"

BOOT_TAR="${BOOT}.tar"
BOOT_TGZ="${BOOT_TAR}.gz"

DATA_TAR="${DATA}.tar"
DATA_TGZ="${DATA_TAR}.gz"

BRICKSTRAP="../brickstrap/brickstrap.sh"

COMMAND=${@:-"all"}

#! could use `mktemp` here
TMP_DIR="_tmp_dir_"

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

echo "BOARD    = ${BOARD}"
#echo "OUT      = ${OUT}"
#echo "OUT_TAR  = ${OUT_TAR}"
#echo "ROOT     = ${ROOT}"
#echo "ROOT_TAR = ${ROOT_TAR}"
echo "ROOT_TGZ = ${ROOT_TGZ}"
#echo "BOOT     = ${BOOT}"
#echo "BOOT_TAR = ${BOOT_TAR}"
echo "BOOT_TGZ = ${BOOT_TGZ}"
#echo "DATA     = ${DATA}"
#echo "DATA_TAR = ${DATA_TAR}"
echo "DATA_TGZ = ${DATA_TGZ}"

#! exit immediately on any errors
set -e

case "${COMMAND}" in
    "all" | "run-multistrap" | "create-tar" | "shell" )
        #! run brickstrap script to generate ${OUT_TAR} => ${ROOT_TAR}
        cmd="${BRICKSTRAP} -b ${BOARD} -d ${OUT} -f ${COMMAND}"
        script -q -c "${cmd}" "${OUT_LOG}"
        mv "${OUT_TAR}" "${ROOT_TAR}"

        #! Remove ANSI color codes, etc
        cat "${OUT_LOG}" | sed "s,\x1B\[[0-9;]*[a-zA-Z],,g" > "${OUT_TXT}"
        ;;
esac

#
# Make boot filesystem image.
# Make data filesystem image.
# Compress the root filesystem image.
# Make upgrade script.
# Remove tar image (to save space)
#
case "${COMMAND}" in
    "all" | "post" )
        #! Make boot filesystem image (extract `/boot/flash/*` from rootfs image)
        echo "extract and compress boot fs => ${DATA_TGZ}"
        rm -rf "${TMP_DIR}" && mkdir -p "${TMP_DIR}"
        tar -x --strip-components=3 -f "${ROOT_TAR}" -C "${TMP_DIR}" "./boot/flash/"
        tar czf "${BOOT_TGZ}" -C "${TMP_DIR}" .
        rm -rf "${TMP_DIR}"

        #! Make data filesystem image (extract `/flash/data/*` from rootfs image)
        echo "extract and compress data fs => ${DATA_TGZ}"
        rm -rf "${TMP_DIR}" && mkdir -p "${TMP_DIR}"
        tar -x --strip-components=3 -f "${ROOT_TAR}" -C "${TMP_DIR}" "./flash/data"
        tar czf "${DATA_TGZ}" -C "${TMP_DIR}" .
        rm -rf "${TMP_DIR}"

        #! compress rootfs tar image
        echo "compress root fs => ${ROOT_TGZ}"
        cat "${ROOT_TAR}" | gzip --best --rsyncable > "${ROOT_TGZ}"

        #! remove root fs tar image
        rm -f "${ROOT_TAR}"

        #! make upgrade script
        echo "make upgrade image"
        ./makeupgrade.sh

        #! Remove data fs files from root fs archive.
        #! don't remove -- let SD card production tool and upgrade script remove them
        #gzip -cd "${ROOT_TGZ}" | tar f - --delete "./flash" | gzip -c > "_tmp_${ROOT_TGZ}"
        #mv "_tmp_${ROOT_TGZ}" "${ROOT_TGZ}"

        #! don't delete root archive -- need for SD card production
        #rm -f ${ROOT_TGZ}

        ;;
esac

