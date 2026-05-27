import streamlit as st

try:
    from streamlit_webrtc import webrtc_streamer, RTCConfiguration, WebRtcMode
    _WEBRTC_AVAILABLE = True
except ImportError:
    _WEBRTC_AVAILABLE = False

_RTC_CONFIG = {
    "iceServers": [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {"urls": ["stun:stun1.l.google.com:19302"]},
    ]
}

def render_camera_feed(key: str = "hr-camera") -> bool:
    """
    Render a live webcam feed using streamlit-webrtc.
    Returns True if feed runs successfully, False otherwise.
    """
    if not _WEBRTC_AVAILABLE:
        st.warning("Camera unavailable - streamlit-webrtc is not installed.")
        return False

    try:
        ctx = webrtc_streamer(
            key=key,
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=RTCConfiguration(_RTC_CONFIG),
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
            desired_playing_state=True,
        )
        return ctx is not None and ctx.state.playing
    except Exception as exc:
        st.warning(f"Camera feed error: {exc}")
        return False
