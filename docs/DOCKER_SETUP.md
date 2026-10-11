# Docker setup on Nykra workstation

Checked October 11, 2026.

- Installed Docker Desktop for Windows in official per-user mode at `%LOCALAPPDATA%\Programs\DockerDesktop`.
- Downloaded the official Docker Inc signed installer (Windows Authenticode status **Valid**; SHA-256: `a9814e31049d66156477a86614e83365669677733014ec72f74229623ff3890a`).
- Verified installed Docker CLI **29.8.2**. Its current-user PATH registration exists; a fresh terminal receives it.
- **WSL 3.0.1.0 is installed**, with WSL 2 as the default. The administrator-elevated `wsl --install --no-distribution --web-download` finished successfully (exit 0). **Virtual Machine Platform** was then enabled successfully by administrator-elevated DISM, returning **3010 (restart required)**. The Linux Docker daemon is **not yet running** until Windows is restarted and Docker Desktop is started.
- **Next step for the user:** Restart Windows once. Open Docker Desktop from the Start menu and review/accept its license prompt. No additional WSL installation command is needed.
- After reboot and opening Docker Desktop, run `docker version` and `python -m nykra benchmark preflight`; follow with a small constrained container smoke check before any external code.
- Docker presence or a successful container smoke does not by itself authorize executing untrusted external benchmark code. Nykra remains fail-closed until a constrained evaluator is implemented and verified.

Storage note: approximately 3.2 GiB of npm and 0.56 GiB of pip package caches were purged, plus regenerable Gradle 9.4.1 and Forge Gradle build caches; project repositories were not deleted. These caches may need downloading again when other builds run. The workstation has only one C: volume; monitor free space before downloading large benchmark images.

No Nykra code commits/pushes, no forced restart or Docker license acceptance occurred **during the initial installation**.

## Post-reboot verification — October 11, 2026

Docker daemon and WSL2 are now operational. `docker info` returned Engine **29.8.2**, Linux and `overlayfs`. WSL reports default version **2** and `docker-desktop` as the default distribution. The initial post-reboot C: free space was **3,012,702,208 bytes (~2.81 GiB)**, so do not pull a large benchmark image.

A small official BusyBox 1.37.0 image was downloaded and referenced by digest for an approved, fixed-command, offline, nonroot Docker smoke with a read-only root and resource constraints. The smoke passed. See [execution boundary and reproducible command](EXTERNAL_EVALUATION.md) and [captured result](evidence/docker_smoke_2026-10-11.json). Docker installation plus this smoke does **not** unlock arbitrary untrusted benchmark code. The signed download was deleted **after** installing Docker to recover about 606 MiB. Free C: space before the pending reboot was around 2.8 GiB; do not download large benchmark images with this little remaining space.
