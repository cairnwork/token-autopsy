"""Generate the synthetic fixtures (no real content). Run: python tests/make_fixtures.py"""
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "projects", "-proj-a")


def ts(sec):
    return "2026-10-01T00:%02d:%02dZ" % (sec // 60, sec % 60)


def call(mid, sec, cr, cw, inp, out, tools=(), model="claude-opus-5-5"):
    lines = []
    blocks = [{"type": "text", "text": "x"}] + [
        {"type": "tool_use", "id": f"t{mid}{i}", "name": n, "input": inp_} for i, (n, inp_) in enumerate(tools)]
    for b in blocks:  # Claude Code writes one line per content block, usage repeated
        lines.append({"type": "assistant", "timestamp": ts(sec), "message": {
            "id": mid, "model": model, "role": "assistant", "content": [b],
            "usage": {"input_tokens": inp, "cache_read_input_tokens": cr,
                      "cache_creation_input_tokens": cw, "output_tokens": out}}})
    return lines


def big_result():
    return [{"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "content": "y" * 25000}]}}]


def write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for o in lines:
            f.write(json.dumps(o, separators=(",", ":")) + "\n")


def B(c):
    return ("Bash", {"command": c})


main = []
main += call("m1", 0, 0, 10000, 5, 100)                               # <50k
main += call("m2", 10, 60000, 1000, 5, 100, [B("ls src")])            # 50-200k, browse run starts
main += call("m3", 20, 61000, 500, 5, 100, [B("grep -r foo .")])
main += call("m4", 30, 62000, 500, 5, 100, [("Glob", {"pattern": "*.py"})])
main += call("m5", 40, 63000, 500, 5, 100, [("Read", {"file_path": "/x"})])  # run followed by Read: not waste
main += call("m6", 50, 64000, 500, 5, 100, [B("sleep 30 && echo ready")])    # sleep poll
main += call("m7", 60, 64500, 500, 5, 100, [B("kubectl get pods")])
main += call("m8", 70, 65000, 500, 5, 100, [B("kubectl get pods")])  # repeat within 60 s of m7
main += big_result()
main += call("m9", 200, 250000, 1000, 5, 200, [B("ls")])             # >200k, new browse run
main += call("m10", 210, 251000, 500, 5, 200, [B("find . -name x")])
main += call("m11", 220, 252000, 500, 5, 200, [B("rg bar")])          # run of 3, no follow-up: waste
main += call("m12", 230, 253000, 500, 5, 200, [B("echo done")], model="claude-sonnet-5-5")
write(os.path.join(ROOT, "sess-main.jsonl"), main)

sub = []
sub += call("s1", 0, 0, 30000, 5, 50)
sub += call("s2", 5, 30000, 500, 5, 50, [("Read", {"file_path": "/x"})])
sub += call("s3", 10, 30500, 500, 5, 50)
write(os.path.join(ROOT, "sess-main", "subagents", "agent-1.jsonl"), sub)
write(os.path.join(ROOT, "empty.jsonl"), [{"type": "user", "message": {"role": "user", "content": "hello"}}])
