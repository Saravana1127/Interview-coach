import os
import streamlit.components.v1 as components

_component_func = components.declare_component(
    "proctoring",
    path=os.path.dirname(os.path.abspath(__file__))
)

def run_proctoring(tts_text: str = "", key=None):
    """
    Mounts the hidden proctoring component.
    Returns a dict with 'tabs', 'pastes', 'fs_exits' counts.
    """
    component_value = _component_func(tts_text=tts_text, key=key, default={"tabs": 0, "pastes": 0, "fs_exits": 0})
    return component_value
