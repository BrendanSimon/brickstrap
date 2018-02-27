Create archive to unpack with `makeself` script
===============================================

Execute the following `tar` command from the appropriate built rootfs version.

Create rootfs for your version (only required if it doesn't exist already)

    $ git checkout <tag-or-branch-reference>
    $ cd ../build
    $ ../brickstrap/ind-efd/build.sh

Enter the brickstrap (qemu) shell and run `tar` command.

    $ ../brickstrap/ind-efd/build.sh shell
    # tar czvf /host-rootfs/home/brendan/SEPL/brickstrap/build/xxx.tgz \
        <list-of-files>
    # exit

Create a patch directory for your arhive and script to run.

    $ mkdir ind-efd-patch-vA.B.C-to-vX.Y.Z
    $ cp xxx.tgz to ind-efd-patch-vA.B.C-to-vX.Y.Z/

Create/edit your run script, specific to your patch directory contents.

    $ vi ind-efd-patch-vA.B.C-to-vX.Y.Z/run.sh

Run `makeself` to crate an executable shell script that will self-unpack and
execute the run script.

**See `makepatch.sh` to automate this step**

    ## makeself.sh [args] archive_dir file_name label startup_script [script_args]

    $ makeself.sh ind-efd-vA.B.C-to-vX.Y.Z \
        ind-efd-patch-vA.b.C-to-vX.Y.X.run \
        "IND EFD Patch from vA.B.C to vX.Y.Z" \
        ./run.sh

v0.10.0 to v0.10.1
------------------

tar czvf /host-rootfs/home/brendan/SEPL/brickstrap/build/xxx.tgz \
    /opt/sbin/efd_config.py
    /etc/systemd/system/serial-getty@ttyS1.service
    /etc/chrony/chrony.conf
    /etc/chrony/chrony_ORIG.conf
    /etc/chrony/chrony_SEPL.conf
    /etc/systemd/system/chrony.service
    /etc/systemd/system/gpsd.service
    /etc/logrotate.d/chrony
    /etc/default/gpsd
    /etc/default/gpsd.ORIG

v0.10.1 to v0.10.2
------------------

tar czvf /host-rootfs/home/brendan/SEPL/brickstrap/build/xxx.tgz \
    /opt/sbin/efd_config.py \
    /etc/systemd/system/chrony.service \
    /etc/apt/sources.list

