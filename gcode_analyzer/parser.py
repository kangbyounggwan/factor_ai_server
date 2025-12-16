from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel
from .models import GCodeLine
from dataclasses import dataclass


@dataclass
class ParseResult:
    """G-code 파싱 결과"""
    lines: List[GCodeLine]
    encoding: str
    is_fallback: bool  # latin-1 fallback으로 디코딩되었는지


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

def parse_gcode(file_path: str) -> ParseResult:
    """Parse a G-code file into a list of structured GCodeLine objects.

    Returns:
        ParseResult with lines, encoding used, and fallback flag
    """
    parsed_lines = []

    # 시도할 인코딩 목록 (우선순위 순)
    encodings = ['utf-8', 'cp949', 'euc-kr']

    content = None
    used_encoding = None
    is_fallback = False

    # 바이너리로 읽어서 인코딩 시도
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()

    for encoding in encodings:
        try:
            content = raw_bytes.decode(encoding)
            used_encoding = encoding
            break
        except (UnicodeDecodeError, LookupError):
            continue

    # 모든 인코딩 실패 시 latin-1로 강제 디코딩 (항상 성공)
    if content is None:
        content = raw_bytes.decode('latin-1', errors='replace')
        used_encoding = 'latin-1 (fallback)'
        is_fallback = True

    # 줄 단위로 파싱
    lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    for i, line in enumerate(lines):
        parsed_lines.append(parse_line(line, i + 1))

    return ParseResult(lines=parsed_lines, encoding=used_encoding, is_fallback=is_fallback)
