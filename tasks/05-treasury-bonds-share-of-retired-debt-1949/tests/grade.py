"""Deterministic verifier for a numeric-answer task: the one number the agent's reply
commits to, checked against the task's accepted ranges (tests/answer.json). No model,
no key, no network.

The reply is every message the agent wrote, in order (Harbor's ATIF trajectory), or the
oracle's output when there is no trajectory. The number is read as the task's assertion
states it: the last ANSWER line, else the last stated numeric result; currency symbols,
thousands separators, percent signs and unit words are ignored (unit words never
rescale); a leading minus, a Unicode minus or accounting parentheses make it negative.

extract(reply) -> Extraction(value, how, candidates, flags, segment), where `how` is
  answer_line  the last line that starts with ANSWER (any case, markdown tolerated)
  last_number  no ANSWER line: the last stated number that is not a year, page or id
  abstain      the ANSWER line says the value cannot be determined
  status_msg   no ANSWER line and the reply is a progress note ("I'm waiting on…")
  harness_msg  the reply is a harness failure message (time limit, exit code)
  none         an empty reply, or no number at all
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

AGENT_TRAJECTORY = Path(os.environ.get("TRAJECTORY_PATH", "/logs/agent/trajectory.json"))
ORACLE_OUTPUT = Path(os.environ.get("ORACLE_OUTPUT_PATH", "/logs/agent/oracle.txt"))
ANSWER = Path(os.environ.get("ANSWER_PATH", "/tests/answer.json"))
OUT_DIR = Path(os.environ.get("VERIFIER_LOGS", "/logs/verifier"))

_LATEX = [
    (re.compile(r"\\\$"), "$"),
    (re.compile(r"\{,\}"), ","),
    (re.compile(r"\\[,;:! ]"), ""),
    (re.compile(r"\\\(|\\\)|\\\[|\\\]"), " "),
    (re.compile(r"\\(?:text|mathrm|mathbf|textbf|operatorname)\{([^{}]*)\}"), r"\1"),
    (re.compile(r"\$\$"), " "),
    (re.compile(r"\\(?:approx|times|cdot|quad|qquad)"), " "),
]
#: True minus signs (always negative).
_MINUS = "\u2212\ufe63\uff0d"
#: A figure or en dash glued to a number acts as a minus; a spaced dash is punctuation.
_DASH_ATTACHED = re.compile("[\u2012\u2013](?=[$\\d])")
#: No-break, thin, narrow and figure spaces inside numbers.
_SPACES = "\u00a0\u2009\u202f\u2007"
ANSWER_LINE = re.compile(
    r"(?im)^[\s>#*_`|-]*(?:\*\*)?\s*(?:final\s+)?answer\s*(?:\*\*)?\s*[:：=—-]\s*(?:\*\*)?(.*)$"
)
NUM = re.compile(
    r"""
    (?P<open>\()?\s*
    (?P<sign>-)?
    (?P<cur>[$€£])?\s*
    (?P<sign2>-)?
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)
    (?P<close>\s*\))?
    """,
    re.X,
)
ABSTAIN = re.compile(
    r"(?i)\b(does\s+not\s+contain|do(?:es)?n\'t\s+contain|no\s+(?:data|figures?)\s+(?:for|on)|"
    r"not\s+determinable|cannot\s+be\s+determined|can(?:no|\')t\s+determine|"
    r"unable\s+to\s+determine|not\s+(?:available|found|in\s+the\s+corpus|present)|"
    r"insufficient|n/?a\b|unknown|no\s+answer)"
)
STATUS = re.compile(
    r"(?i)\b(i'?m (?:waiting|holding|checking|extracting|using)|"
    r"i'?ll (?:report|give|pick|follow|update|reply|post|send)|still running|"
    r"background (?:agent|search)|subagent|search agent|let me\b|current step|"
    r"i'?ve (?:started|handed|now isolated)|next,? i)"
)
HARNESS = re.compile(
    r"(?i)could not finish within the time limit|failed to produce an answer \(exit"
)
CORRECTION = re.compile(
    r"(?i)\b(is\s+wrong|incorrect|instead|correct(?:ed)?\s+(?:value|answer)\s+is|should\s+be)\b|→|->"
)
YEARISH = re.compile(r"^(1[6-9]\d\d|20\d\d)$")
PAGE_REF = re.compile(
    r"(?i)\b(?:page|pp?\.|pdf\s+p\.?|table|line|row|col(?:umn)?|no\.|#|account|series|"
    r"section|part)\s*$"
)
YEAR_REF = re.compile(
    r"(?i)\b(?:fy|fiscal(?:\s+year)?|year|in|of|for|through|to|from|june\s+30,?|"
    r"december\s+31,?|since)\s*$"
)


@dataclass
class Extraction:
    value: float | None
    how: str
    candidates: list[float] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    segment: str = ""


def normalize(text: str) -> str:
    t = text or ""
    for rx, rep in _LATEX:
        t = rx.sub(rep, t)
    for ch in _MINUS:
        t = t.replace(ch, "-")
    t = _DASH_ATTACHED.sub("-", t)
    t = re.sub(rf"(?<=\d)[{_SPACES}](?=\d{{3}}\b)", ",", t)  # 1 234 567 with thin spaces
    t = re.sub(r"[*_`]", "", t)
    return t


def _context_drop(seg: str, m: re.Match) -> str | None:
    """Why a number match is not the answer (part of a file name, a page, a task id, a
    fiscal year, a footnote), or None."""
    s, e = m.span("num")
    before, after = seg[max(0, s - 12) : s], seg[e : e + 6]
    raw = m.group("num")
    if re.search(r"[A-Za-z_]$", before) or re.match(r"[A-Za-z_]", after):  # cs-1941, P092
        if not re.search(r"(?i)(?:US|USD|\$)\s*$", before):
            return "glued to letters"
    if re.search(r"[-_./]$", before) and re.search(r"[A-Za-z]", before[-6:]):  # cs-1990
        return "file name"
    if PAGE_REF.search(before):
        return "page/table/line reference"
    if YEAR_REF.search(before) and YEARISH.match(raw):
        return "year"
    if (
        YEARISH.match(raw)
        and not m.group("cur")
        and (
            re.match(r"\s*[-–]\s*\d{2,4}\b", seg[e : e + 8])
            or re.search(r"\d{2,4}\s*[-–]\s*$", before)
        )
    ):
        return "year range"
    return None


def _candidates(seg: str) -> list[tuple[float, re.Match, str | None]]:
    out = []
    for m in NUM.finditer(seg):
        raw = m.group("num")
        if not raw:
            continue
        v = float(raw.replace(",", ""))
        signed = bool(m.group("sign") or m.group("sign2"))
        neg = signed or (bool(m.group("open")) and bool(m.group("close")))
        if signed:
            # a hyphen right after a word or digit (cs-1990, 15-0328) is not a minus sign
            s = m.start("sign") if m.group("sign") else m.start("sign2")
            if s > 0 and re.match(r"[A-Za-z0-9]", seg[s - 1]):
                neg = False
        out.append((-v if neg else v, m, _context_drop(seg, m)))
    return out


def extract(reply: str) -> Extraction:
    if not reply or not reply.strip():
        return Extraction(None, "none")
    if HARNESS.search(reply) and not ANSWER_LINE.search(normalize(reply)):
        return Extraction(None, "harness_msg")
    t = normalize(reply)
    lines = ANSWER_LINE.findall(t)
    if lines:
        return _from_answer_line(lines[-1].strip(), several=len(lines) > 1)
    status = bool(STATUS.search(t))
    flags = ["no ANSWER line"] + (["progress/status message"] if status else [])
    amounts = []
    for v, m, why in _candidates(t):
        raw = m.group("num")
        after = t[m.end("num") : m.end("num") + 2].lstrip()
        is_amount = bool(m.group("cur")) or "." in raw or "," in raw or after.startswith("%")
        if why is None and is_amount and not (YEARISH.match(raw) and not m.group("cur")):
            amounts.append(v)
    if not amounts:
        return Extraction(None, "status_msg" if status else "none", flags=flags, segment=t[-160:])
    return Extraction(amounts[-1], "last_number", amounts[-5:], flags, t[-160:])


def _from_answer_line(seg: str, *, several: bool) -> Extraction:
    flags = ["several ANSWER lines"] if several else []
    cands = _candidates(seg)
    kept = [(v, m) for v, m, why in cands if why is None]
    if not kept:
        if ABSTAIN.search(seg) or not cands:
            how = "abstain" if ABSTAIN.search(seg) or seg else "none"
            return Extraction(None, how, segment=seg[:160], flags=flags)
        kept = [(v, m) for v, m, _ in cands]
        flags.append("only context-numbers on ANSWER line")
    lead = seg[: kept[0][1].start()]
    if ABSTAIN.search(lead) and len(lead) > 3:
        flags.append("abstain wording before the number")
        return Extraction(None, "abstain", [v for v, _ in kept], flags, seg[:160])
    pick = kept[-1] if CORRECTION.search(seg) and len(kept) > 1 else kept[0]
    if len(kept) > 1:
        which = " (correction: took the last)" if pick is kept[-1] else " (took the first)"
        flags.append("several numbers on ANSWER line" + which)
    return Extraction(pick[0], "answer_line", [v for v, _ in kept], flags, seg[:160])


def grade(reply: str, ranges: list[tuple[float, float]]) -> tuple[bool, Extraction]:
    """Pass when the committed number lies inside any accepted range, inclusive."""
    ex = extract(reply)
    inside = ex.value is not None and any(lo - 1e-9 <= ex.value <= hi + 1e-9 for lo, hi in ranges)
    return inside, ex


# ---------------------------------------------------------------- Harbor verifier


def _text(message) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return "\n".join(
            p.get("text") or f"[{p.get('type')}]" for p in message if isinstance(p, dict)
        )
    return "" if message is None else json.dumps(message, ensure_ascii=False)


def agent_reply(trajectory: dict) -> str:
    """Every message the agent wrote, in order: the last ANSWER line anywhere wins, as
    on Bench where the candidate's reply is one message."""
    messages = [
        _text(step.get("message")).strip()
        for step in trajectory.get("steps", [])
        if step.get("source") == "agent"
    ]
    return "\n\n".join(m for m in messages if m)


def read_reply() -> tuple[str, str]:
    """The reply and where it came from: the agent's trajectory, the oracle's output,
    or nothing (graded as an empty reply, never a verifier error)."""
    if AGENT_TRAJECTORY.is_file():
        doc = json.loads(AGENT_TRAJECTORY.read_text())
        if isinstance(doc, dict) and isinstance(doc.get("steps"), list):
            return agent_reply(doc), "trajectory"
    if ORACLE_OUTPUT.is_file():
        return ORACLE_OUTPUT.read_text().strip(), "oracle"
    return "", "none"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not ANSWER.is_file():
        print(f"{ANSWER} is missing: this task cannot be graded", file=sys.stderr)
        return 2
    answer = json.loads(ANSWER.read_text())
    ranges = [(float(lo), float(hi)) for lo, hi in answer["ranges"]]
    reply, source = read_reply()
    passed, extraction = grade(reply, ranges)
    reward = {"reward": 1.0 if passed else 0.0}
    verdict = {
        "passed": passed,
        "expected": answer.get("expected"),
        "ranges": ranges,
        "reply_source": source,
        **asdict(extraction),
    }
    (OUT_DIR / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n")
    (OUT_DIR / "reward.json").write_text(json.dumps(reward))
    print(json.dumps(reward))
    return 0


if __name__ == "__main__":
    sys.exit(main())
