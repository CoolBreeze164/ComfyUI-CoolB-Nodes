# ComfyUI CoolB Nodes ⚡️

A simple pack of utility nodes for **ComfyUI** featuring saving/loading speakers with transcripts (useful alongside TTS packs), execution flow control (muting/bypassing nodes and groups on trigger to actively change the workflow state from run to run), some useful image, audio, video and text file utilities (including save/load text file) and data type conversion.

This pack was created primarily to support my other project — a fully [Autonomous Telegram Bot](https://github.com/CoolBreeze164/ComfyUI-Autonomous-Telegram-Bot) inside a single ComfyUI workflow.

---

## 🧩 List of Nodes

<img width="2083" height="972" alt="image" src="https://github.com/user-attachments/assets/e6f3b9e1-d1a6-48d2-b687-f11c6664d3cd" />

### 🎙️ Speaker Management
Designed for TTS (Text-to-Speech) workflows, voice cloning, and audio archiving. Automatically uses `PyAV` or `torchaudio` fallback.
* **CB Save Speaker:** Saves an audio tensor/file alongside its provided text transcription (speech script) into a structured format inside `models/SPEAKERS` (customizable via `config.json`). Supports `.mp3` and `.wav`.
* **CB Load Speaker:** Lists and loads saved speakers dynamically from your storage, outputting both the audio waveform and its reference text.

### 🔊 Audio processing
* **CB Audio Info:** A simple node that provides information about the input audio (duration, sample rate, total samples, number of channels).
* **CB Audio Processor:** Processes an audio track with volume, fades, and silence padding. Can be used alongside native "Merge Audio" nodes to combine multiple tracks with precise control.
* **CB Roll and Trim Audio Samples:** Rolls audio by a time offset first, then trims from start/end. No resampling is performed, does a cyclic sample shift and sample-accurate trim. Returns _trimmed audio_, removed _start audio_, and removed _end audio_. Can be used to trim and split audio track at the right position or when dealing with looping videos.

### 🎬 Image/video processing
* **CB Roll and Trim Video Frames:**  Does the same as the other node for audio, but for video frames. Rolls the clip by an integer offset first, then trims frames from the start/end. Returns _trimmed video_, removed _start frames_, and removed _end frames_. Very useful for working with looping videos.
* **CB Nearest Resolution:** Calculates the nearest resolution for an input image/video that matches chosen `megapixels` and `divisible_by`, while keeping the aspect ratio closest to the original. Useful for quick calculations of width/height. The output can be connected to the native "Resize Image/Mask" node.
* **CB Color Correct:** Allows to tweak the color of the image/video by changing the following parameters: temperature, hue, brightness, contrast, saturation and gamma. An improved version of the node from from art-venture pack; was optimized and made much faster for processing batches.

### ⚙️ Automation & Workflow Control
* **CB Set Mute/Bypass State:** Allows you to dynamically **Mute**, **Bypass**, or **Activate** one or multiple nodes specified by their IDs using any passthrough signal (applies to the *next* prompt run). An improved version of the node from ComfyUI-Impact-Pack.
* **CB Set Group Mute/Bypass State:** Same as the other node but for entire groups. Changes execution states (**Mute/Bypass/Active**) for all nodes within specified groups at once based on a group name search string (applies to the *next* prompt run). Node detection adapted from rgthree-comfy group muters/bypassers.

### 📝 Text & String Utilities
* **CB Textbox:** A simple text container that displays text, prints to screen and automatically overwrites its contents and converts any incoming data stream to a string. An improved version of the node from ComfyUI-Chibi-Nodes.
* **CB String Selector:** Splits a multiline or delimited string (by newlines, commas, or spaces) and returns a specific substring based on an index (supports modulo wrapping).
* **CB String List Match Index:** Compares an input string against a list of strings that are devided by a chosen delimiter. Supports custom matching modes (*Equal, Contains, Starts with, Ends with*) and returns a 1-based index (0 if not matched) and a boolean match state.

### 💾 Text Save/Load
* **CB Read Text File:** Loads raw text content from any specified file path relative to your ComfyUI output folder.
* **CB Save Text File:** Saves text strings into files with three operation modes: `overwrite` (replace), `append` (add to end), or `increment` (automatically generates numbered filenames like `config_00001.txt`). Also limited to ComfyUI output folder for safety reasons.

### 🔄 Type Conversion
* **CB Data type Converter:** Accepts **any** input connection type and safely converts it to a standard primitive: `STRING`, `FLOAT`, `INT`, or `BOOLEAN`.

---

## 🛠️ Installation and requirements

### Install Via ComfyUI Manager (clones the repo and installs `requirements.txt`)
1. Open ComfyUI and click on the **Manager** button.
2. Click **Custom Nodes Manager**.
3. Search for `ComfyUI CoolB Nodes` and click **Install**.
4. Restart ComfyUI.

**Requirements:** `torch`, `av`, `numpy`, and `pillow` come with ComfyUI natively. The only new requirement is `opencv-python` (`cv2`).

---

## 👥 Credits & Acknowledgements
This pack was vibecoded with Qwen, Gemini and DeepSeek. Some of the nodes were inspired by [Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack), [rgthree-comfy](https://github.com/rgthree/rgthree-comfy), [Chibi-Nodes](https://github.com/chibiace/ComfyUI-Chibi-Nodes), [Fill-Nodes](https://github.com/filliptm/ComfyUI_Fill-Nodes), [art-venture](https://github.com/sipherxyz/comfyui-art-venture), [Geeky_AudioMixer](https://github.com/GeekyGhost/ComfyUI_Geeky_AudioMixer), [WhiteRabbit](https://github.com/Artificial-Sweetener/WhiteRabbit) and [afloy_audio_tools](https://github.com/afloy011-spec/afloy_audio_tools).

---

## CHANGELOG
**V1.1.0**
* Added 6 new nodes: **CB Audio Info**, **CB Audio Processor**, **CB Roll and Trim Audio Samples**, **CB Roll and Trim Video Frames**, **CB Nearest Resolution**, **CB Color Correct**.
* Added `requirements.txt` to enable `opencv-python` (`cv2`) for **CB Color Correct** node.
