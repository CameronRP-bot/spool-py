#!/bin/bash

# Exit if command fails
set -e

# This program will compile the micropython code and upload it to the pi and then restart the tc2-hat-comms so it will upload the new code to the trap.

remote_host="$1"

if [ -z "$remote_host" ]; then
    echo "Usage: $0 [user@]host"
    exit 1
fi

# Default to the pi user so only the device name needs to be given.
if [[ "$remote_host" != *@* ]]; then
    remote_host="pi@$remote_host"
fi

# compile-mpy writes to ./mpy, so run from the directory this script is in.
cd "$(dirname "$0")"

remote_tmp="/tmp/spool-mpy"

echo "Compiling mpy..."
./compile-mpy

echo "Copying files to $remote_host..."
ssh "$remote_host" "rm -rf $remote_tmp"
scp -r mpy "$remote_host:$remote_tmp"

echo "Moving new mpy files..."
ssh "$remote_host" "sudo rm -rf /etc/cacophony/mpy && sudo mv $remote_tmp /etc/cacophony/mpy"

echo "Restarting tc2-hat-comms"
ssh "$remote_host" "sudo systemctl restart tc2-hat-comms"

echo "Done"
