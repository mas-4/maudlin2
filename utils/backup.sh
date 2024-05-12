#!/bin/bash

DATE=$(date +%Y-%m-%d)

cp /home/maudlin/maudlin2/data/data.db data.db
gzip data.db
mv data.db.gz /mnt/data_$DATE.db.gz
