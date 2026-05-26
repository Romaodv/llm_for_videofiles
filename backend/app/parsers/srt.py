import re
from dataclasses import dataclass

from backend.app.utils.timecode import seconds_to_srt_time, srt_time_to_seconds


@dataclass(frozen=True)
class SrtCue:
    index: int
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class TranscriptChunk:
    index: int
    start_seconds: float
    end_seconds: float
    text: str
    cues: list[SrtCue]


SRT_BLOCK_RE = re.compile(
    r"(?P<index>\d+)\s+"
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<text>.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)


def parse_srt(content: str) -> list[SrtCue]:
    cues: list[SrtCue] = []
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    for match in SRT_BLOCK_RE.finditer(normalized):
        text = " ".join(line.strip() for line in match.group("text").splitlines() if line.strip())
        cues.append(
            SrtCue(
                index=int(match.group("index")),
                start_seconds=srt_time_to_seconds(match.group("start")),
                end_seconds=srt_time_to_seconds(match.group("end")),
                text=text,
            )
        )
    return cues


def cues_to_srt(cues: list[SrtCue]) -> str:
    blocks = []
    for cue in cues:
        blocks.append(
            "\n".join(
                [
                    str(cue.index),
                    f"{seconds_to_srt_time(cue.start_seconds)} --> {seconds_to_srt_time(cue.end_seconds)}",
                    cue.text,
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def chunk_cues(cues: list[SrtCue], target_chars: int = 1000, overlap_cues: int = 2) -> list[TranscriptChunk]:
    chunks: list[TranscriptChunk] = []
    cursor = 0
    while cursor < len(cues):
        selected: list[SrtCue] = []
        char_count = 0
        while cursor + len(selected) < len(cues):
            cue = cues[cursor + len(selected)]
            next_len = len(cue.text) + 1
            if selected and char_count + next_len > target_chars:
                break
            selected.append(cue)
            char_count += next_len

        text = " ".join(cue.text for cue in selected)
        chunks.append(
            TranscriptChunk(
                index=len(chunks),
                start_seconds=selected[0].start_seconds,
                end_seconds=selected[-1].end_seconds,
                text=text,
                cues=selected,
            )
        )
        cursor += max(1, len(selected) - overlap_cues)
    return chunks
