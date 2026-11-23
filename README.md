# Lain Companion

A small animated desktop companion for KDE Plasma. Click Lain to chat, drag her to move, or right-click to change the sprite size or Ollama model. Built-in commands handle time, system information and arithmetic. Other questions go to your selected chat provider. Ollama is the default. Scroll through longer replies with the mouse wheel or arrow keys.

![Lain in her bear pajamas beside the open desktop chat](docs/lain-companion.png)

## Install on CachyOS or Arch Linux

Install Python, Bash, curl, Git and Ollama. Install npm if you do not already have the Codex CLI. On NVIDIA systems you can install the ollama-cuda package for GPU inference. Enable the service and download the default model:

```sh
sudo systemctl enable --now ollama.service
ollama pull gemma3:4b
mkdir -p ~/.local/opt
git clone https://github.com/zehnzwanzig/lain-companion.git ~/.local/opt/lain-companion
cd ~/.local/opt/lain-companion
./install.sh
./launch.sh
```

The installer creates a Python virtual environment with PySide6. The launcher uses XWayland under Plasma Wayland to support window placement. Preferences are stored in `~/.config/lain-companion/config.json`. If an earlier installation requests a missing model, set its `ollama_model` entry to an installed tag.

## Codex with your ChatGPT account

Run `./install.sh` after updating. It installs PySide6 from `requirements.txt` and reuses an existing Codex CLI. If needed, it installs the official npm package from `requirements-npm.txt` inside the project’s virtual environment.

Run `.venv/bin/codex login status` in the project directory. To sign in, run `.venv/bin/codex login` and choose ChatGPT. Restart the widget, then right-click Lain and select **Chat-Anbieter → Codex (ChatGPT-Konto)**. Each chat question starts a fresh online session. Spotify and file commands still run locally. Ollama is required at startup even when Codex is selected.

## Start at login

Quit the manually started companion first. From the project directory:

```sh
install -Dm644 lain-companion.service ~/.config/systemd/user/lain-companion.service
systemctl --user daemon-reload
systemctl --user enable --now lain-companion.service
```

For a different installation directory, adjust WorkingDirectory in the installed unit. Use `journalctl --user -u lain-companion.service -b` to see startup errors.

## Spotify and text files

Install `playerctl` and open Spotify Desktop. Ask “Welcher Song spielt gerade?” for live track metadata. Use `spotify pause`, `spotify next`, or `spotify play <Spotify track link>` to control playback.

For title searches such as `Spiele Duvet von bôa`, set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` locally. For the user service, put the assignments in `~/.config/lain-companion/spotify.env` (mode 600). Create `~/.config/systemd/user/lain-companion.service.d/spotify.conf` with:

```ini
[Service]
EnvironmentFile=%h/.config/lain-companion/spotify.env
```

Run `systemctl --user daemon-reload` and `systemctl --user restart lain-companion.service`.

Use `create file` or `edit file` to choose a UTF-8 text file and enter the contents in a local dialog.

## License and artwork

The software and documentation are available under the MIT license. This unofficial fan project includes an AI-generated sprite inspired by Serial Experiments Lain. The software license grants no rights in third-party characters or designs. Ollama and downloaded models have their own licenses.
