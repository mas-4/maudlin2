#!/bin/bash

# Define the mount point and the device
MOUNT_POINT="/mnt"
DEVICE="/dev/sdb1"

# Check if the device is already mounted
if mount | grep -q " on ${MOUNT_POINT} "; then
    echo "The drive is already mounted."
else
    # Mount the device to the mount point
    echo "Mounting the drive..."
    mount ${DEVICE} ${MOUNT_POINT}
    # Check if the mount was successful
    if [ $? -eq 0 ]; then
        echo "Drive mounted successfully."
    else
        echo "Failed to mount the drive."
        exit 1  # Exit if mounting fails
    fi
fi

# Get the current date in YYYY-MM-DD format
DATE=$(date +%Y-%m-%d)

# Define the source and destination paths
SOURCE_FILE="/home/maudlin/maudlin2/data/data.db"
INTERMED_FILE = "data-$DATE.db"
TARGET_FILE="${MOUNT_POINT}/data-$DATE.db.gz"

# Copy and compress the database file with a timestamp
echo "Backing up the database file..."
# Copy the file to the destination and compress it
cp ${SOURCE_FILE} ${INTERMED_FILE}
gzip -f ${INTERMED_FILE}
cp ${INTERMED_FILE}.gz ${TARGET_FILE}

# Check if the backup was successful
if [ $? -eq 0 ]; then
    echo "Backup completed successfully."
else
    echo "Backup failed."
fi