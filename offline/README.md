# Ubuntu 26 amd64 local installation packages

`linux-amd64/` contains the non-apt packages required by `install.sh`:
the official Node.js 24 archive, Python wheels, a complete npm lockfile cache,
and vendored Go modules (including modules normally fetched from GitHub).
The two SHA-256 files verify the package bytes and their matching source locks.

From a complete checkout on Ubuntu 26 amd64:

```bash
sudo bash install.sh --source "$PWD" --domain 192.168.100.100
```

The installer automatically selects this bundle. `--offline-dir /path/to/linux-amd64`
selects a separate copy explicitly. If a selected bundle is incomplete, corrupt,
or built for different lock files, installation stops before replacing the app.
Without a bundle, the installer downloads non-apt dependencies as before.
Ubuntu apt packages still require configured apt repositories or an apt mirror.

To regenerate after changing a dependency lock on an online Ubuntu 26 amd64 host,
remove or move the old `offline/linux-amd64` directory, then run
`bash scripts/prepare_offline_bundle.sh`. Review the resulting archives and
commit the regenerated bundle with the lockfile change. A full source checkout
is still required; pass `--source` to avoid cloning GitHub during installation.
