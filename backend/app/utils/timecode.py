def seconds_to_srt_time(value: float) -> str:
    millis = int(round(value * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def srt_time_to_seconds(value: str) -> float:
    time_part, millis_part = value.strip().split(",")
    hours, minutes, seconds = [int(part) for part in time_part.split(":")]
    return hours * 3600 + minutes * 60 + seconds + int(millis_part) / 1000
