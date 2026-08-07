#!/bin/bash

set -e

echo "Compiling mpy..."
./compile-mpy

echo "Uploading to camera..."
scp -r mpy pi@logicallyrapidgarfish-new.local:

echo "Removing old mpy files..."
ssh "pi@logicallyrapidgarfish-new.local" "sudo rm -r /etc/cacophony/mpy"

echo "Moving new mpy files..."
ssh "pi@logicallyrapidgarfish-new.local" "sudo mv mpy /etc/cacophony/mpy"

echo "Restarting tc2-hat-comms"
ssh "pi@logicallyrapidgarfish-new.local" "sudo systemctl restart tc2-hat-comms"

