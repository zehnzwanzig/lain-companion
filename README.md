# Lain Companion

A small animated desktop companion for KDE Plasma. Click Lain to chat, drag her to move, or right-click to change the sprite size or Ollama model. Built-in commands handle time, system information and arithmetic. Other questions go to Ollama on your machine. Scroll through longer replies with the mouse wheel or arrow keys.

## Install on CachyOS or Arch Linux

Install Python, Bash, curl, Git and Ollama. On NVIDIA systems you can install the ollama-cuda package for GPU inference. Enable the service and download the default model:

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

## Start at login

Quit the manually started companion first. From the project directory:

```sh
install -Dm644 lain-companion.service ~/.config/systemd/user/lain-companion.service
systemctl --user daemon-reload
systemctl --user enable --now lain-companion.service
```

For a different installation directory, adjust WorkingDirectory in the installed unit. Use `journalctl --user -u lain-companion.service -b` to see startup errors.

## License and artwork

The software and documentation are available under the MIT license. This unofficial fan project includes an AI-generated sprite inspired by Serial Experiments Lain. The software license grants no rights in third-party characters or designs. Ollama and downloaded models have their own licenses.
