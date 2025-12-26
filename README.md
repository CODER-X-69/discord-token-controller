# 🚀 Hacker X - Discord Multi-Token Controller

A robust, multi-interface Python tool designed to manage and control multiple Discord user accounts simultaneously. Control your token swarm via a **Command Line Interface**, a **Real-time Web Dashboard**, or a **Remote Discord Bot**.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-SocketIO-green?style=for-the-badge&logo=flask)
![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA?style=for-the-badge&logo=discord)

> **⚠️ DISCLAIMER**
> This tool is for **educational purposes only**. Automating user accounts (self-botting) is against Discord's Terms of Service. The developer is not responsible for any account bans or suspensions resulting from the use of this software. Use at your own risk.

---

## ✨ Features

* **Triple Interface Control system:**
    * **CLI:** Interactive terminal for fast command execution.
    * **Web Dashboard:** Flask + SocketIO based UI with live logs and buttons.
    * **Remote Bot:** Execute commands via a standard Discord bot (discord.py).
* **Voice Channel Manager:** Make all tokens join/leave specific voice channels instantly.
* **Server Management:** Mass join or leave servers via invite codes.
* **Broadcasting:** Send messages to specific channels across all accounts.
* **Status Rotator:** Sync custom status (Activities) across all accounts.
* **Token Checker:** Built-in validator to check if tokens are valid or invalid.
* **Live Logging:** Real-time feedback in the dashboard and console.

## 🛠️ Installation

1.  **Clone the repository**
    ```bash
    git clone [https://github.com/yourusername/discord-token-controller.git](https://github.com/yourusername/discord-token-controller.git)
    cd discord-token-controller
    ```

2.  **Install dependencies**
    You will need the following Python libraries:
    ```bash
    pip install flask flask-socketio eventlet requests colorama discord.py questionary rich discum
    ```
    *(Note: `discum` is required for gateway interaction. If pip fails, install it from the source).*

3.  **Setup Tokens**
    Create a file named `token.txt` in the root directory. Paste one Discord user token per line.
    ```text
    OTk1...
    MTAx...
    NzI4...
    ```

---

## ⚙️ Configuration

You can configure settings via environment variables or by editing the top of the `discord-token-controller.py` file.

| Variable | Description | Default |
| :--- | :--- | :--- |
| `HX_DASH_USER` | Dashboard Username | `Admin X` |
| `HX_DASH_PASS` | Dashboard Password | `hackerxontop` |
| `HX_SECRET` | Dashboard Secret Token | `CoderX-HackerX-On-Top` |
| `REMOTE_BOT_TOKEN` | (Optional) Token for remote control bot | `None` |
| `AUTHORIZED_CHANNELS`| (Optional) Channel IDs for bot commands | `0` (All) |

---

## 🖥️ Usage

Run the script using Python:

```python discord-token-controller.py```

## How to use.

1. Web Dashboard
Once running, open your browser and navigate to:
http://localhost:5000
User: Admin X
Pass: hackerxontop

2. CLI Commands
Type help in the terminal to see all commands. Common commands:
list - View loaded tokens.
joinserver <invite_url> --all - Join a server with all accounts.
joinvc_all <channel_id> - Join a voice channel with all accounts.
message_all <channel_id> <content> - Spam a message.
check_tokens - Validate tokens.

3. Remote Bot (Optional)
If you set REMOTE_BOT_TOKEN, invite that bot to your server. Use the prefix !.
!run joinvc_all <channel_id>
!run status "Hacking..."

## 📝 License
This project is licensed under the MIT License.
