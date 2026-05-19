import os, re, sys
sys.stdout.reconfigure(encoding='utf-8')

raw_dir = r"G:/Mi unidad/JME/raw/actas"
cur_dir = r"G:/Mi unidad/JME/actas"
md_dir  = r"G:/Mi unidad/JME/markdown/actas"

def norm_raw(name):
    m = re.match(r"Acta 0*(\d+)\s*\(\s*(\d+)\s*\)\s*(\d{1,2})-(\d{1,2})-(\d{1,2})", name)
    if m:
        num, ycode, d, mo, y2 = m.groups()
        year = 2000 + int(y2)
        return ('ordinary', int(num), year, f"{year}-{int(mo):02d}-{int(d):02d}")
    m = re.match(r"Acta Extraordinaria N[°ºÂ]?[°ºÂ]?\s*0*(\d+)\s*\(\s*(\d{1,2})-(\d{1,2})-(\d{2,4})", name)
    if m:
        num, d, mo, y = m.groups()
        y = int(y); year = y if y > 100 else 2000+y
        return ('extra', int(num), year, f"{year}-{int(mo):02d}-{int(d):02d}")
    m = re.match(r"Acta Extraordinaria N[°Â]?\s*0*(\d+)\s*-\s*(\d{1,2})-(\w+)-(\d{4})", name)
    if m:
        num, d, mo_name, y = m.groups()
        months = {'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12}
        mo = months.get(mo_name.lower(), 0)
        return ('extra', int(num), int(y), f"{y}-{mo:02d}-{int(d):02d}")
    return None

raw_entries = {}
unmatched_raw = []
for f in sorted(os.listdir(raw_dir)):
    if not f.lower().endswith('.pdf'): continue
    k = norm_raw(f)
    if k:
        kind, num, year, date = k
        key = (kind, num, year)
        raw_entries.setdefault(key, []).append(f)
    else:
        unmatched_raw.append(f)

cur_ordinary = {}
cur_extra = {}
cur_other = []
md_files = set(os.listdir(md_dir))
for f in sorted(os.listdir(cur_dir)):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2}) - Acta (\d+)-(\d{4})", f)
    if m:
        cur_ordinary[(int(m.group(4)), int(m.group(5)))] = f
        continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2}) - Acta Extraordinaria (\d+)-(\d{4})", f)
    if m:
        cur_extra[(int(m.group(4)), int(m.group(5)))] = f
        continue
    cur_other.append(f)

print(f"Raw unique sessions: ordinary={sum(1 for k in raw_entries if k[0]=='ordinary')}  extra={sum(1 for k in raw_entries if k[0]=='extra')}  unmatched={len(unmatched_raw)}")
print(f"Curated:             ordinary={len(cur_ordinary)}  extra={len(cur_extra)}  other={len(cur_other)}")
print()
print("Curated 'other' (special):")
for o in cur_other: print(" -", o)
print()
print("Raw unmatched by regex:")
for u in unmatched_raw: print(" -", u)

print()
print("=== RAW ORDINARY MISSING IN CURATED ORDINARY ===")
for key in sorted(k for k in raw_entries if k[0]=='ordinary'):
    _, num, year = key
    if (num, year) not in cur_ordinary:
        print(f"  MISSING: Acta {num}-{year}  ← raw: {raw_entries[key][0]}")

print()
print("=== RAW EXTRA mapped to curated (any form) ===")
miss = []
for key in sorted(k for k in raw_entries if k[0]=='extra'):
    _, num, year = key
    # Curated stored either as 'Acta Extraordinaria N-YYYY' or as ordinary 'Acta N-YYYY' (low number)
    if (num, year) in cur_extra:
        print(f"  ✓ Extra {num}-{year} -> {cur_extra[(num,year)]}")
    elif (num, year) in cur_ordinary:
        print(f"  ✓ Extra {num}-{year} -> (as ordinary) {cur_ordinary[(num,year)]}")
    else:
        miss.append((num,year))
        print(f"  ✗ MISSING Extra {num}-{year} ← raw: {raw_entries[key][0]}")

print()
print("=== Check OCR markdown availability for missing curated ===")
print("md_dir file count:", len(md_files))
