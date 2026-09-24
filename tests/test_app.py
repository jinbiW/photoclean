import sys

from photoclean.app import ensure_output_streams


def test_gui_process_receives_output_streams(tmp_path) -> None:
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    stream = None
    try:
        sys.stdout = None
        sys.stderr = None
        stream = ensure_output_streams(tmp_path / "photoclean.log")

        assert sys.stdout is stream
        assert sys.stderr is stream
        sys.stderr.write("torch output\n")
        stream.flush()
        assert (tmp_path / "photoclean.log").read_text(encoding="utf-8") == "torch output\n"
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if stream is not None:
            stream.close()
