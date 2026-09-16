import os
import importlib.util

try:
    from .nodes import SaveSpeaker, LoadSpeaker, SetMuteBypassState, Textbox, StringListMatchIndex, TextFileReader, TextFileWriter, StringSelector, SetGroupMuteBypassState, AnyToPrimitive
except ImportError:
    _nodes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes.py")
    _spec = importlib.util.spec_from_file_location("comfyui_speaker_pack_nodes", _nodes_path)
    _nodes = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_nodes)
    SaveSpeaker = _nodes.SaveSpeaker
    LoadSpeaker = _nodes.LoadSpeaker


NODE_CLASS_MAPPINGS = {
    "SaveSpeaker": SaveSpeaker,
    "LoadSpeaker": LoadSpeaker,
    "SetMuteBypassState": SetMuteBypassState,
    "CBTextbox": Textbox,
    "StringListMatchIndex": StringListMatchIndex,
    "TextFileReader": TextFileReader,
    "TextFileWriter": TextFileWriter,
    "CBStringSelector": StringSelector,
    "SetGroupMuteBypassState": SetGroupMuteBypassState,
    "AnyToPrimitive": AnyToPrimitive,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveSpeaker": "CB Save Speaker",
    "LoadSpeaker": "CB Load Speaker",
    "SetMuteBypassState": "CB Set Mute/Bypass State",
    "CBTextbox": "CB Textbox",
    "StringListMatchIndex": "CB String List Match Index",
    "TextFileReader": "CB Read Text File",
    "TextFileWriter": "CB Save Text File",
    "CBStringSelector": "CB String Selector",
    "SetGroupMuteBypassState": "CB Set Group Mute/Bypass State",
    "AnyToPrimitive": "CB Data type Converter",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

WEB_DIRECTORY = "./js"