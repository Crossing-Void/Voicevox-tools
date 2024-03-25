from voicevox import Client as ClientBase
from dataclasses import dataclass, field
from typing import ClassVar, Union
import sounddevice
import asyncio
import numpy
import json
import os


log_path = ".\\data\\voicevox\\log"
wav_file_saving_path = ".\\sounds\\voicevox"


class Client:

    def __init__(self, localhost: str = "127.0.0.1", port: str = "50021") -> None:
        self.http = f"http://{localhost}:{port}"
        self.client = ClientBase(self.http)
        _Voice.client = self.client  # initialize _Voice class's client

    async def log(self):
        async def log_config():
            tasks = [
                self.client.check_devices(),
                self.client.fetch_core_versions(),
                self.client.fetch_engine_version()
            ]
            result = await asyncio.gather(*tasks)

            config_info = {
                "supportModes": {
                    "cpu": result[0].cpu,
                    "cuda": result[0].cuda,
                    "dml": result[0].dml
                },
                "coreVersions": result[1],
                "engineVersion": result[2]
            }
            with open(os.path.join(log_path, "config.json"), "w", encoding="utf-8") as f:
                json.dump(config_info, f, indent=4, ensure_ascii="False")

        async def log_speakers():
            speakers = await self.client.fetch_speakers()
            speakers_info = []
            for speaker in speakers:
                speakers_info.append(
                    {
                        "name": speaker.name,
                        "uuid": speaker.uuid,
                        "version": speaker.version,
                        "canMorphing": speaker.supported_features.permitted_synthesis_morphing,
                        "styles": [
                            {"style": style.name, "id": style.id} for style in speaker.styles
                        ]
                    }
                )
            with open(os.path.join(log_path, "speakers.json"), "w", encoding="utf-8") as f:
                json.dump(speakers_info, f, indent=4, ensure_ascii=False)

        # build folder
        try:
            os.makedirs(log_path)
        except FileExistsError:
            pass
        tasks = [
            log_config(),
            log_speakers(),
        ]
        await asyncio.gather(*tasks)

    def add_text_in_database(self, text: str, speaker_id: int, **modify):
        """
        modify arguments include

        speed_scale: float, speed(速度)
        pitch_scale: float, pitch(音高)
        intonation_scale: float, intonation(抑揚)
        volume_scale: float, volume(音量)
        pre_phoneme_length: float, start no voice(開始無音)
        post_phoneme_length: float, end no voice(結束無音)

        """
        if len(text) > StringLengthTooMuchError.max_length:
            raise StringLengthTooMuchError("Text do not exceed 50 charcters")

        voice = _Voice(text, speaker_id, modify)
        return voice

    async def create_audio_data(self, objs: Union[list['_Voice'], '_Voice']):
        tasks = [obj.to_audio_data() for obj in objs]
        await asyncio.gather(*tasks)

    def play_audio(self, objs: Union[list['_Voice'], '_Voice']):
        for obj in objs:
            obj.play_audio()

    async def save_audio(self, objs: Union[list['_Voice'], '_Voice']):
        for obj in objs:
            await obj.save_audio(filename=f"{obj.text}_{obj.speaker_id}")


@dataclass
class _Voice:
    voice_base: ClassVar[list] = []
    client: ClassVar[ClientBase] = None

    text: str
    speaker_id: int
    modify: dict

    def __post_init__(self):
        self.audio_data = None

    async def to_audio_data(self):
        """
        making _Voice object's audio_data a bytes data
        """
        # judge had built before?
        for voice in _Voice.voice_base:
            if self == voice:
                # had built
                self.audio_data = voice.audio_data
                break
        else:
            # ----- build -----
            core_version = (await self.__class__.client.fetch_core_versions())[0]
            raw_audio_data = await self.__class__.client.create_audio_query(self.text, self.speaker_id, core_version=core_version)

            # modify
            for attr in self.modify:
                if hasattr(raw_audio_data, attr):
                    raw_audio_data.__dict__[attr] = self.modify[attr]

            self.sampling_rate = raw_audio_data.output_sampling_rate
            self.audio_data = await raw_audio_data.synthesis(speaker=self.speaker_id)

            # ----- build -----
        _Voice.voice_base.append(self)

    async def save_audio(self, path=wav_file_saving_path, filename: str = None):
        def write():
            with open(os.path.join(path, f"{filename}.wav"), "wb") as f:
                f.write(self.audio_data)
        try:
            os.makedirs(path)
        except FileExistsError:
            pass
        await asyncio.get_event_loop().run_in_executor(None, write)

    def play_audio(self):
        audio_array = numpy.frombuffer(self.audio_data, dtype=numpy.int16)
        sounddevice.play(audio_array, self.sampling_rate, blocking=True)


class StringLengthTooMuchError(Exception):
    max_length = 20

    def __init__(self, *args: object) -> None:
        super().__init__(*args)

    def __str__(self):
        return str(*self.args)

    def __repr__(self) -> str:
        return super().__repr__()


if __name__ == "__main__":
    async def main():
        client = Client()

        audio1 = client.add_text_in_database("ありがとうございます。", 2, speed_scale=2.0)
        audio2 = client.add_text_in_database("ぶーはぁおいっす", 2)
        await client.create_audio_data([audio1, audio2])

    asyncio.run(main())
