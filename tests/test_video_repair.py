"""Dry-run repair reports damaged timestamp files without changing inputs."""

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import av
import numpy as np

from video_repair import repair_directory, repair_video


class RepairPacketCountTest(unittest.TestCase):
    def test_extra_last_timestamp_is_dropped_before_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "camera.mp4"
            with av.open(str(video), "w") as container:
                stream = container.add_stream("libx264", rate=30)
                stream.width = stream.height = 16
                stream.pix_fmt = "yuv420p"
                stream.options = {"bf": "0"}
                for value in (0, 128):
                    frame = av.VideoFrame.from_ndarray(
                        np.full((16, 16, 3), value, dtype=np.uint8), format="rgb24"
                    )
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            video.with_suffix(".pts").write_text("33.000\n66.000\n0.000\n")

            original_video = video.read_bytes()
            original_pts = video.with_suffix(".pts").read_bytes()
            with av.open(str(video)) as container:
                source_timestamps = [
                    (str(packet.pts), str(packet.dts),
                     str(packet.time_base.numerator), str(packet.time_base.denominator))
                    for packet in container.demux(video=0) if packet.dts is not None
                ]
            self.assertEqual(repair_video(video, dry_run=True), 0)
            self.assertEqual(video.read_bytes(), original_video)
            self.assertEqual(video.with_suffix(".pts").read_bytes(), original_pts)
            self.assertFalse(video.with_suffix(".frame_index_mapping.csv").exists())
            self.assertEqual(repair_video(video), 0)
            self.assertEqual(video.with_suffix(".pts").read_text(), "33.000\n66.000\n")
            self.assertEqual(video.with_suffix(".pts").with_name("camera.pts.bak").read_bytes(), original_pts)
            self.assertFalse(video.with_suffix(".frame_index_mapping.csv").exists())
            with video.with_name("camera.mp4.timestamps.csv.bak").open(newline="") as handle:
                saved_timestamps = list(csv.DictReader(handle))
            self.assertEqual(len(saved_timestamps), 2)
            self.assertEqual([int(row["packet_index"]) for row in saved_timestamps], [0, 1])
            self.assertEqual(
                [(row["pts"], row["dts"], row["time_base_num"], row["time_base_den"])
                 for row in saved_timestamps],
                source_timestamps,
            )
            with av.open(str(video)) as container:
                self.assertEqual(sum(1 for _ in container.decode(video=0)), 2)
            repaired_video = video.read_bytes()
            with self.assertRaises(FileExistsError):
                repair_video(video)
            self.assertEqual(video.read_bytes(), repaired_video)
            self.assertEqual(video.with_name("camera.pts.bak").read_bytes(), original_pts)

            separate_source = Path(directory) / "other.mp4"
            separate_source.write_bytes(original_video)
            separate_source.with_suffix(".pts").write_bytes(original_pts)
            separate_output = Path(directory) / "repaired.mp4"
            self.assertEqual(repair_video(separate_source, separate_output), 0)
            self.assertEqual(separate_source.read_bytes(), original_video)
            self.assertEqual(separate_source.with_suffix(".pts").read_bytes(), original_pts)
            self.assertFalse(separate_source.with_name("other.pts.bak").exists())
            self.assertFalse(separate_source.with_name("other.mp4.timestamps.csv.bak").exists())
            self.assertEqual(separate_output.with_name("repaired.pts.bak").read_bytes(), original_pts)
            with separate_output.with_name("repaired.mp4.timestamps.csv.bak").open(newline="") as handle:
                self.assertEqual(list(csv.DictReader(handle)), saved_timestamps)

            failed_output = Path(directory) / "failed.mp4"
            failed_output.write_bytes(b"previous output")
            failed_output.with_suffix(".pts").write_bytes(b"previous pts")
            real_replace = os.replace

            def fail_timestamp_commit(source: Path, destination: Path) -> None:
                if Path(destination) == failed_output.with_name("failed.mp4.timestamps.csv.bak"):
                    raise OSError("timestamp commit failed")
                real_replace(source, destination)

            with patch("video_repair.os.replace", side_effect=fail_timestamp_commit):
                with self.assertRaisesRegex(OSError, "timestamp commit failed"):
                    repair_video(separate_source, failed_output)
            self.assertEqual(failed_output.read_bytes(), b"previous output")
            self.assertEqual(failed_output.with_suffix(".pts").read_bytes(), b"previous pts")
            self.assertFalse(failed_output.with_name("failed.pts.bak").exists())
            self.assertFalse(failed_output.with_name("failed.mp4.timestamps.csv.bak").exists())

            moved_source = Path(directory) / "moved.mp4"
            moved_source.write_bytes(original_video)
            moved_source.with_suffix(".pts").write_text("66.000\n33.000\n0.000\n")
            moved_output = Path(directory) / "moved_repaired.mp4"
            self.assertEqual(repair_video(moved_source, moved_output), 1)
            old_positions = moved_output.with_name("moved_repaired.pts.bak").read_text().splitlines()[:2]
            new_positions = moved_output.with_suffix(".pts").read_text().splitlines()
            self.assertEqual(
                [(original, new_positions.index(timestamp)) for original, timestamp in enumerate(old_positions)],
                [(0, 1), (1, 0)],
            )
            self.assertFalse(moved_output.with_suffix(".frame_index_mapping.csv").exists())

    def test_two_or_three_extra_timestamps_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "source.mp4"
            with av.open(str(video), "w") as container:
                stream = container.add_stream("libx264", rate=30)
                stream.width = stream.height = 16
                stream.pix_fmt = "yuv420p"
                stream.options = {"bf": "0"}
                for value in (0, 128):
                    frame = av.VideoFrame.from_ndarray(
                        np.full((16, 16, 3), value, dtype=np.uint8), format="rgb24"
                    )
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)

            for extra_count in (2, 3):
                with self.subTest(extra_count=extra_count):
                    pts = video.with_suffix(".pts")
                    original_pts = "33.000\n66.000\n" + "33.000\n" * extra_count
                    pts.write_text(original_pts)
                    output = root / f"repaired_{extra_count}.mp4"

                    self.assertEqual(repair_video(video, dry_run=True), 0)
                    self.assertEqual(repair_video(video, output), 0)
                    self.assertEqual(pts.read_text(), original_pts)
                    self.assertEqual(output.with_suffix(".pts").read_text(), "33.000\n66.000\n")
                    self.assertEqual(output.with_name(f"repaired_{extra_count}.pts.bak").read_text(), original_pts)
                    with av.open(str(output)) as container:
                        self.assertEqual(sum(1 for _ in container.decode(video=0)), 2)

    def test_larger_mismatch_leaves_files_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "camera.mp4"
            video.write_bytes(b"video")
            pts = video.with_suffix(".pts")
            pts.write_text("\n".join(str(value) for value in range(32)) + "\n")
            with patch("video_repair._count_video_packets", return_value=1):
                with self.assertRaisesRegex(ValueError, "32 entries, video has 1 packets"):
                    repair_video(video)
            self.assertEqual(video.read_bytes(), b"video")
            self.assertEqual(pts.read_text(), "\n".join(str(value) for value in range(32)) + "\n")

            with patch("video_repair._count_video_packets", return_value=1):
                with self.assertRaisesRegex(ValueError, "32 entries, video has 1 packets"):
                    repair_video(video, dry_run=True)
            self.assertFalse(video.with_suffix(".frame_index_mapping.csv").exists())


class RepairDryRunTest(unittest.TestCase):
    def test_nul_bytes_report_file_and_line_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "camera.mp4"
            pts = root / "camera.pts"
            video.write_bytes(b"untouched video")
            pts.write_bytes(b"0.000\n33.330\n\0\0\0")

            with self.assertRaisesRegex(ValueError, r"camera\.pts: NUL byte on line 3"):
                repair_video(video, dry_run=True)
            self.assertEqual(video.read_bytes(), b"untouched video")
            self.assertEqual(pts.read_bytes(), b"0.000\n33.330\n\0\0\0")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["camera.mp4", "camera.pts"])

    def test_directory_continues_after_invalid_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.mp4").write_bytes(b"")
            (root / "bad.pts").write_text("0.000\ninvalid\n")
            (root / "good.mp4").write_bytes(b"")
            (root / "good.pts").write_text("33.330\n0.000\n")

            with patch("video_repair._count_video_packets", return_value=2):
                self.assertEqual(repair_directory(root, dry_run=True), 1)
            self.assertEqual(
                sorted(p.name for p in root.iterdir()),
                ["bad.mp4", "bad.pts", "good.mp4", "good.pts", "repair_error.log", "repair_report.csv"],
            )
            error_log = (root / "repair_error.log").read_text()
            self.assertIn("Video: bad.mp4", error_log)
            self.assertIn("ValueError: Invalid timestamp", error_log)
            self.assertNotIn("Video: good.mp4", error_log)
            with (root / "repair_report.csv").open(newline="", encoding="utf-8") as handle:
                rows = {row["video"]: row for row in csv.DictReader(handle)}
            self.assertEqual(rows["good.mp4"]["status"], "checked")
            self.assertEqual(rows["good.mp4"]["count"], "1")
            self.assertEqual(rows["bad.mp4"]["status"], "failed")

    def test_directory_can_log_without_saving_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertLogs("video_repair", level="INFO") as logs:
                self.assertEqual(repair_directory(root, dry_run=True, save_report=False), 0)
            self.assertIn("Found 0 out-of-order frames across 0 videos", "\n".join(logs.output))
            self.assertFalse((root / "repair_report.csv").exists())
            self.assertFalse((root / "repair_error.log").exists())

    def test_directory_logs_positive_counts_and_saves_all_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("zero", "one", "two", "failed", "skipped", "report_only"):
                (root / f"{name}.mp4").touch()
            (root / "skipped.pts.bak").touch()
            (root / "report_only.frame_index_mapping.csv").touch()

            def fake_repair(video: Path, *, dry_run: bool) -> int:
                if video.stem == "failed":
                    raise ValueError("bad timestamps")
                return {"zero": 0, "one": 1, "two": 2, "report_only": 0}[video.stem]

            with patch("video_repair.repair_video", side_effect=fake_repair):
                with self.assertLogs("video_repair", level="INFO") as logs:
                    repair_directory(root)
            output = "\n".join(logs.output)

            with (root / "repair_report.csv").open(newline="", encoding="utf-8") as handle:
                rows = {row["video"]: row for row in csv.DictReader(handle)}
            self.assertEqual(rows["zero.mp4"]["count"], "0")
            self.assertEqual(rows["one.mp4"]["count"], "1")
            self.assertEqual(rows["two.mp4"]["count"], "2")
            self.assertEqual(rows["failed.mp4"]["status"], "failed")
            self.assertEqual(rows["failed.mp4"]["count"], "")
            self.assertEqual(rows["failed.mp4"]["error"], "bad timestamps")
            self.assertIn("ValueError: bad timestamps", (root / "repair_error.log").read_text())
            self.assertEqual(rows["skipped.mp4"]["status"], "already_repaired")
            self.assertEqual(rows["skipped.mp4"]["count"], "")
            self.assertEqual(rows["report_only.mp4"]["status"], "repaired")
            self.assertIn("repaired: 4", output)
            self.assertIn("already_repaired: 1", output)
            self.assertIn("failed: 1", output)
            self.assertIn("Found 3 out-of-order frames across 2 videos", output)
            self.assertEqual(
                output.count(":completed:"),
                4,
            )
            self.assertIn("2/6:completed:", output)
            self.assertIn("6/6:completed:", output)
            self.assertRegex(output, r"(?m)one\.mp4\s+1\s*$")
            self.assertRegex(output, r"(?m)^\s*two\.mp4\s+2\s*$")
            self.assertNotRegex(output, r"(?m)zero\.mp4\s+0\s*$")
