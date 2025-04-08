## BEGIN: yo_tasklib.sh - a few helper functions for tasks
# Copyright (c) 2023, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

TASK_DIR=$$TASK_DIR$$

DEPENDS_ON() {
    echo "Waiting on task $1"
    echo "$1" > ./wait
    while ! [ -f "$TASK_DIR/$1/status" ]; do
        sleep 1
    done
    rm -f ./wait
    if [ "$(cat "$TASK_DIR/$1/status")" != "0" ]; then
        echo "error: dependency task $1 failed"
        exit 1
    fi
    echo "Wait on task $1 completed"
}

CONFLICTS_WITH() {
    true
}

RUN_ONCE() {
    if ! [ -f "./status.old" ]; then
        return 0
    fi
    if [ "$(cat ./status.old)" = "0" ]; then
        echo "Task already completed"
        exit 0
    else
        echo "Task has already run unsuccessfully, trying again."
        return 0
    fi
}

PREREQ_FOR() {
    true
}

# Operating system information
source /etc/os-release
case "${NAME}" in
    Oracle*)
        # Setup the "$ORAVER" variable for Oracle Linux. It is a single integer
        # number describing the current Oracle Linux distribution release. EG:
        # "8", "9", "10", etc.
        ORAVER="${VERSION//\.*}"
        case "${ORAVER}" in
            6|7)
                PKGMGR=yum
                ;;
            *)
                PKGMGR=dnf
                ;;
        esac
        ;;
    Ubuntu*)
        UBUVER="${VERSION_ID//\.*}"
        PKGMGR=apt-get
        ;;
    Debian*)
        DEBVER="$VERSION_ID"
        PKGMGR=apt-get
        ;;
    Fedora*)
        FEDVER="$VERSION_ID"
        PKGMGR=dnf
        ;;
    Arch*)
        PKGMGR=pacman
        ;;
esac

PKG_INSTALL() {
    if [ "$PKGMGR" = "pacman" ]; then
        sudo pacman -Sy --noconfirm "$@"
    elif [ -n "$PKGMGR" ]; then
        sudo $PKGMGR install -y "$@"
    else
        echo "error: package manager is unknown"
        exit 1
    fi
}

## END: yo_tasklib.sh
