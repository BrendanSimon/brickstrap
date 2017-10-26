README_sepl.md
==============

How to archive `ind-efd` brickstrap sources from git repo
---------------------------------------------------------

    git archive --prefix=brickstrap-ind-efd-v0.9/ -o ../brickstrap-ind-efd-v0.9.tar.gz ind-efd/v0.9

or

    PRJ=ind-efd
    VER=0.9
    TAG=${PRJ}/v${VER}

    PRE=brickstrap-${PRJ}-v${VER}
    OUT=../${PRE}.tar.gz

    git archive --prefix=${PRE}/ -o ${OUT} ${TAG}
        or
    git archive --prefix=${PRE}/ --format=tar ${TAG} | gzip --best > ${OUT}

