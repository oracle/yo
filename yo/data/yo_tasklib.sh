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

# Setup the "$ORAVER" variable for Oracle Linux
if [ -f /etc/oracle-release ] && grep '6\.' /etc/oracle-release; then
    ORAVER=6
elif [ -f /etc/oracle-release ] && grep '7\.' /etc/oracle-release; then
    ORAVER=7
elif [ -f /etc/oracle-release ] && grep '8\.' /etc/oracle-release; then
    ORAVER=8
elif [ -f /etc/oracle-release ] && grep '9\.' /etc/oracle-release; then
    ORAVER=9
fi

## END: yo_tasklib.sh
