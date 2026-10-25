"""세대 진행 막대.

개체 평가가 하나 끝날 때마다 터미널의 같은 줄을 다시 그리고(``\\r``), 세대가 끝나면 결과 한 줄을 남깁니다::

    Gen   7/300 [██████████▍         ]  51% 37/72 | Best   31.6645 kW   |  4:12
    Gen   7/300 [████████████████████] 100% 72/72 | Best   31.6645 kW ▲ |  8:03 | WAMIT   436  Hits     0  Penalty   140

출력이 파일이나 파이프로 갈 때(계산용 PC의 ``run.log`` 등)는 다시 그리지 않고 세대마다 마지막 한 줄만 쓰며,
어느 프로그램으로 열어도 깨지지 않도록 ASCII 문자(``#``, ``-``, ``+``)를 씁니다. 세대 번호와 개수는
최대 자릿수에 맞춰 오른쪽 정렬하므로 1세대와 100세대의 줄 칸이 같습니다.
"""

import math
import shutil
import sys
import time

BAR_WIDTH = 20
REFRESH_SECONDS = 0.1  # 터미널을 다시 그리는 최소 간격 (빠른 평가 함수에서 출력이 밀리지 않게)
_UNICODE = {"fill": "█", "empty": " ", "parts": " ▏▎▍▌▋▊▉", "up": "▲"}
_ASCII = {"fill": "#", "empty": "-", "parts": "", "up": "+"}


def format_seconds(seconds):
    """``m:ss`` (한 시간 이상이면 ``h:mm:ss``), 분 자리는 두 칸으로 맞춥니다."""
    seconds = max(0, round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:2d}:{secs:02d}"


def _is_terminal(stream):
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _can_encode(stream, text):
    try:
        text.encode(getattr(stream, "encoding", None) or "ascii")
        return True
    except (LookupError, UnicodeEncodeError):
        return False


class GenerationProgress:
    """한 실행의 세대별 진행 막대. ``start`` → ``advance``(평가마다) → ``finish`` 순서로 부릅니다.

    :param max_iter: 최대 세대 수 (세대 번호의 자릿수)
    :param pop_size: 세대당 최대 평가 수 (개수의 자릿수)
    :param stream: 출력 스트림 (기본 ``sys.stdout``)
    :param live: 같은 줄을 다시 그릴지 여부 (기본: 스트림이 터미널이면 True)
    """

    def __init__(self, max_iter, pop_size, stream=None, live=None):
        self.stream = stream if stream is not None else sys.stdout
        self.live = _is_terminal(self.stream) if live is None else live
        unicode_ok = self.live and _can_encode(self.stream, "".join(_UNICODE.values()))
        self.chars = _UNICODE if unicode_ok else _ASCII
        self.max_iter = max_iter
        self.gen_width = len(str(max_iter))
        self.count_width = len(str(pop_size))
        self.stat_width = len(str(pop_size * (max_iter + 1)))
        self.label_width = len(self._label(max_iter))
        self.gen = self.total = self.done = 0
        self.best = self.prev_best = -math.inf
        self.started = self._last_draw = 0.0
        self._drawn = 0  # 지금 터미널 줄에 그려진 글자 수 (다시 그릴 때 남는 글자를 지움)

    def _label(self, gen):
        return f"Gen {gen:>{self.gen_width}}/{self.max_iter}"

    def start(self, gen, total, best=-math.inf):
        """세대 ``gen``(0이면 초기 개체군)을 시작합니다. ``total``은 이번 세대의 평가 수입니다."""
        self.gen, self.total, self.done = gen, max(1, total), 0
        self.best = self.prev_best = best
        self.started = time.time()
        self._last_draw = 0.0
        if self.live:
            self._draw(force=True)

    def advance(self, score=None):
        """평가 하나가 끝났을 때 부릅니다. ``score``가 지금까지의 최고값보다 크면 표시값을 바꿉니다."""
        self.done = min(self.done + 1, self.total)
        if score is not None and score > self.best:
            self.best = score
        if self.live:
            self._draw(force=self.done == self.total)

    def finish(self, best, evaluator=None):
        """세대 결과 한 줄을 씁니다. ``best``는 알고리즘이 확정한 최고값 [W]입니다."""
        self.done, self.best = self.total, best
        improved = self.gen > 0 and best > self.prev_best
        line = self._line(improved=improved)
        if evaluator is not None:
            w = self.stat_width
            line += (
                f" | WAMIT {evaluator.physics_evals:>{w}}  Hits {evaluator.cache_hits:>{w}}"
                f"  Penalty {evaluator.penalty_evals:>{w}}"
            )
        if self.live:
            self.stream.write("\r" + line.ljust(self._drawn) + "\n")
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
        self._drawn = 0

    def _bar(self):
        fraction = self.done / self.total
        parts = self.chars["parts"]
        cells = fraction * BAR_WIDTH
        full = int(cells)
        bar = self.chars["fill"] * full
        if full < BAR_WIDTH:
            if parts:
                bar += parts[int((cells - full) * len(parts))]
            else:
                bar += self.chars["empty"]
            bar += self.chars["empty"] * (BAR_WIDTH - full - 1)
        return bar

    def _line(self, improved=False):
        label = "Init" if self.gen == 0 else self._label(self.gen)
        best = "-" if self.best == -math.inf else f"{self.best / 1000:.4f}"
        mark = self.chars["up"] if improved else " "
        return (
            f"{label:<{self.label_width}} [{self._bar()}] {100 * self.done // self.total:3d}%"
            f" {self.done:>{self.count_width}}/{self.total:<{self.count_width}}"
            f" | Best {best:>9} kW {mark} | {format_seconds(time.time() - self.started)}"
        )

    def _draw(self, force=False):
        now = time.time()
        if not force and now - self._last_draw < REFRESH_SECONDS:
            return
        self._last_draw = now
        columns = shutil.get_terminal_size((120, 24)).columns
        line = self._line()[: max(1, columns - 1)]  # 줄이 넘치면 \r이 윗줄로 돌아가지 못함
        self.stream.write("\r" + line.ljust(self._drawn))
        self.stream.flush()
        self._drawn = len(line)
