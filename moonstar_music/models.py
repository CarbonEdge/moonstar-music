from pydantic import BaseModel, model_validator


class Section(BaseModel):
    name: str
    seconds: int
    prompt: str


class MusicBrief(BaseModel):
    title: str
    genre: str
    mood: str
    bpm: int
    key: str
    instrumental: bool
    lyrics: str | None = None
    duration_sec: int
    sections: list[Section]
    style_prompt: str

    @model_validator(mode="after")
    def _drop_lyrics_if_instrumental(self) -> "MusicBrief":
        if self.instrumental:
            self.lyrics = None
        return self
