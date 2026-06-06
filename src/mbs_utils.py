import pandas as pd
import re

def parse_mbs_price(price_str):
    """
    Parses MBS price strings from various formats into decimal.
    Supported formats:
    - Bloomberg 32nds with 8ths (e.g., '100-163' -> 100 + 16/32 + 3/256)
    - Standard 32nds (e.g., '100-16+')
    - Decimal strings
    """
    if pd.isna(price_str) or price_str == '': return None
    s = str(price_str).strip()
    if s in ['0', '0.0', '0.00', '.0', '0-00', '0-000', '0-00+', '0-0000']: return None

    # Format 1: Bloomberg style (Handle-Ticks-Eighths, e.g., 99-163)
    match = re.match(r'(\d+)-(\d{2})(\d)$', s)
    if match:
        return int(match.group(1)) + int(match.group(2))/32.0 + int(match.group(3))/256.0

    # Format 2: Standard 32nds with '+' (e.g., 99-16+)
    if '-' in s:
        try:
            parts = s.split('-')
            h, r = float(parts[0]), parts[1]
            ticks = float(r.replace('+', ''))
            extra = 0.5 if '+' in r else 0.0
            return h + (ticks + extra) / 32.0
        except: return None
        
    # Format 3: Decimal
    try: return float(s) if abs(float(s)) > 1e-6 else None
    except: return None

def format_32nds(x, pos=None):
    """ 
    Formats a decimal value into standard MBS 32nds notation.
    Example: 
      1.5 -> '1-16'
      0.03125 -> '0-01'
      0.046875 -> '0-01+' (Plus indicates half-tick / 1/64th)
    """
    if pd.isna(x): return ""
    sign = '-' if x < 0 else ''
    x = abs(x)
    
    handle = int(x)
    decimal_part = x - handle
    
    # Convert decimal part to 32nds
    ticks_float = decimal_part * 32.0
    ticks_int = int(ticks_float)
    
    # Check for half-tick (plus sign)
    remainder = ticks_float - ticks_int
    plus = ""
    
    if remainder > 0.8: # Round up to next tick if very close
        ticks_int += 1
    elif remainder > 0.2: # Add plus if near half-tick
        plus = "+"
        
    # Handle overflow (32 ticks = 1 full point)
    if ticks_int >= 32:
        handle += 1
        ticks_int = 0
        plus = ""
        
    return f"{sign}{handle}-{ticks_int:02d}{plus}"