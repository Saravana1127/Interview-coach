import os
import streamlit.components.v1 as components

# Declare the custom component for automatic turn-taking voice interaction
_COMPONENT_NAME = "audio_turn"
_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", _COMPONENT_NAME)

if not os.path.exists(_COMPONENT_DIR):
    os.makedirs(_COMPONENT_DIR, exist_ok=True)

_HTML_PATH = os.path.join(_COMPONENT_DIR, "index.html")

_HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Audio Turn Taking Component</title>
    <style>
        @keyframes pulse {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.2); opacity: 0.6; }
            100% { transform: scale(1); opacity: 1; }
        }
        .pulsing {
            animation: pulse 1.5s infinite;
        }
        button:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }
        button:active {
            transform: translateY(0);
        }
    </style>
</head>
<body style="margin: 0; padding: 0; background: transparent; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <div style="display: flex; align-items: center; gap: 10px; padding: 4px 0;">
        <button id="micBtn" style="background: #6d28d9; color: white; border: none; border-radius: 20px; padding: 6px 14px; font-size: 0.8rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.2s; box-shadow: 0 2px 4px rgba(109, 40, 217, 0.2); outline: none;">
            <span id="micIcon" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22c55e;"></span>
            <span id="micText">Connecting</span>
        </button>
        <div id="status" style="font-size: 0.82rem; color: #475569; font-weight: 600;">Initializing audio loop...</div>
    </div>
    
    <script>
        function sendMessageToStreamlit(type, data) {
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: type,
                ...data
            }, "*");
        }

        const parentWin = window.parent || window;
        const SpeechRecognition = parentWin.SpeechRecognition || parentWin.webkitSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition;
        const speechSynthesis = parentWin.speechSynthesis || window.speechSynthesis;

        let lastSpokenText = "";
        let recognition = null;
        let isSpeaking = false;
        let isListening = false;

        const micBtn = document.getElementById("micBtn");
        const micIcon = document.getElementById("micIcon");
        const micText = document.getElementById("micText");
        const statusDiv = document.getElementById("status");

        function log(msg) {
            console.log("[AudioComponent] " + msg);
        }

        function updateMicUI(state, text) {
            if (state === "listening") {
                micBtn.style.background = "#6d28d9";
                micIcon.style.background = "#22c55e";
                micIcon.classList.add("pulsing");
                micText.innerText = "Listening";
                statusDiv.innerText = text || "Speak now...";
            } else if (state === "speaking") {
                micBtn.style.background = "#475569";
                micIcon.style.background = "#0891b2";
                micIcon.classList.remove("pulsing");
                micText.innerText = "AI Speaking";
                statusDiv.innerText = text || "Coach is speaking...";
            } else if (state === "error") {
                micBtn.style.background = "#dc2626";
                micIcon.style.background = "#ffffff";
                micIcon.classList.remove("pulsing");
                micText.innerText = "Mic Issue";
                statusDiv.innerText = text || "Click button to try again";
            } else {
                micBtn.style.background = "#0f172a";
                micIcon.style.background = "#94a3b8";
                micIcon.classList.remove("pulsing");
                micText.innerText = "Click to Speak";
                statusDiv.innerText = text || "Microphone closed";
            }
        }

        // Initialize Speech Recognition on parent context
        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-US';

            recognition.onstart = function() {
                isListening = true;
                updateMicUI("listening");
            };

            recognition.onresult = function(event) {
                const transcript = event.results[0][0].transcript;
                log("Transcript: " + transcript);
                statusDiv.innerText = "Transcribing...";
                sendMessageToStreamlit("streamlit:setComponentValue", { value: transcript });
            };

            recognition.onerror = function(event) {
                log("Recognition error: " + event.error);
                let errMsg = "ERROR: " + event.error;
                if (event.error === 'no-speech') {
                    errMsg = "ERROR: No speech detected";
                    updateMicUI("idle", "No speech heard. Click to talk.");
                } else if (event.error === 'not-allowed') {
                    errMsg = "ERROR: Microphone permission denied";
                    updateMicUI("error", "Microphone access blocked.");
                } else {
                    updateMicUI("error", "Error: " + event.error);
                }
                sendMessageToStreamlit("streamlit:setComponentValue", { value: errMsg });
            };

            recognition.onend = function() {
                isListening = false;
                if (micText.innerText === "Listening") {
                    updateMicUI("idle");
                }
            };
        } else {
            updateMicUI("error", "Speech recognition not supported");
        }

        function speak(text) {
            if (!speechSynthesis) {
                log("Speech synthesis not supported");
                return;
            }

            speechSynthesis.cancel(); // Stop any ongoing speech
            
            const utterance = new (parentWin.SpeechSynthesisUtterance || window.SpeechSynthesisUtterance)(text);
            utterance.lang = 'en-US';
            utterance.rate = 1.0;
            utterance.pitch = 1.0;

            utterance.onstart = function() {
                isSpeaking = true;
                if (recognition && isListening) {
                    recognition.stop();
                }
                updateMicUI("speaking");
            };

            utterance.onend = function() {
                isSpeaking = false;
                updateMicUI("listening", "Speak now...");
                if (recognition && !isListening) {
                    try {
                        recognition.start();
                    } catch (e) {
                        log("Microphone start error: " + e.message);
                    }
                }
            };

            utterance.onerror = function(event) {
                isSpeaking = false;
                log("Speech synthesis error: " + event.error);
                updateMicUI("idle", "TTS error. Click to respond.");
            };

            speechSynthesis.speak(utterance);
        }

        micBtn.onclick = function() {
            if (isSpeaking) {
                log("AI is currently speaking. Please wait.");
                return;
            }
            if (isListening) {
                if (recognition) {
                    recognition.stop();
                }
            } else {
                if (recognition) {
                    try {
                        recognition.start();
                    } catch (e) {
                        log("Microphone error: " + e.message);
                    }
                }
            }
        };

        // Listen for Streamlit render arguments
        window.addEventListener("message", (event) => {
            if (event.data.type === "streamlit:render") {
                sendMessageToStreamlit("streamlit:setFrameHeight", { height: 45 });

                const args = event.data.args;
                const ttsText = args.tts_text || "";

                if (ttsText && ttsText !== lastSpokenText) {
                    lastSpokenText = ttsText;
                    speak(ttsText);
                } else if (!isSpeaking && !isListening) {
                    updateMicUI("idle");
                }
            }
        });

        // Component initialization
        sendMessageToStreamlit("streamlit:componentReady", { apiVersion: 1 });
        sendMessageToStreamlit("streamlit:setFrameHeight", { height: 45 });
    </script>
</body>
</html>
"""

with open(_HTML_PATH, "w", encoding="utf-8") as f:
    f.write(_HTML_CONTENT)

_component_func = components.declare_component(
    _COMPONENT_NAME,
    path=_COMPONENT_DIR
)

def audio_component(tts_text: str = "", key=None):
    """
    Mount the custom audio turn-taking component.
    Plays tts_text, then automatically opens the browser microphone and listens.
    Returns the transcription string or "ERROR: <msg>".
    """
    return _component_func(tts_text=tts_text, key=key, default=None)
