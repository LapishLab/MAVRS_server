"""Losslessly put H.264 packets in camera-timestamp order."""

import argparse
import csv
import os
import shutil
import traceback
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from fractions import Fraction
from pathlib import Path

import av
import pandas as pd


TIME_BASE = Fraction(1, 1_000_000)




def _read_timestamps(path: Path) -> list[int]:
    # Picamera2 writes milliseconds; integer microseconds preserve its precision.
    timestamps = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = line.strip()
        if not value:
            continue
        if "\0" in value:
            raise ValueError(f"Corrupt PTS file {path}: NUL byte on line {line_number}")
        try:
            timestamps.append(int(Decimal(value) * 1000))
        except (InvalidOperation, ValueError, OverflowError) as error:
            raise ValueError(
                f"Invalid timestamp in {path} on line {line_number}: {value!r}"
            ) from error
    if not timestamps:
        raise ValueError(f"No timestamps in {path}")
    return timestamps


def _determine_frame_order(timestamps: list[int]) -> list[int]:
    """Return original frame indices in ascending timestamp order."""
    order = sorted(range(len(timestamps)), key=timestamps.__getitem__)
    if any(timestamps[b] == timestamps[a] for a, b in zip(order, order[1:])):
        raise ValueError("Duplicate timestamps cannot be assigned unique frame positions")
    return order


def _count_frames_behind_prior_max(timestamps: list[int]) -> int:
    """Count frames whose timestamp is below an earlier timestamp."""
    latest = timestamps[0]
    count = 0
    for timestamp in timestamps[1:]:
        if timestamp < latest:
            count += 1
        else:
            latest = timestamp
    return count


def _count_video_packets(video: Path) -> int:
    """Count video packets before assigning timestamps to their frame positions."""
    with av.open(str(video)) as source:
        if len(source.streams) != 1 or source.streams[0].type != "video":
            raise ValueError("Only single-stream videos are supported")
        return sum(packet.dts is not None for packet in source.demux(source.streams.video[0]))


def _write_original_packet_timestamps(video: Path, output: Path) -> None:
    """Save the source packet timestamps as exact time-base ticks."""
    with av.open(str(video)) as source, output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("packet_index", "pts", "dts", "time_base_num", "time_base_den"))
        for index, packet in enumerate(
            packet for packet in source.demux(source.streams.video[0]) if packet.dts is not None
        ):
            time_base = packet.time_base or packet.stream.time_base
            writer.writerow((index, packet.pts, packet.dts,
                             time_base.numerator, time_base.denominator))


def _repair_mp4(video: Path, output: Path, timestamps: list[int], order: list[int]) -> None:
    """Write reordered H.264 packets and camera timestamps to an MP4."""
    with av.open(str(video)) as source:
        if len(source.streams) != 1 or source.streams[0].type != "video":
            raise ValueError("Only single-stream videos are supported")
        in_stream = source.streams.video[0]
        if in_stream.codec_context.name != "h264" or in_stream.codec_context.has_b_frames:
            raise ValueError("This repair requires H.264 without B-frames")

        with av.open(str(output), "w", format="mp4") as target:
            out_stream = target.add_stream_from_template(in_stream)
            out_stream.time_base = TIME_BASE

            pending: dict[int, av.Packet] = {}
            count = 0
            next_output = 0
            for packet in source.demux(in_stream):
                if packet.dts is None:  # PyAV's end-of-stream flush packet
                    continue
                if count >= len(timestamps):
                    raise ValueError("Video has more packets than PTS entries")
                pending[count] = packet
                while next_output < len(order) and order[next_output] in pending:
                    index = order[next_output]
                    frame_packet = pending.pop(index)
                    frame_packet.stream = out_stream
                    frame_packet.time_base = TIME_BASE
                    frame_packet.pts = timestamps[index]
                    frame_packet.dts = timestamps[index]
                    target.mux(frame_packet)
                    next_output += 1
                count += 1
            if count != len(timestamps):
                raise ValueError(f"PTS file has {len(timestamps)} entries, video has {count} packets")


def _repair_pts(output: Path, timestamps: list[int], order: list[int]) -> None:
    """Write camera timestamps in the repaired frame order."""
    with output.open("x", encoding="utf-8") as handle:
        for index in order:
            timestamp = timestamps[index]
            handle.write(f"{timestamp // 1000}.{timestamp % 1000:03d}\n")


def repair_video(
    video: str | Path, output: str | Path | None = None, *, dry_run: bool = False, debug_print: bool = False
) -> int:
    """Repair files and return the count of timestamps below a previous maximum."""
    video = Path(video)
    pts = video.with_suffix(".pts")
    output = video if output is None else Path(output)
    output_pts = output.with_suffix(".pts")
    if not video.is_file():
        raise FileNotFoundError(video)
    timestamps = _read_timestamps(pts)
    packet_count = _count_video_packets(video)
    pts_oversize_threshold = 30
    if not packet_count <= len(timestamps) <= packet_count + pts_oversize_threshold:
        raise ValueError(f"PTS file has {len(timestamps)} entries, video has {packet_count} packets")
    timestamps = timestamps[:packet_count]
    if not timestamps:
        raise ValueError("Video has no packets")
    order = _determine_frame_order(timestamps)
    out_of_order = _count_frames_behind_prior_max(timestamps)
    if dry_run:
        return out_of_order

    backup = output.with_name(output.name + ".bak")
    backup_pts = output_pts.with_name(output_pts.name + ".bak")
    original_timestamps = output.with_name(output.name + ".timestamps.csv.bak")
    rollback_pts = output_pts.with_name(output_pts.name + ".rollback")
    for path in (backup, backup_pts, original_timestamps, rollback_pts):
        if path.exists():
            raise FileExistsError(path)
    temporary = output.with_name(output.name + ".partial")
    temporary_pts = output_pts.with_name(output_pts.name + ".partial")
    temporary_backup_pts = backup_pts.with_name(backup_pts.name + ".partial")
    temporary_timestamps = original_timestamps.with_name(original_timestamps.name + ".partial")
    for path in (temporary, temporary_pts, temporary_backup_pts, temporary_timestamps):
        if path.exists():
            raise FileExistsError(path)

    try:
        _repair_mp4(video, temporary, timestamps, order)
        _repair_pts(temporary_pts, timestamps, order)
        _write_original_packet_timestamps(video, temporary_timestamps)
        shutil.copy2(pts, temporary_backup_pts)
        had_output = output.exists()
        had_output_pts = output_pts.exists()
        try:
            if had_output:
                os.replace(output, backup)
            if had_output_pts:
                os.replace(output_pts, rollback_pts)
            os.replace(temporary, output)
            os.replace(temporary_pts, output_pts)
            os.replace(temporary_backup_pts, backup_pts)
            os.replace(temporary_timestamps, original_timestamps)
        except Exception:
            original_timestamps.unlink(missing_ok=True)
            backup_pts.unlink(missing_ok=True)
            if backup.exists():
                os.replace(backup, output)
            elif not had_output:
                output.unlink(missing_ok=True)
            if rollback_pts.exists():
                os.replace(rollback_pts, output_pts)
            elif not had_output_pts:
                output_pts.unlink(missing_ok=True)
            raise
        if had_output:
            backup.unlink()
        if had_output_pts:
            rollback_pts.unlink()
    finally:
        temporary.unlink(missing_ok=True)
        temporary_pts.unlink(missing_ok=True)
        temporary_backup_pts.unlink(missing_ok=True)
        temporary_timestamps.unlink(missing_ok=True)
    if debug_print:
        print(f"Wrote {output} and {output_pts} "
              f"({len(timestamps)} packets, {out_of_order} frames behind earlier timestamps)")
        print(f"Saved original timestamps to {original_timestamps} and PTS backup to {backup_pts}")
    return out_of_order

class RepairStatus(StrEnum):
    PENDING = "pending"
    ALREADY_REPAIRED = "already_repaired"
    FAILED = "failed"
    CHECKED = "checked"
    REPAIRED = "repaired"


def find_videos(directory) -> list[str]:
    videos = [vid for vid in directory.rglob("*.mp4")]
    videos = [vid.relative_to(directory) for vid in videos]
    videos = [str(vid) for vid in videos]
    return sorted(videos)

def repair_directory(directory: str | Path, *, dry_run: bool = False, save_report: bool = True) -> int:
    """Repair unmarked MP4s below a directory; return the number of failures."""
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(directory)

    report = pd.DataFrame()
    report["video"] = pd.Series(find_videos(directory))
    report["status"] = pd.Series([RepairStatus.PENDING] * len(report), dtype="string")
    report["count"] = pd.Series([pd.NA] * len(report), dtype="Int64")
    report["error"] = pd.Series([pd.NA] * len(report), dtype="string")
    error_log = directory / "repair_error.log"

    total_videos = len(report)
    for video_num, (index, row) in enumerate(report.iterrows(), start=1):
        video = directory / row["video"]
        if video.with_suffix(".pts.bak").is_file():
            report.at[index, "status"] = RepairStatus.ALREADY_REPAIRED
            print_progress(video_num, total_videos, video, "skipped (already repaired)")
            continue
        try:
            count = repair_video(video, dry_run=dry_run)
        except Exception as error:
            report.at[index, "status"] = RepairStatus.FAILED
            report.at[index, "error"] = str(error)
            with error_log.open("a", encoding="utf-8") as handle:
                handle.write(f"Video: {row['video']}\n")
                handle.writelines(traceback.format_exception(error))
                handle.write("\n")
            print_progress(video_num, total_videos, video, f"failed {error}")
        else:
            stat = RepairStatus.CHECKED if dry_run else RepairStatus.REPAIRED
            report.at[index, "status"] = stat
            report.at[index, "count"] = count
            print_progress(video_num, total_videos, video, "completed")
    directory_report = directory / "repair_report.csv"
    if save_report:
        report.to_csv(directory_report, index=False)
        print(f"Wrote {directory_report}")

    print("Status totals:")
    status_counts = report["status"].value_counts()
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    out_of_order = report.loc[report["count"].gt(0).fillna(False), ["video", "count"]]

    if not out_of_order.empty:
        print(out_of_order.to_string(index=False))
    total_out_of_order = int(out_of_order["count"].sum())
    print(f"Found {total_out_of_order} out-of-order frames across {len(out_of_order)} videos")
    return int(status_counts.get(RepairStatus.FAILED, 0))

def print_progress(current: int, total: int, video: Path, message: str) -> None:
    print(f"{current}/{total}:{message}:{Path(*video.parts[-3:])}")
    

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--dry-run", action="store_true",
                        help="check videos without modifying them")
    parser.add_argument("--no-save-report", action="store_false", dest="save_report",
                        help="do not write repair_report.csv")
    args = parser.parse_args()
    repair_directory(args.directory, dry_run=args.dry_run, save_report=args.save_report)


if __name__ == "__main__":
    main()
