"""실시간 진행 모니터 테스트 (SSH, WAMIT 없이 실행)."""

import base64
import io
import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from watch_progress import (  # noqa: E402
    AGENT_SECONDS,
    COMMAND_LIMIT,
    Screen,
    agent_command,
    find_targets,
    follow_local,
    format_trial,
    handle_agent_line,
    new_state,
    parse_local,
    progress_text,
    read_new_lines,
    read_settings,
    settings_label,
    status_text,
)

GEN_LINE = "Gen  27/300 [####] 100% 100/100 | Best   46.6762 kW + |  9:28 | WAMIT  2331  Hits  3  Penalty  466"


def script_of(command):
    return base64.b64decode(command.split()[-1]).decode("utf-16-le")


def run_started(state, site="Buan", mode="Geometry and Layout Optimization", seed=1, population=100):
    for text in (
        f"L|Sea state: [{site}] - Hs: 1.07 m",
        f"L|Mode: [{mode}] - Number of WEC: 5",
        f"L|Random seed: {seed}",
        f"L|Optimization started: evaluating the initial population of {population}...",
    ):
        handle_agent_line(text, state)


class TestSettings(unittest.TestCase):
    def test_host_and_root_are_read_and_comments_are_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "remote.pc2.local.psd1")
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write('# Host = "example"\n@{\n    Host         = "wec-2"\n    JobsRoot     = "D:\\jobs"\n}\n')
            self.assertEqual(read_settings(path), ("wec-2", "D:\\jobs"))
            self.assertEqual(find_targets(folder), [("PC2", "wec-2", "D:\\jobs")])

    def test_labels(self):
        self.assertEqual(settings_label("remote.local.psd1"), "PC1")
        self.assertEqual(settings_label("remote.pc2.local.psd1"), "PC2")

    def test_local_argument(self):
        self.assertEqual(parse_local(["LOCAL=logs/a.csv"]), [("LOCAL", "logs/a.csv")])
        with self.assertRaises(ValueError):
            parse_local(["logs/a.csv"])


class TestAgent(unittest.TestCase):
    def test_command_fits_the_remote_shell_and_carries_the_position(self):
        state = new_state() | {"job": "20261107_seeds", "log": 1234, "file": "a_trial_history.csv", "trial": 77}
        command = agent_command(r"C:\wec_jobs", state)
        self.assertLess(len(command), COMMAND_LIMIT)
        script = script_of(command)
        self.assertIn(r"$root='C:\wec_jobs'", script)
        self.assertIn("$j='20261107_seeds'", script)
        self.assertIn("$p=1234", script)
        self.assertIn("$q=77", script)
        self.assertNotIn("@ROOT@", script)

    def test_agent_ends_by_itself_so_a_lost_connection_leaves_nothing_running(self):
        script = script_of(agent_command("C:\\jobs", new_state()))
        self.assertIn(f"while($i -lt {AGENT_SECONDS})", script)
        self.assertIn("E|", script)
        self.assertLessEqual(AGENT_SECONDS, 300)

    def test_agent_only_reads_files(self):
        script = script_of(agent_command("C:\\jobs", new_state()))
        for word in ("Remove-Item", "Set-Content", "Add-Content", "Out-File", "Stop-Process"):
            self.assertNotIn(word, script)


class TestStatus(unittest.TestCase):
    def test_site_seed_method_generation_and_particle(self):
        state = new_state()
        handle_agent_line("J|job1", state)
        run_started(state)
        handle_agent_line("H|a.csv|v1,v2,fitness,p1,penalized", state)
        for _ in range(2818):
            handle_agent_line("T|2.5,4.8,45062.0,1,0", state)
        handle_agent_line("L|" + GEN_LINE, state)
        self.assertEqual(
            status_text(state),
            "Buan seed 1 simultaneous | Gen 28/300 | particle 21/100 | best 46.68 kW",
        )

    def test_generation_comes_from_the_log_when_designs_are_reused(self):
        state = new_state()
        run_started(state)
        handle_agent_line("H|a.csv|v1,fitness,p1,penalized", state)
        for _ in range(2800):  # 재사용한 설계는 평가 파일에 적히지 않습니다
            handle_agent_line("T|2.5,1.0,1,0", state)
        handle_agent_line(
            "L|Gen 299/300 [####] 100% 100/100 | Best 3.0 kW | 0:00 | WAMIT 2340 Hits 27000 Penalty 460", state
        )
        self.assertEqual(progress_text(state), "Gen 300/300 | particle 0/100")

    def test_catching_up_reads_the_log_before_the_evaluation_file(self):
        state = new_state()
        run_started(state)
        handle_agent_line("L|" + GEN_LINE, state)
        handle_agent_line("H|a.csv|v1,fitness,p1,penalized", state)
        for _ in range(2800):
            handle_agent_line("T|2.5,1.0,1,0", state)
        self.assertEqual(progress_text(state), "Gen 28/300 | particle 3/100")

    def test_header_row_is_not_counted(self):
        state = new_state()
        run_started(state)
        handle_agent_line("T|v1,v2,fitness,p1,penalized", state)
        handle_agent_line("T|2.5,4.8,45062.0,1,0", state)
        self.assertEqual(state["rows"], 1)
        self.assertEqual(progress_text(state), "Init | particle 1/100")

    def test_rejected_designs_count_as_particles(self):
        state = new_state()
        run_started(state)
        handle_agent_line("H|a.csv|v1,fitness,p1,penalized", state)
        handle_agent_line("T|2.5,0,0,1", state)
        self.assertEqual(state["rows"], 1)

    def test_new_run_starts_counting_again(self):
        state = new_state()
        run_started(state, mode="Geometry Optimization", population=20)
        state["rows"] = 500
        handle_agent_line("L|=== Optimization Finished ===", state)
        self.assertEqual(progress_text(state), "finished")
        run_started(state, mode="Layout Optimization", seed=2)
        self.assertEqual(state["rows"], 0)
        self.assertEqual(state["method"], "layout")
        self.assertEqual(state["seed"], "2")
        self.assertFalse(state["finished"])

    def test_finished_job_is_stated(self):
        state = new_state()
        handle_agent_line("J|job1", state)
        self.assertIsNone(handle_agent_line("S|running", state))
        self.assertTrue(state["ready"])
        self.assertEqual(handle_agent_line("S|done", state), "job state: done")
        self.assertEqual(status_text(state), "job done: job1")

    def test_generation_and_finish_become_events(self):
        state = new_state()
        run_started(state)
        self.assertEqual(
            handle_agent_line("L|" + GEN_LINE, state),
            "Buan seed 1 simultaneous Gen 27/300 done, best 46.68 kW, WAMIT 2331",
        )
        self.assertEqual(
            handle_agent_line("L|Best fitness : 45.0620 kW", state),
            "Buan seed 1 simultaneous finished, best 45.06 kW",
        )

    def test_other_log_lines_stay_quiet_unless_verbose(self):
        state = new_state()
        line = "L|WEC shape: cylinder + hemisphere"
        self.assertIsNone(handle_agent_line(line, state))
        self.assertEqual(handle_agent_line(line, state, verbose=True), "WEC shape: cylinder + hemisphere")
        self.assertEqual(handle_agent_line("L|Traceback (most recent call last):", state)[:9], "Traceback")

    def test_trials_are_shown_only_when_verbose_and_caught_up(self):
        state = new_state()
        handle_agent_line("H|a.csv|v1,v2,fitness,p1,penalized", state)
        trial = "T|2.5,4.8,45062.0,1,0"
        self.assertIsNone(handle_agent_line(trial, state))
        self.assertIsNone(handle_agent_line(trial, state, verbose=True))
        handle_agent_line("P|10", state)
        self.assertEqual(handle_agent_line(trial, state, verbose=True), "trial   45.062 kW | 2.5 4.8")

    def test_positions_are_kept_for_a_reconnect(self):
        state = new_state()
        self.assertEqual(handle_agent_line("J|job1", state), "job job1")
        self.assertIsNone(handle_agent_line("J|job1", state))
        self.assertIsNone(handle_agent_line("P|500\r\n", state))
        self.assertIsNone(handle_agent_line("Q|a_trial_history.csv|90\r\n", state))
        self.assertIsNone(handle_agent_line("E|", state))
        self.assertEqual((state["log"], state["file"], state["trial"]), (500, "a_trial_history.csv", 90))
        self.assertTrue(state["ended"])

    def test_broken_trial_line_is_ignored(self):
        self.assertIsNone(format_trial("2.5,abc", 1))
        self.assertIsNone(format_trial("2.5,4.8", None))


class TestScreen(unittest.TestCase):
    def test_events_stay_and_the_status_lines_are_redrawn_in_place(self):
        out = io.StringIO()
        screen = Screen(["PC1", "PC2"], stream=out, live=True)
        screen.set_status("PC1", "a")
        screen.set_status("PC2", "b")
        screen.show("PC1", "event one")
        screen.set_status("PC1", "c")
        text = out.getvalue()
        self.assertEqual(text.count("event one"), 1)
        self.assertIn("\033[2A\033[J", text)
        self.assertTrue(text.endswith("PC1 | c\nPC2 | b\n"))
        self.assertNotIn("\033[2J", text)

    def test_files_get_events_without_control_characters(self):
        out = io.StringIO()
        screen = Screen(["PC1"], stream=out, live=False)
        screen.set_status("PC1", "a")
        screen.show("PC1", "event")
        self.assertNotIn("\033", out.getvalue())
        self.assertIn("event", out.getvalue())


class TestLocalFile(unittest.TestCase):
    def test_only_finished_lines_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "a.txt")
            with open(path, "wb") as f:
                f.write(b"one\r\ntwo\r\nunfinis")
            lines, position = read_new_lines(path, 0)
            self.assertEqual(lines, ["one", "two"])
            with open(path, "ab") as f:
                f.write(b"hed\n")
            lines, _ = read_new_lines(path, position)
            self.assertEqual(lines, ["unfinished"])

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(read_new_lines("no_such_file.txt", 5), ([], 5))

    def test_stopping_is_clean(self):
        stop = threading.Event()
        stop.set()
        out = io.StringIO()
        follow_local("LOCAL", "no_such_file.txt", Screen(["LOCAL"], stream=out, live=False), stop=stop)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
