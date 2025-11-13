import whisper
import os

song = '눈__코__입__Eyes_Nose_Lips_'

print(os.path.exists(f"./instrumentals/{song}/htdemucs/{song}/vocals.wav"))


model = whisper.load_model("medium")
result = model.transcribe(f"./instrumentals/{song}/htdemucs/{song}/vocals.wav")
for segment in result["segments"]:
    print(segment["start"], segment["end"], segment["text"])