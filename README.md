# ShadowTrace

ShadowTrace is a lightweight, real-time keystroke monitoring tool featuring a live web-based dashboard. Built with Python, Flask, and pynput, it allows for instant visualization of keyboard input in a hacker-style terminal interface.

## Features

-   **Real-Time Monitoring:** Updates the web interface instantly as keys are pressed.
-   **Web Dashboard:** Accessible via any browser on the local network.
-   **Hacker-Style UI:** Features a dark, terminal-inspired aesthetic with CSS animations.
-   **Live Statistics:** Tracks total keystroke counts in real-time.
-   **Special Key Handling:** Visually distinguishes functional keys (Shift, Enter, Backspace) from standard text.

## Prerequisites

Ensure you have Python 3.x installed. You will also need the following dependencies:

* Flask
* pynput

## Installation

1.  Clone this repository or download the source code.
2.  Install the required Python packages:

    ```bash
    pip install flask pynput
    ```

## Usage

1.  Run the application script:

    ```bash
    python main.py
    ```

2.  The application will initialize the keylogger background thread and start the Flask web server.
3.  Open your web browser and navigate to:

    ```
    http://localhost:5005
    ```

    *Note: To view the dashboard from a mobile device or another computer on the same Wi-Fi network, replace `localhost` with your machine's local IP address (e.g., `http://192.168.1.15:5005`).*

## Troubleshooting

-   **Permission Issues (macOS/Linux):** You may need to grant the terminal "Input Monitoring" or "Accessibility" permissions in your system settings to allow `pynput` to record keystrokes.
-   **Port Conflicts:** If port 5005 is in use, modify the `port=5005` parameter in the `app.run` command at the bottom of the script.

## Disclaimer

**Educational Use Only.** This software is intended for educational purposes, self-monitoring, or authorized testing only. The developers assume no liability and are not responsible for any misuse or damage caused by this program. Always ensure you have explicit permission before monitoring any system.

## License

This project is licensed under the [MIT License](LICENSE).
