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
</head>
<body style="margin: 0; padding: 0; background: transparent; overflow: hidden;">
    <div id="status" style="font-family: sans-serif; font-size: 0.8rem; color: #94a3b8; font-weight: 500;"></div>
    <script>
        function sendMessageToStreamlit(type, data) {
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: type,
                ...data
            }, "*");
        }

        let lastSpokenText = "";
        let recognition = null;
        let isSpeaking = false;
        let isListening = false;

        function log(msg) {
            document.getElementById("status").innerText = msg;
            console.log("[AudioComponent] " + msg);
        }

        // Initialize Speech Recognition
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-US';

            recognition.onstart = function() {
                isListening = true;
                log("Listening... Speak now");
            };

            recognition.onresult = function(event) {
                const transcript = event.results[0][0].transcript;
                log("Transcript: " + transcript);
                sendMessageToStreamlit("streamlit:setComponentValue", { value: transcript });
            };

            recognition.onerror = function(event) {
                log("Recognition error: " + event.error);
                if (event.error === 'no-speech') {
                    sendMessageToStreamlit("streamlit:setComponentValue", { value: "ERROR: No speech detected" });
                } else if (event.error === 'not-allowed') {
                    sendMessageToStreamlit("streamlit:setComponentValue", { value: "ERROR: Microphone permission denied" });
                } else {
                    sendMessageToStreamlit("streamlit:setComponentValue", { value: "ERROR: " + event.error });
                }
            };

            recognition.onend = function() {
                isListening = false;
                log("Microphone closed");
            };
        } else {
            log("Speech recognition not supported in this browser");
        }

        function speak(text) {
            if (!window.speechSynthesis) {
                log("Speech synthesis not supported");
                return;
            }

            window.speechSynthesis.cancel(); // Stop any ongoing speech
            
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'en-US';
            utterance.rate = 1.0;
            utterance.pitch = 1.0;

            utterance.onstart = function() {
                isSpeaking = true;
                log("AI speaking...");
            };

            utterance.onend = function() {
                isSpeaking = false;
                log("Finished speaking. Activating microphone...");
                if (recognition && !isListening) {
                    try {
                        recognition.start();
                    } catch (e) {
                        log("Microphone error: " + e.message);
                    }
                }
            };

            utterance.onerror = function(event) {
                isSpeaking = false;
                log("Speech synthesis error: " + event.error);
            };

            window.speechSynthesis.speak(utterance);
        }

        // Listen for Streamlit render arguments
        window.addEventListener("message", (event) => {
            if (event.data.type === "streamlit:render") {
                sendMessageToStreamlit("streamlit:setFrameHeight", { height: 25 });

                const args = event.data.args;
                const ttsText = args.tts_text || "";

                // Only speak if text is non-empty and has changed
                if (ttsText && ttsText !== lastSpokenText) {
                    lastSpokenText = ttsText;
                    speak(ttsText);
                }
            }
        });

        // Component initialization
        sendMessageToStreamlit("streamlit:setComponentReady", { apiVersion: 1 });
        sendMessageToStreamlit("streamlit:setFrameHeight", { height: 25 });
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
