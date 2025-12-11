from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from .models import GCodeLine

def parse_line(line: str, index: int) -> GCodeLine:
    """Parse a single G-code line."""
    raw = line.rstrip()
    comment = None
    if ';' in raw:
        parts = raw.split(';', 1)
        raw_cmd = parts[0].strip()
        comment = parts[1].strip()
    else:
        raw_cmd = raw.strip()

    if not raw_cmd:
        return GCodeLine(index=index, raw=raw, cmd="", params={}, comment=comment)

    parts = raw_cmd.split()
    cmd = parts[0].upper()
    params = {}

    for part in parts[1:]:
        if not part:
            continue
        key = part[0].upper()
        try:
            # Handle standard parameters like X10.5, S200
            # Some slicers might output parameters differently, but this is standard
            value = float(part[1:])
            params[key] = value
        except ValueError:
            # Handle non-numeric parameters or malformed parts if necessary
            # For now, ignore or store as 0 if critical, but standard G-code params are floats
            pass
            
    return GCodeLine(index=index, raw=raw, cmd=cmd, params=params, comment=comment)

def parse_gcode(file_path: str) -> List[GCodeLine]:
    """Parse a G-code file into a list of structured GCodeLine objects."""
    parsed_lines = []
    # newline='\n'을 지정하여 CR만 있는 줄바꿈을 무시하고 LF 기반으로만 처리
    # 이렇게 하면 CRLF(\r\n)도 정상적으로 하나의 줄로 처리됨
    with open(file_path, 'r', encoding='utf-8', errors='replace', newline='\n') as f:
        for i, line in enumerate(f):
            # CR 문자가 줄 끝에 남아있으면 제거
            line = line.rstrip('\r\n')
            parsed_lines.append(parse_line(line, i + 1))
    return parsed_lines
