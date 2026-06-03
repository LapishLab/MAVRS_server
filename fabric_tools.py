

import io
import sys
from fabric import Config, Connection
from fabric.group import ThreadingGroup


import sys
from fabric import Connection
from fabric.group import ThreadingGroup


class HostPrefixStream:
    """A stream wrapper that prefixes each line of output with the host name."""
    def __init__(self, host, target_stream=sys.stdout):
        self.prefix = f"[{host}] "
        self.target = target_stream
        self.at_line_start = True

    def write(self, data):
        if not data:
            return
        # Split lines but keep the endings to preserve formatting
        lines = data.splitlines(keepends=True)
        for line in lines:
            if self.at_line_start:
                self.target.write(self.prefix)
            self.target.write(line)
            # If the line ends with a newline, the next chunk should start with a prefix
            self.at_line_start = line.endswith('\n') or line.endswith('\r')

    def flush(self):
        self.target.flush()

class PrefixedConnection(Connection):
    def run(self, command, **kwargs):
        # Dynamically inject the unique stream for this specific connection instance
        if 'out_stream' not in kwargs:
            kwargs['out_stream'] = HostPrefixStream(self.host, sys.stdout)
        if 'err_stream' not in kwargs:
            kwargs['err_stream'] = HostPrefixStream(self.host, sys.stderr)
        return super().run(command, **kwargs)