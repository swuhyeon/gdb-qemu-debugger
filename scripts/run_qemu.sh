#!/usr/bin/env bash

QEMU_BIN="$HOME/qemu/build/qemu-system-x86_64"
VM_DISK="$HOME/vm/linux_guest.qcow2"

"$QEMU_BIN" \
  -accel tcg \
  -cpu qemu64 \
  -m 2048 \
  -smp 1 \
  -drive file="$VM_DISK",if=virtio,format=qcow2 \
  -netdev user,id=n1,hostfwd=tcp::2222-:22 \
  -device e1000,netdev=n1 \
  -display gtk \
  -s -S
