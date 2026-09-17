# ComfyUI CoolB Nodes

A simple pack of utility nodes for **ComfyUI** featuring saving/loading speakers with transcripts (useful alongside TTS packs), execution flow control (muting/bypassing nodes and groups on trigger to actively change the workflow state from run to run), some useful text file utilities (including save/load text file) and data type conversion.

This pack was created primarily to support my other project — a fully Autonomous Telegram Bot inside a single ComfyUI workflow.

---

## 🧩 List of Nodes

<img width="1710" height="1067" alt="image" src="https://github.com/user-attachments/assets/9e7050e5-f184-4c3a-b682-a4e2ee57c9a2" />

### 🎙️ Audio & Speaker Management
Designed for TTS (Text-to-Speech) workflows, voice cloning, and audio archiving. Automatically uses `PyAV`, `torchaudio`, or native fallbacks.
* **CB Save Speaker:** Saves an audio tensor/file alongside its provided text transcription (speech script) into a structured format inside `models/SPEAKERS` (customizable via `config.json`). Supports `.mp3` and `.wav`.
* **CB Load Speaker:** Lists and loads saved speakers dynamically from your storage, outputting both the audio waveform and its reference text.

### ⚙️ Automation & Workflow Control
* **CB Set Mute/Bypass State:** Allows you to dynamically **Mute**, **Bypass**, or **Activate** one or multiple nodes specified by their IDs using any passthrough signal (applies to the *next* prompt run). An improved version of the node from ComfyUI-Impact-Pack.
* **CB Set Group Mute/Bypass State:** Same as the other node but for entire groups. Changes execution states (**Mute/Bypass/Active**) for all nodes within specified groups at once based on a group name search string (applies to the *next* prompt run). Node detection adapted from rgthree-comfy group muters/bypassers.

### 📝 Text & String Utilities
* **CB Textbox:** A simple text container that displays text, prints to screen and automatically overwrites its contents and converts any incoming data stream to a string. An improved version of the node from ComfyUI-Chibi-Nodes.
* **CB String Selector:** Splits a multiline or delimited string (by newlines, commas, or spaces) and returns a specific substring based on an index (supports modulo wrapping).
* **CB String List Match Index:** Compares an input string against a list of strings that are devided by a chosen delimiter. Supports custom matching modes (*Equal, Contains, Starts with, Ends with*) and returns a 1-based index (0 if not matched) and a boolean match state.

### 💾 Text Save/Load
* **CB Read Text File:** Loads raw text content from any specified file path relative to your ComfyUI root folder.
* **CB Save Text File:** Saves text strings into files with three operation modes: `overwrite` (replace), `append` (add to end), or `increment` (automatically generates numbered filenames like `config_00001.txt`).

### 🔄 Type Conversion
* **CB Data type Converter:** Accepts **any** input connection type and safely converts it to a standard primitive: `STRING`, `FLOAT`, `INT`, or `BOOLEAN`.

---

## 🛠️ Installation

### Method 1: Via ComfyUI Manager (Recommended)
1. Open ComfyUI and click on the **Manager** button.
2. Click **Custom Nodes Manager**.
3. Search for `ComfyUI CoolB Nodes` and click **Install**.
4. Restart ComfyUI.

### Method 2: Manual Installation
Download this repo's code and unpack it into ComfyUI/custom_nodes (no other dependencies required: `av`, `numpy` and `torchaudio` come with ComfyUI).
Or do it through console:
1. Open your terminal and navigate to your ComfyUI custom nodes directory:
   ```bash
   cd ComfyUI/custom_nodes
   ```
2. Clone this repo:
   ```bash
   git clone https://github.com/CoolBreeze164/ComfyUI-CoolB-Nodes
   ```
3. Restart ComfyUI.

---

## 👥 Credits & Acknowledgements
This pack was vibecoded with Qwen and Gemini. Some of the nodes were inspired by [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack "ComfyUI Impact Pack github") and [ComfyUI-Chibi-Nodes](https://github.com/chibiace/ComfyUI-Chibi-Nodes "ComfyUI Chibi Nodes github").

---

## 📜 License
This node pack is open-source and distributed under the **MIT License**. Please refer to the dependency licenses regarding audio backends (`PyAV` / `LGPL`, etc) if redistributed commercially.
