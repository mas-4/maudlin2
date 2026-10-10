#!/bin/bash
# Keep the model caches out of snapper's snapshots (Oct 10). Ollama's models (/var/lib/ollama) and Hugging Face's
# (~mas/.cache/huggingface) are large, churn as models are tried, and can always be downloaded again; but / and /home
# are snapshotted hourly and at every pacman run (snap-pac), so a deleted model's space stayed taken for weeks: the
# Oct 10 cleanup removed ~250 GB of models and the disk didn't move.
#
# 1. Each cache becomes a btrfs subvolume of its own, nested where it is (snapshots skip nested subvolumes). Ollama
#    keeps running: the files are copied by reflink (no data copied, seconds), then the two folders are swapped by
#    rename. After a snapper rollback the folder would come back empty and the models need pulling again.
# 2. The caches are removed from the snapshots already taken (each made writable for the moment and read-only again),
#    which frees the deleted models' space. Everything else in the snapshots is left as it was.
#
#   sudo bash deploy/btrfs-model-caches.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }

is_subvolume() { [ "$(stat -c %i "$1")" = 256 ]; }

to_subvolume() {
    local dir=$1
    if is_subvolume "$dir"; then
        echo "$dir is a subvolume already"
        return
    fi
    echo "making $dir a subvolume"
    btrfs subvolume create "$dir.new" >/dev/null
    chown --reference="$dir" "$dir.new"
    chmod --reference="$dir" "$dir.new"
    cp -a --reflink=always "$dir/." "$dir.new/"
    mv "$dir" "$dir.old"
    mv "$dir.new" "$dir"
    rm -rf "$dir.old"
}

purge_snapshots() {
    local snapshots=$1 inside=$2 n=0 s
    for s in "$snapshots"/*/snapshot; do
        [ -d "$s/$inside" ] || continue
        btrfs property set -f -ts "$s" ro false
        rm -rf "${s:?}/$inside"
        btrfs property set -f -ts "$s" ro true
        n=$((n + 1))
    done
    echo "removed $inside from $n snapshots in $snapshots"
}

while [ "$(systemctl show -p ActiveState --value maudlin-scrape.service)" = activating ]; do
    echo "waiting for the hourly run to finish"; sleep 30
done

df -h / | tail -1
to_subvolume /var/lib/ollama
to_subvolume /home/mas/.cache/huggingface
purge_snapshots /.snapshots var/lib/ollama
purge_snapshots /home/.snapshots mas/.cache/huggingface
echo "btrfs frees the space in the background over a minute or two:"
sleep 60
df -h / | tail -1
