from typing import List
from .models import GCodeLine

def extract_snippet(
    lines: List[GCodeLine],
    center_idx: int, # 1-based index from Anomaly
    window: int = 50,
    max_lines: int = 200
) -> str:
    """
    Extract a snippet of G-code around the center index.
    """
    # Convert 1-based index to 0-based list index
    idx_0 = center_idx - 1
    total = len(lines)
    
    start_0 = max(0, idx_0 - window)
    end_0 = min(total, idx_0 + window + 1) # +1 inclusive
    
    # If the range is too large (shouldn't be with window=50, total 101), 
    # but strictly checking max_lines
    snippet_lines = lines[start_0:end_0]
    
    if len(snippet_lines) > max_lines:
        # Re-center
        half = max_lines // 2
        start_0 = max(0, idx_0 - half)
        end_0 = min(total, idx_0 + half)
        snippet_lines = lines[start_0:end_0]
        
    # Format: "LineNumber: Command Params ; Comment"
    output = []
    for line in snippet_lines:
        content = line.raw.strip()
        output.append(f"{line.index}: {content}")
        
    return "\n".join(output)
