"""
backend/video_handler.py — WebRTC camera handler for the HR interview mode.

Uses streamlit-webrtc. If the library is not installed or the browser
denies camera access, the session degrades gracefully to text-only mode.
"""

import streamlit as st

try:
    from streamlit_webrtc import webrtc_streamer, RTCConfiguration, WebRtcMode
    _WEBRTC_AVAILABLE = True
except ImportError:
    _WEBRTC_AVAILABLE = False

# Public STUN servers — sufficient for same-LAN or localhost use.
# For production deployments behind NAT, add TURN server credentials here.
_RTC_CONFIG = {
    "iceServers": [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {"urls": ["stun:stun1.l.google.com:19302"]},
    ]
}


def render_camera_feed(key: str = "hr-camera") -> bool:
    """
    Render a live webcam feed in the current Streamlit container.

    Returns True  — camera stream started successfully.
    Returns False — library unavailable or user denied camera access.
    """
    if not _WEBRTC_AVAILABLE:
        st.warning(
            "Camera unavailable — `streamlit-webrtc` is not installed.\n\n"
            "Install it with: `pip install streamlit-webrtc av`"
        )
        return False

    try:
        ctx = webrtc_streamer(
            key=key,
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=RTCConfiguration(_RTC_CONFIG),
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
        )
        return ctx is not None and ctx.state.playing
    except Exception as exc:
        st.warning(f"Camera error: {exc}")
        return False
