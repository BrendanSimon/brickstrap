#!/bin/bash

## Exit on any error.
set -o errexit

prog_full=$0
prog_base=$(basename $0)

start_dir=$(pwd)
prog_dir=$(dirname ${start_dir}/${prog_full})

archive=$(find -name "ind-efd-*gz")

dev_fs1="/dev/mmcblk0p2"
dev_fs2="/dev/mmcblk0p3"

upgrade_root_mnt="/tmp/upgrade"

current_uenv="/boot/flash/uEnv.txt"
upgrade_uenv="/boot/flash/uEnv_tmp.txt"

settings_file="/mnt/data/etc/settings"
settings_orig_dir="/mnt/data/etc/ORIG"
settings_prev_dir="/mnt/data/etc/PREV"
settings_new="/mnt/data/etc/settings_NEW"

reboot_delay=3

## Set to "#" to do a dry-run (no actions)
#dryrun="#"

## Set to 1 for more diagnostic output.
verbose=0

##===========================================================================

cmd()
{
    if [[ ${verbose} != 0 ]] ; then
        if [[ -z ${dryrun} ]] ; then
            echo "executing command: $@"
        else
            echo "skipping command: $@"
        fi
    fi

    if [[ -z ${dryrun} ]] ; then
        $@
    fi
}

##===========================================================================

error()
{
    echo "ERROR: $1"
}

##===========================================================================

fatal()
{
    error "$1"
    echo "Terminated ['${prog_base}']"
    exit -1
}

##===========================================================================

copy_from_current_fs()
{
    local src="$1"
    local dst="${upgrade_root_mnt}$1"

    if [ -d "${src}" ] ; then
        dst=$(dirname "${dst}")
    fi

    if [[ -e ${src} ]] ; then
        echo "copying '${src}' => '${dst}'"
        cmd cp -a "${src}" "${dst}"
    fi
}

##===========================================================================

echo "Starting ['${prog_base}']"

##
## Check for root privileges.
##
id=$(id --user)
if [[ ${id} != 0 ]] ; then
    fatal "No superuser privileges.  Try running with 'sudo'"
fi

##
## Determine current root filesystem and upgrade root filesystem.
##
current_root_dev=$(findmnt --noheadings --first-only --output SOURCE)

if [[ ${current_root_dev} == "${dev_fs2}" ]] ; then
    upgrade_root_dev="${dev_fs1}"
    upgrade_root_name="ROOTFS1"
    upgrade_boot_part="2"
    current_boot_part="3"
elif [[ ${current_root_dev} == "${dev_fs1}" ]] ; then
    upgrade_root_dev="${dev_fs2}"
    upgrade_root_name="ROOTFS2"
    upgrade_boot_part="3"
    current_boot_part="2"
else
    fatal "Unknown current root device ['${current_root_dev}']"
fi

## Confirm format
while true ; do
    echo -e "\nAuto-detected current rootfs on partition ${current_boot_part}"
    echo "Upgrade rootfs will be extracted to partition ${upgrade_boot_part}"
    echo "WARNING: partition ${upgrade_boot_part} will be erased !!"
    echo -e "\nPlease confirm (type: 'YES' to continue, 'NO' to exit)"
    read r
    if [[ ${r} == "YES" ]] ; then
        echo "Confirmed"
        break
    elif [[ ${r} == "NO" ]] ; then
        echo "Not confirmed.  Exiting ..."
        exit 1
    fi
done

##
## Make a clean filesystem on the upgrade partition.
## (ensure it's not mounted first)
##
cmd umount "${upgrade_root_dev}" || true
cmd mkfs.ext4 -F -L "${upgrade_root_name}" "${upgrade_root_dev}"

##
## Mount the upgrade filesystem.
##
mkdir --parents ${upgrade_root_mnt}
echo "Mounting the upgrade filesystem ['${upgrade_root_mnt}']"
cmd mount ${upgrade_root_dev} ${upgrade_root_mnt}

cd ${upgrade_root_mnt}

##
## Unpack upgrade archive to upgrade filesystem.
##
echo "Unpacking rootfs archive... ['${archive}' => '${upgrade_root_mnt}']"
cmd tar --extract --gzip --file "${prog_dir}/${archive}"

##
## Copy config files from current rootfs to upgrade rootfs.
##
copy_from_current_fs /etc/hostname
copy_from_current_fs /etc/ssh
copy_from_current_fs /home/sepladmin/.ssh
copy_from_current_fs /home/sepluser/.ssh
copy_from_current_fs /home/efdadmin/.ssh
copy_from_current_fs /home/efduser/.ssh

##
## Update user settings file (merge exisiting settings).
##
echo -e "\nUpdating user settings..."

if [[ ! -e ${settings_orig_dir} ]] ; then
    echo -e "\nMake backup of original user settings file..."
    cmd mkdir -p "${settings_orig_dir}"
    cmd cp "${settings_file}" "${settings_orig_dir}/"
fi

echo -e "\nMake backup of current user settings file..."
cmd mkdir -p "${settings_prev_dir}"
cmd cp "${settings_file}" "${settings_prev_dir}/"

echo -e "\nCopy new default user settings file..."
cmd cp "${upgrade_root_mnt}/opt/sbin/settings_new" "${settings_new}"

## Get system setting values and overwrite default values in
## the new settings file.
echo -e "\nReplace default user settings with existing settings..."
pat_old="^(\w+=).*"
while read -r  line ; do
    if [[ ${line} =~ ${pat_old} ]] ; then
        pat_new="^${BASH_REMATCH[1]}.*"
        cmd sed -i "s|${pat_new}|${line}|" "${settings_new}"
    fi
done < "${settings_file}"

cmd mv "${settings_new}" "${settings_file}"

##
## Detect/choose platform type.
## Check FPGA version first, then fallback to running devicetree.
##
fpga_ver_maj=$(${upgrade_root_mnt}/opt/sbin/fpga_version.py | grep --no-filename --only-matching --perl-regexp "major += +\K.*")
let fpga_ver_maj="${fpga_ver_maj}" || true

devtree_model=$(cat /proc/device-tree/model)

if [[ ${fpga_ver_maj} == 2 ]] ; then
    platform=2
elif [[ "${fpga_ver_maj}" == 1 ]] ; then
    platform=1
elif [[ "${devtree_model}" == "Xilinx Zynq IND-EFD-2" ]] ; then
    platform=2
elif [[ "${devtree_model}" == "Xilinx Zynq LSI" ]] ; then
    platform=2
elif [[ "${devtree_model}" == "Xilinx Zynq ZED" ]] ; then
    platform=1
else
    platform=0
fi

## Confirm platform.
while true ; do
    if [[ ${platform} == 0 ]] ; then
        echo -e "\nPlatform could not be auto-detected !!"
        echo "Please choose the target platform (type: '1' or '2')"
    else
        echo -e "\nAuto-detected platform = ${platform}"
        echo "Please confirm/choose the target platform (type: 'YES', '1' or '2')"
    fi
    read p
    if [[ ${p} == "YES" && ${platform} != 0 ]] ; then
        echo "Confirmed platform = ${platform}"
        break
    elif [[ ${p} == [1-2] ]] ; then
        platform=${p}
        echo "Selected platform = ${platform}"
        break
    fi
done
#echo "Set platform = ${platform}"

##
## Make boot partition writeable.
##
cmd mount --options remount,rw /boot/flash

##
## Upgrade the BOOT.bin bootloader/FPGA for the platform.
## Copies all files from `/boot/flash/`
##
if [[ ! -e "/boot/flash/ORIG" ]] ; then
    echo -e "\nMake backup of original boot files for platform..."
    cmd mkdir -p "/boot/flash/ORIG"
    cmd find "/boot/flash" -maxdepth 1 -type f | xargs cp -t "/boot/flash/ORIG/"
fi

echo -e "\nMake backup of current boot files for platform..."
cmd mkdir -p "/boot/flash/PREV"
cmd find "/boot/flash" -maxdepth 1 -type f | xargs cp -t "/boot/flash/PREV/"

echo -e "\nUpgrade boot files for platform..."
cmd cp "${upgrade_root_mnt}/boot/flash/*" "/boot/flash/"
cmd cp "/boot/flash/BOOT${platform}.bin" "/boot/flash/BOOT.bin"

##
## Setup the devicetree symlinks for the platform.
##
echo -e "\nSetup devicetree symlinks for platform..."
pushd "${upgrade_root_mnt}/boot" > /dev/null
cmd ln --symbolic --force "zynq-IND${platform}.dtb" "ind.dtb"
cmd ls -l "ind.dtb"
popd > /dev/null

##
## Edit U-Boot enviroment file to boot from new partition.
##
while true ; do
    echo -e "\nThe U-Boot environment boot partition needs to be changed\nto use the upgraded firmware"
    echo -n "Change it now? (type: 'YES' or 'NO'): "
    read change_uboot_env
    if [[ ${change_uboot_env} == "YES" ]] ; then
        echo "Changing U-Boot env boot partition: ${current_boot_part} to ${upgrade_boot_part}"
        cmd head --lines=1 "${current_uenv}"
        cmd cp "${current_uenv}" "${upgrade_uenv}"
        cmd sed -i "s/^boot_part=.*/boot_part=${upgrade_boot_part}/" "${upgrade_uenv}"
        cmd mv "${upgrade_uenv}" "${current_uenv}"
        cmd head --lines=1 "${current_uenv}"
        break
    elif [[ ${change_uboot_env} == "NO" ]] ; then
        echo "You will have to change it manually later to use the new firmware"
        break
    fi
done

##
## Make boot partition read-only.
## Sync filesystems.
##
echo -e "\nRemount boot partition read-only and sync filesystems..."
cd ${start_dir}
cmd sync
cmd mount --options remount,ro /boot/flash
cmd umount ${upgrade_root_dev}
cmd sync

##
## Prmopt to perform reboot
##
while true ; do
    echo -e "\nYou need to reboot to use the upgraded firmware"
    echo -n "Do want to reboot now? (type: 'YES' or 'NO'): "
    read reboot
    if [[ ${reboot} == "YES" ]] ; then
        echo "Rebooting soon ..."
        break
    elif [[ ${reboot} == "NO" ]] ; then
        echo "You will have to manually reboot later to use the new firmware"
        break
    fi
done

echo "Finished ['${prog_base}']"

##
## Perform the reboot as last step.
##
if [[ ${reboot} == "YES" ]] ; then
    echo "Rebooting in ${reboot_delay} seconds"
    for n in $(seq ${reboot_delay} -1 1) ; do
        echo -n "${n}.."
        sleep 1
    done
    echo
    echo "Rebooting now !!"
    sleep 1
    cmd reboot
fi

##===========================================================================

