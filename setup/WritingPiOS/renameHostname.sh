#!/bin/bash

# Look for rootfs directory mounted in /media/
username=$(whoami)
usbRootPath="/media/$username/rootfs"
if [ ! -d "$usbRootPath" ]; then
    echo "rootfs folder not found at /media/$username"
    echo "do not run this script as sudo and ensure that usb drive is mounted at /media"
    echo "Try unplugging and replugging the microSD into the PC"
    exit 1
fi

# Get old hostname from hostname file
hostnamePath="$usbRootPath/etc/hostname"
if [ ! -f "$hostnamePath" ]; then
    echo Could not find hostname file at $hostnamePath
    exit 1
fi
oldHostname=$(head -n 1 "$hostnamePath")
echo old hostname=$oldHostname

# check for existence of hosts file
hostsPath="$usbRootPath/etc/hosts"
if [ ! -f "$hostsPath" ]; then
    echo Could not find hosts file at $hostsPath
    exit 1
fi

# check that hosts file contains the same name as hostname file
if  ! grep -wq $oldHostname $hostsPath; then
    echo "hostname and hosts files do not have matching names. Please manually edit"
    exit 1
fi

# Enter new hostname and change in both hostname and hosts files
read -p "Enter the new hostname: " newHostname
sudo sed -i "s/$oldHostname/$newHostname/g" $hostnamePath
sudo sed -i "s/$oldHostname/$newHostname/g" $hostsPath
echo new hostname set to $newHostname
