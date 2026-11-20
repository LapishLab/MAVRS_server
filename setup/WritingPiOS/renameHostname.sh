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

# Allow this computer to log in to the Pi after its first boot.
publicKeyPath="$HOME/.ssh/id_ed25519.pub"
if [ ! -r "$publicKeyPath" ]; then
    echo "Public key not found at $publicKeyPath"
    exit 1
fi
if ! ssh-keygen -lf "$publicKeyPath" >/dev/null; then
    echo "Invalid SSH public key at $publicKeyPath"
    exit 1
fi

read -r -p "Enter the Pi username [pi]: " piUsername
piUsername=${piUsername:-pi}
if [[ ! "$piUsername" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo "Invalid Pi username: $piUsername"
    exit 1
fi
piHomePath="$usbRootPath/home/$piUsername"
if [ ! -d "$piHomePath" ]; then
    echo "Pi home directory not found at $piHomePath"
    echo "The Pi user may need to be created on first boot before this key can be installed"
    exit 1
fi

piUid=$(stat -c %u "$piHomePath") || exit 1
piGid=$(stat -c %g "$piHomePath") || exit 1
sshDir="$piHomePath/.ssh"
authorizedKeysPath="$sshDir/authorized_keys"
sudo install -d -m 700 -o "$piUid" -g "$piGid" "$sshDir" || exit 1
sudo touch "$authorizedKeysPath" || exit 1
sudo chown "$piUid:$piGid" "$authorizedKeysPath" || exit 1
sudo chmod 600 "$authorizedKeysPath" || exit 1

IFS= read -r publicKey < "$publicKeyPath"
if sudo grep -Fxq -- "$publicKey" "$authorizedKeysPath"; then
    echo "This computer's public key is already authorized for $piUsername"
else
    printf '%s\n' "$publicKey" | sudo tee -a "$authorizedKeysPath" >/dev/null || exit 1
    echo "This computer's public key was authorized for $piUsername"
fi
