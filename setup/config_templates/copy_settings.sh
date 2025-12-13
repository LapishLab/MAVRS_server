#!/bin/bash

SCRIPT_DIR=$(dirname "$0")
CONFIG_DIR="$HOME/MAVRS_settings"

mkdir -p $CONFIG_DIR
cp "$SCRIPT_DIR/experiment_names.txt" "$CONFIG_DIR/experiment_names.txt"
cp "$SCRIPT_DIR/settings.yaml"  "$CONFIG_DIR/settings.yaml"
cp "$SCRIPT_DIR/pi_addresses.txt" "$CONFIG_DIR/pi_addresses.txt"
