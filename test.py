import torchaudio
print(torchaudio.get_audio_backend())
torchaudio.set_audio_backend("sox_io")  # or "soundfile"