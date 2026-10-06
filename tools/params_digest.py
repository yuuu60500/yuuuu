"""ParamsDigest() of a source tree with every input at its default - the value
an untouched build logs as params= on its HMI-BUILD-BEGIN line.

Reads the format string and argument list straight out of ParamsDigest() in
H4M5_Identification.mq5 and the defaults out of the input declarations, then
does what the MQL does: StringFormat, then 32-bit FNV-1a over the characters.

    python3 tools/params_digest.py [MQL5/Indicators/HMI]
"""
import pathlib, re, sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "MQL5/Indicators/HMI")
src = "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.glob("*.mq*")))
enums = {}
for body in re.findall(r"enum\s+\w+\s*\{([^}]*)\}", src):
    names = [re.sub(r"//.*", "", x).strip().split("=")[0].strip() for x in body.split(",")]
    for i, n in enumerate([n for n in names if n]):
        enums[n] = i
defaults = {}
for typ, name, val in re.findall(r"^\s*input\s+(\w+)\s+(Inp\w+)\s*=\s*([^;]+);", src, re.M):
    v = val.strip()
    defaults[name] = 1 if v == "true" else 0 if v == "false" else enums[v] if v in enums else float(v) if typ == "double" else int(v) if re.fullmatch(r"-?\d+", v) else v

main = (root / "H4M5_Identification.mq5").read_text(encoding="utf-8")
m = re.search(r'string s = StringFormat\("([^"]+)",(.*?)\);', main, re.S)
fmt = m.group(1)
args = [re.sub(r"\(int\)", "", a).strip() for a in m.group(2).replace("\n", " ").split(",") if a.strip()]
vals = [defaults[a] for a in args]
specs = re.findall(r"%[.\d]*[a-zA-Z]", fmt)
assert len(specs) == len(vals), (len(specs), len(vals))
s = fmt.replace("%d", "{}").replace("%.8f", "{:.8f}")
s = s.format(*[int(v) if sp == "%d" else float(v) for v, sp in zip(vals, specs)])
h = 0x811C9DC5
for ch in s:
    h ^= ord(ch)
    h = (h * 16777619) & 0xFFFFFFFF
print(f"inputs in digest: {len(args)}")
print(f"string: {s}")
print(f"params={h:08X}")
