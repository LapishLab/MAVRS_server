#!/bin/bash

path="$(dirname "$(readlink -f "$0")")""/startExperiment.sh"
echo $path
xfce4-terminal -x $path
