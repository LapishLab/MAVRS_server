from threading import Thread, Lock
from typing import Iterable, List, Union, Any
from fabric import Connection

def run_on_connections(connections: Iterable[Connection], command: str, **kwargs) -> List[Union[Any, Exception]]:
    """Run a shell command concurrently on a list of Fabric Connection objects.

    Args:
        connections: iterable of `fabric.Connection` instances.
        command: command to run on each connection.
        **kwargs: passed through to each connection's `run()` call.

    Returns:
        List where each element corresponds to the connection at the same index
        in `connections`. Each element is either a `fabric.runners.Result` (on
        success) or an `Exception` instance (on failure).

    This mirrors the concurrent behaviour of `ThreadingGroup.run` but operates on
    an explicit list of `Connection` objects.
    """
    # Prepare a results list aligned with the input order. Each entry will
    # contain either a `fabric.runners.Result` or an Exception instance.
    conns: List[Connection] = list(connections)
    results: List[Union[Any, Exception]] = [None] * len(conns)
    lock: Lock = Lock()

    def _worker(idx: int, conn: Connection) -> None:
        try:
            res = conn.run(command, **kwargs)
            with lock:
                results[idx] = res
        except Exception as exc:
            with lock:
                results[idx] = exc

    threads = []
    for idx, c in enumerate(conns):
        t = Thread(target=_worker, args=(idx, c))
        t.daemon = True
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return results