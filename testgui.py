import vlc
import time

audio_file = "./instrumentals/俏郎君/htdemucs/俏郎君/no_vocals.wav"

player = vlc.MediaPlayer(audio_file)
player.play()
time.sleep(0.2)

print("Playing audio...")

while True:
    state = player.get_state()
    if state in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]:
        print("Playback finished")
        break
    time.sleep(0.1)
