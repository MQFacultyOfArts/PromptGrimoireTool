#!/usr/bin/env bash
# Update the production TinyTeX tree with an exact pre-update snapshot.

set -Eeuo pipefail

APP_DIR=/opt/promptgrimoire
SERVICE_USER=promptgrimoire
SERVICE_HOME=/home/promptgrimoire
TEX_BIN="$SERVICE_HOME/.TinyTeX/bin/x86_64-linux"
TEX_AUDIT_DIR=/var/backups/promptgrimoire/texlive
TEX_BACKUP_DIR="$SERVICE_HOME/.TinyTeX/tlpkg/backups"
LOCK_FILE=/run/lock/promptgrimoire-texlive.lock

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: run as root: sudo $0" >&2
    exit 1
fi

# sudo preserves the caller's cwd. The service user cannot traverse a normal
# operator home, and tlmgr returns to its initial cwd after using File::Temp.
cd "$APP_DIR"

exec 9>"$LOCK_FILE"
if ! flock --exclusive --nonblock 9; then
    echo "ABORT: another TinyTeX maintenance process holds $LOCK_FILE" >&2
    exit 1
fi

tex_stamp=$(date +%Y%m%d-%H%M%S-%N)
tex_snapshot="$TEX_AUDIT_DIR/tree-before-$tex_stamp.tar.gz"
before_file="$TEX_AUDIT_DIR/before-$tex_stamp.txt"
after_file="$TEX_AUDIT_DIR/after-$tex_stamp.txt"
worker_stopped=false
update_started=false

run_as_service() {
    sudo -H -u "$SERVICE_USER" \
        env PATH="$TEX_BIN:/usr/local/bin:/usr/bin:/bin" "$@"
}

on_exit() {
    status=$?
    trap - EXIT

    if [[ "$status" -ne 0 && "$worker_stopped" == true ]]; then
        if [[ "$update_started" == false ]]; then
            if systemctl start promptgrimoire-worker.service; then
                echo "FAILED before package updates; worker restarted." >&2
            else
                echo "FAILED before package updates; worker restart also failed." >&2
            fi
        else
            echo "FAILED after package updates began; worker remains stopped." >&2
            echo "Snapshot: $tex_snapshot" >&2
        fi
    fi

    exit "$status"
}
trap on_exit EXIT

active_exports=$(sudo -u "$SERVICE_USER" psql -At -v ON_ERROR_STOP=1 \
    -d promptgrimoire \
    -c "SELECT count(*) FROM export_job WHERE status IN ('queued', 'running');")
if [[ ! "$active_exports" =~ ^[0-9]+$ ]]; then
    echo "ABORT: export queue query returned an invalid count." >&2
    exit 1
fi
if [[ "$active_exports" != 0 ]]; then
    echo "ABORT: $active_exports export job(s) are active." >&2
    exit 1
fi

if ! systemctl is-active --quiet promptgrimoire-worker.service; then
    echo "ABORT: export worker is not active before maintenance." >&2
    exit 1
fi
systemctl stop promptgrimoire-worker.service
worker_stopped=true
if systemctl is-active --quiet promptgrimoire-worker.service; then
    echo "ABORT: export worker did not stop." >&2
    exit 1
fi

install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$TEX_AUDIT_DIR"
tar -C "$SERVICE_HOME" -czf "$tex_snapshot" .TinyTeX
test -s "$tex_snapshot"
tar -tzf "$tex_snapshot" >/dev/null
sha256sum "$tex_snapshot" > "$tex_snapshot.sha256"
sha256sum -c "$tex_snapshot.sha256" >/dev/null
ln -sfn "$(basename "$tex_snapshot")" \
    "$TEX_AUDIT_DIR/latest-tree-snapshot.tar.gz"

run_as_service bash -c 'set -euo pipefail
    tlmgr version
    tlmgr repository list
    tlmgr option backupdir
    tlmgr option autobackup
    tlmgr info --only-installed --data name,localrev,lcat-version
    tlmgr update --list --all' \
    | tee "$before_file" >/dev/null

run_as_service mkdir -p "$TEX_BACKUP_DIR"
run_as_service tlmgr option backupdir "$TEX_BACKUP_DIR"
run_as_service tlmgr option autobackup 5

update_started=true
run_as_service tlmgr update --self
run_as_service tlmgr update --all

run_as_service bash -c 'set -euo pipefail
    tlmgr version
    tlmgr repository list
    tlmgr option backupdir
    tlmgr option autobackup
    tlmgr info --only-installed --data name,localrev,lcat-version' \
    | tee "$after_file" >/dev/null

/usr/local/bin/grimoire-run grimoire test smoke-export

systemctl start promptgrimoire-worker.service
systemctl is-active --quiet promptgrimoire-worker.service
worker_stopped=false

grep '^marginalia,' "$after_file"
printf 'snapshot=%s\nbefore=%s\nafter=%s\n' \
    "$tex_snapshot" "$before_file" "$after_file"

trap - EXIT
echo "TinyTeX update complete; worker active."
